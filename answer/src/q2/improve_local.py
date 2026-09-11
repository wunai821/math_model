"""Feasible, hot-started neighborhood improvement for question 2.

The global compact solve is better for proving prefixes.  This program takes a
separately validated incumbent, releases a changing subset of equipment, and
solves that subset exactly against the fixed schedule.  It only writes a
separate candidate artifact and never presents its neighborhood result as a
global bound.
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from q2.solve import read_plans
from q2.solve_compact import OBJECTIVE_NAMES, save, validate_resume
from verify_schedule import check_conflicts, check_operations
from console import header, summary


CACHE = Path(__file__).resolve().parents[2] / ".cache/q2"
LIMITS = (150, 20, 40, 150, 20, 40, 2000)


def options_for(p):
    """All q2 operations, including the revoke choice, as full plan records."""
    out = []
    moves = [(0, 0)] + [(df, 0) for df in range(-10, 11) if df]
    moves += [(0, dt) for dt in range(-5, 6) if dt]
    for df, dt in moves:
        if p["lo"] + df < 0 or p["hi"] + df > 100 or p["start"] + dt < 0:
            continue
        out.append(dict(p, lo=p["lo"] + df, hi=p["hi"] + df,
                        start=p["start"] + dt, end=p["end"] + dt,
                        df=df, dt=dt, canceled=False))
    out.append(dict(p, df=0, dt=0, canceled=True))
    return out


def occupied_cells(p):
    if p["canceled"]:
        return set()
    duration = p["end"] - p["start"]
    return {(t, f) for k in range(p["count"])
            for t in range(p["start"] + k * (duration + p["gap"]),
                           p["start"] + k * (duration + p["gap"]) + duration)
            for f in range(p["lo"], p["hi"])}


def vector(plans):
    stats = {group: defaultdict(int) for group in "ABC"}
    cost = 0
    for p in plans:
        group = p["id"][0]
        if p["canceled"]:
            stats[group]["canceled"] += 1
        elif p["df"] or p["dt"]:
            stats[group]["adjusted"] += 1
        cost += abs(p["df"]) + 2 * abs(p["dt"])
    return (sum(x["canceled"] for x in stats.values()), stats["A"]["canceled"],
            stats["B"]["canceled"], sum(x["adjusted"] for x in stats.values()),
            stats["A"]["adjusted"], stats["B"]["adjusted"], cost)


def weights():
    result = [1] * len(LIMITS)
    for index in range(len(result) - 2, -1, -1):
        result[index] = result[index + 1] * (LIMITS[index + 1] + 1)
    return result


def terms(p):
    adjusted = int(bool(p["df"] or p["dt"]))
    return (int(p["canceled"]), int(p["canceled"] and p["id"].startswith("A")),
            int(p["canceled"] and p["id"].startswith("B")), adjusted,
            adjusted * int(p["id"].startswith("A")), adjusted * int(p["id"].startswith("B")),
            abs(p["df"]) + 2 * abs(p["dt"]))


def select_neighborhood(plans, current, option_cache, rng, size):
    """Prioritize revoked equipment and plans competing for its candidate space."""
    current_by_id = {p["id"]: p for p in current}
    revoked = [p["id"] for p in current if p["canceled"]]
    revoked_space = set().union(*(occupied_cells(c) for ident in revoked
                                  for c in option_cache[ident] if not c["canceled"])) if revoked else set()
    touches, changed = [], []
    for p in plans:
        ident = p["id"]
        if ident in revoked:
            continue
        if current_by_id[ident]["df"] or current_by_id[ident]["dt"]:
            changed.append(ident)
        if any(occupied_cells(c) & revoked_space for c in option_cache[ident] if not c["canceled"]):
            touches.append(ident)
    rng.shuffle(touches)
    rng.shuffle(changed)
    order, seen = [], set()
    for ident in revoked + touches + changed:
        if ident not in seen:
            order.append(ident)
            seen.add(ident)
    remaining = [p["id"] for p in plans if p["id"] not in seen]
    rng.shuffle(remaining)
    order.extend(remaining)
    return set(order[:size])


def solve_round(plans, current, free, option_cache, seconds, workers, seed, b_cap=None,
                fix_prefix=0):
    fixed = {p["id"]: p for p in current if p["id"] not in free}
    occupied = set().union(*(occupied_cells(p) for p in fixed.values())) if fixed else set()
    model, choices, variables, groups, resource = cp_model.CpModel(), [], [], {}, defaultdict(list)
    for p in plans:
        if p["id"] not in free:
            continue
        indices = []
        for candidate in option_cache[p["id"]]:
            cells = occupied_cells(candidate)
            if cells & occupied:
                continue
            index = len(choices)
            choices.append(candidate)
            variable = model.new_bool_var(f"x_{index}")
            variables.append(variable)
            indices.append(index)
            for cell in cells:
                resource[cell].append(index)
        if not indices:
            return None, 0, "no legal option against fixed plan"
        groups[p["id"]] = indices
        model.add_exactly_one(variables[i] for i in indices)
    for indices in resource.values():
        if len(indices) > 1:
            model.add_at_most_one(variables[i] for i in indices)
    fixed_b = sum(p["canceled"] and p["id"].startswith("B") for p in fixed.values())
    if b_cap is not None:
        model.add(fixed_b + sum(int(c["canceled"] and c["id"].startswith("B")) * v
                                for c, v in zip(choices, variables)) <= b_cap)
    current_by_id = {p["id"]: p for p in current}
    for ident, indices in groups.items():
        old = current_by_id[ident]
        for index in indices:
            c = choices[index]
            match = (c['df'], c['dt'], c['canceled']) == (old['df'], old['dt'], old['canceled'])
            model.add_hint(variables[index], int(match))
    w = weights()
    incumbent = vector(current)
    fixed_values = vector(list(fixed.values()))
    if not 0 <= fix_prefix <= 6:
        raise ValueError('fix_prefix must be in [0, 6]')
    for index in range(fix_prefix):
        model.add(fixed_values[index] + sum(terms(c)[index] * v
                  for c, v in zip(choices, variables)) == incumbent[index])
    model.minimize(sum(sum(a * b for a, b in zip(terms(c)[fix_prefix:], w[fix_prefix:])) * v
                       for c, v in zip(choices, variables)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    validation_error = model.validate()
    if validation_error:
        raise ValueError(validation_error)
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None, len(choices), solver.status_name(status)
    selected = list(fixed.values()) + [c for c, v in zip(choices, variables) if solver.value(v)]
    selected.sort(key=lambda p: p["id"])
    return selected, len(choices), solver.status_name(status)


def write_candidate(base_plans, selected, historical, metadata, output):
    values = vector(selected)
    b_record = next((record for record in historical
                     if record.get("objective") == "cancel_B"), {})
    b_bound = b_record.get("lower_bound", 0)
    if not isinstance(b_bound, (int, float)) or b_bound > values[2]:
        b_bound = 0
    stages = []
    for index, (name, value) in enumerate(zip(OBJECTIVE_NAMES, values)):
        if index < 2:
            stages.append(dict(historical[index], resumed=True))
        else:
            stages.append(dict(objective=name, value=value, lower_bound=b_bound if name == "cancel_B" else 0,
                               status="FEASIBLE", seconds=None,
                               note="Feasible local-neighborhood result; no global optimality claim."))
    choices = {p["id"]: dict(cancel=p["canceled"], df=p["df"], dt=p["dt"]) for p in selected}
    save(base_plans, choices, stages, output)
    data = json.loads(output.read_text(encoding="utf-8"))
    data["metadata"] = metadata
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def self_test():
    """Exercise fixed-plan exclusion and the mixed-radix priority ordering."""
    def score(v):
        return sum(a * b for a, b in zip(v, weights()))
    assert score((0, 0, 1, 0, 0, 0, 0)) > score((0, 0, 0, 150, 20, 40, 2000))
    fixed = dict(id="A001", lo=0, hi=1, start=0, end=1, gap=0, count=1,
                 df=0, dt=0, canceled=False)
    original = dict(id="B001", lo=0, hi=1, start=0, end=1, gap=0, count=1)
    current = [fixed, dict(original, df=0, dt=0, canceled=True)]
    selected, _, status = solve_round([fixed, original], current, {"B001"},
                                      {"A001": options_for(fixed), "B001": options_for(original)},
                                      2, 1, 11)
    assert status in ("OPTIMAL", "FEASIBLE") and selected is not None
    moved = next(p for p in selected if p["id"] == "B001")
    assert not moved["canceled"] and (moved["df"] or moved["dt"])
    check_conflicts(selected)
    print('【问题2｜局部搜索自检】通过', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="solution.json")
    parser.add_argument("--output", default="round2.json")
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--size", type=int, default=90)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=9173)
    parser.add_argument("--b-cap", type=int, default=None,
                        help="optional conditional B-revocation cap for this neighborhood only")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--fix-prefix", type=int, default=0,
                        help="freeze incumbent counts; does not prove their optimality")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        header('问题2｜局部搜索自检')
        summary('自检结果', 状态='通过')
        return
    if (Path(args.input).name != args.input or Path(args.output).name != args.output
            or min(args.rounds, args.size, args.seconds, args.workers) <= 0
            or not 0 <= args.fix_prefix <= 6):
        parser.error("filenames must be local cache names and limits positive")
    base_plans = read_plans()
    source = {p["id"]: p for p in base_plans}
    data = json.loads((CACHE / args.input).read_text(encoding="utf-8"))
    historical = validate_resume(base_plans, data, 2)
    check_operations(source, data["plans"], 2)
    check_conflicts(data["plans"])
    current, best = data["plans"], vector(data["plans"])
    cache = {p["id"]: options_for(p) for p in base_plans}
    header('问题2｜局部邻域优化')
    rng, records, max_candidates = random.Random(args.seed), [], 0
    for number in range(args.rounds):
        free = select_neighborhood(base_plans, current, cache, rng, args.size)
        result, candidates, status = solve_round(base_plans, current, free, cache, args.seconds,
                                                  args.workers, args.seed + number, args.b_cap,
                                                  args.fix_prefix)
        max_candidates = max(max_candidates, candidates)
        record = dict(round=number + 1, free=len(free), candidates=candidates, status=status,
                      before=best)
        if result is not None:
            check_operations(source, result, 2)
            check_conflicts(result)
            candidate_vector = vector(result)
            record["after"] = candidate_vector
            record["improved"] = candidate_vector < best
            if candidate_vector < best:
                current, best = result, candidate_vector
        else:
            record["improved"] = False
        records.append(record)
        write_candidate(base_plans, current, historical,
                        dict(method="q2_local_neighborhood", input=args.input, seed=args.seed,
                             workers=args.workers, seconds=args.seconds, rounds=records,
                             initial_objective=vector(data["plans"]), final_objective=best,
                             max_candidates=max_candidates, b_cap=args.b_cap,
                             frozen_prefix=args.fix_prefix,
                             global_optimality_proven=False), CACHE / args.output)
        summary('搜索轮次', 轮次=number + 1, 邻域规模=len(free),
                候选数=candidates, 状态=status,
                是否改善='是' if record['improved'] else '否',
                目标向量=record.get('after', best))
    summary('局部搜索完成', 输出文件=str(CACHE / args.output), 目标向量=best,
            轮次数=len(records))


if __name__ == "__main__":
    main()
