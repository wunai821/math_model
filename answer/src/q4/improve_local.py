"""Small-neighborhood Q4 improvement search.

This is a feasible local search only; it deliberately never replaces the
main Q4 checkpoint or claims a global optimality bound.
"""
import argparse
import json
import random
import sys
from pathlib import Path

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, cells, read_plans, save_json
from verify_schedule import check_conflicts, check_operations, source_plans
from q4.select import objective_vector
from q4.solve import candidates_for
from q4.solve_compact import save


CACHE = ANSWER / ".cache/q4"
OUT = CACHE / "local.json"
MAX_VALUES = (150, 20, 40, 150, 20, 40, 1500)


def weights():
    out = [1] * len(MAX_VALUES)
    for i in range(len(out) - 2, -1, -1):
        out[i] = out[i + 1] * (MAX_VALUES[i + 1] + 1)
    return out


def option_cells(candidate):
    return set(cells(candidate)) if not candidate["canceled"] else set()


def neighborhood(plans, current, rng, size=40):
    by_id = {p["id"]: p for p in plans}
    canceled = [p["id"] for p in current if p["canceled"]]
    priority = list(canceled)
    # Include plans whose legal time/frequency candidates touch a candidate of
    # a canceled plan. This is intentionally a small, conservative neighborhood.
    canceled_cells = set()
    for ident in canceled:
        for c in candidates_for(by_id[ident]):
            canceled_cells.update(option_cells(c))
    touches = []
    for p in plans:
        if p["id"] in priority:
            continue
        hit = any(option_cells(c) & canceled_cells for c in candidates_for(p))
        if hit:
            touches.append(p["id"])
    rng.shuffle(touches)
    priority.extend(touches)
    remaining = [p["id"] for p in plans if p["id"] not in priority]
    rng.shuffle(remaining)
    priority.extend(remaining)
    return set(priority[:size])


def run_round(plans, current, free_ids, seconds, worker_count, seed=42):
    fixed = {p["id"]: p for p in current if p["id"] not in free_ids}
    occupied = set()
    for p in fixed.values():
        occupied.update(option_cells(p))
    model = cp_model.CpModel()
    choices, variables = [], []
    resource = {}
    for p in plans:
        if p["id"] not in free_ids:
            continue
        ids = []
        for c in candidates_for(p):
            cc = option_cells(c)
            if cc & occupied:
                continue
            i = len(choices)
            choices.append(c)
            variables.append(model.new_bool_var(f"x{i}"))
            ids.append(i)
            for cell in cc:
                resource.setdefault(cell, []).append(i)
        if not ids:
            return None, 0
        model.add_exactly_one(variables[i] for i in ids)
        # Exactly one candidate is selected for this free equipment.
    for ids in resource.values():
        if len(ids) > 1:
            model.add_at_most_one(variables[i] for i in ids)
    # Hint the incumbent choice for every free plan when it remains legal.
    current_by_id = {p["id"]: p for p in current}
    for p in plans:
        if p["id"] not in free_ids:
            continue
        incumbent = current_by_id[p["id"]]
        for c, v in zip(choices, variables):
            if c["id"] == p["id"] and all(c[k] == incumbent[k] for k in
                                           ("df", "dt", "dg", "canceled")):
                model.add_hint(v, 1)
                break
    w = weights()
    def terms(c):
        changed = int(bool(c["df"] or c["dt"] or c["dg"]))
        return (int(c["canceled"]),
                int(c["canceled"] and c["id"].startswith("A")),
                int(c["canceled"] and c["id"].startswith("B")),
                changed, changed * c["id"].startswith("A"),
                changed * c["id"].startswith("B"),
                abs(c["df"]) + 2 * abs(c["dt"]) + abs(c["dg"]))
    model.minimize(sum(sum(a * b for a, b in zip(terms(c), w)) * v
                       for c, v in zip(choices, variables)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = worker_count
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None, len(choices)
    selected = list(fixed.values())
    selected.extend(c for c, v in zip(choices, variables) if solver.value(v))
    selected.sort(key=lambda p: p["id"])
    return selected, len(choices)


def main(input_name="solution.json", output_name="local.json", seed=42,
         rounds_count=12, neighborhood_size=40, seconds=6.0, worker_count=2):
    plans = read_plans()
    source = source_plans()
    if Path(input_name).name != input_name or Path(output_name).name != output_name:
        raise ValueError("input/output must be filenames inside .cache/q4")
    input_path = CACHE / input_name
    if not input_path.exists():
        raise RuntimeError(f"Missing Q4 checkpoint: {input_name}")
    data = json.loads(input_path.read_text(encoding="utf-8"))
    check_operations(source, data["plans"], 4)
    check_conflicts(data["plans"])
    current = data["plans"]
    best_vector = objective_vector(data)
    rng = random.Random(seed)
    rounds = []
    total_candidates = 0
    for number in range(rounds_count):
        size = neighborhood_size
        free = neighborhood(plans, current, rng, size)
        result, count = run_round(plans, current, free, seconds, worker_count, seed + number)
        total_candidates = max(total_candidates, count)
        if result is None:
            rounds.append(dict(round=number + 1, improved=False, candidates=count))
            continue
        check_operations(source, result, 4)
        check_conflicts(result)
        vector = objective_vector({"plans": result})
        improved = vector < best_vector
        rounds.append(dict(round=number + 1, improved=improved,
                           candidates=count, before=best_vector, after=vector))
        if improved:
            current, best_vector = result, vector
    final = {"plans": current}
    stages = [dict(objective=name, status="FEASIBLE", value=value,
                   lower_bound=0, seconds=None) for name, value in zip(
                       ("cancel_total", "cancel_A", "cancel_B", "adjust_total",
                        "adjust_A", "adjust_B", "shift_cost"), best_vector)]
    metadata = dict(local_search=True, global_optimality_proven=False,
                    initial_objective=objective_vector(data), final_objective=best_vector,
                    rounds=rounds, candidates=total_candidates,
                    max_neighborhood_candidates=total_candidates, workers=worker_count, seed=seed,
                    elapsed_seconds=None)
    metadata["method"] = "local_search"
    note = ("Derived final objective; jointly optimized in local neighborhoods, "
            "not a separately solved global stage.")
    for stage in stages:
        stage["note"] = note
    output = CACHE / output_name
    save(current, stages, metadata, output)
    print(json.dumps(dict(output=str(output), objective=best_vector, rounds=rounds), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="solution.json")
    parser.add_argument("--output", default="local.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--neighborhood-size", type=int, default=40)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if min(args.rounds, args.neighborhood_size, args.seconds, args.workers) <= 0:
        parser.error("rounds, neighborhood-size, seconds and workers must be positive")
    main(args.input, args.output, args.seed, args.rounds, args.neighborhood_size,
         args.seconds, args.workers)
