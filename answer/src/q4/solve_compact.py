"""Compact CP-SAT model for question 4.

Each equipment item has one frequency-shift variable and one enumerated
time/gap mode.  This avoids materialising a Boolean for every grid cell.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, interval, read_plans, save_json
from q4.solve import candidates_for


CACHE = ANSWER / ".cache/q4"
OUTPUT = CACHE / "compact.json"
PRIMARY_SECONDS = 120
LATER_SECONDS = 60
WORKERS = 4


def modes_for(plan):
    """Return legal (dt, dg) choices and their complete occupied-time masks."""
    modes = []
    seen = set()
    for candidate in candidates_for(plan):
        if candidate["canceled"]:
            continue
        mode = (candidate["dt"], candidate["dg"])
        if mode in seen:
            continue
        seen.add(mode)
        duration = candidate["end"] - candidate["start"]
        mask = 0
        for repeat in range(candidate["count"]):
            start = candidate["start"] + repeat * (duration + candidate["gap"])
            # Times are non-negative by candidates_for, so this is a compact
            # exact bitset representation of every occupied integer period.
            mask |= ((1 << duration) - 1) << start
        modes.append((mode[0], mode[1], mask))
    modes.sort(key=lambda value: (value[0] != 0 or value[1] != 0, value[0], value[1]))
    assert modes[0][:2] == (0, 0)
    return modes


def frequency_values(plan):
    return sorted({candidate["df"] for candidate in candidates_for(plan)
                   if not candidate["canceled"] and candidate["dt"] == 0 and candidate["dg"] == 0})


def load_hint():
    """Prefer the current Q4 result; Q2 is also feasible in the Q4 domain."""
    for path in (CACHE / "solution.json", ANSWER / ".cache/q2/solution.json"):
        try:
            plans = json.loads(path.read_text(encoding="utf-8"))["plans"]
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        values = {plan["id"]: plan for plan in plans}
        if values:
            return values
    return {}


def save(selected, stages, metadata, output=OUTPUT):
    stats = {group: dict(unchanged=0, adjusted=0, canceled=0,
                         frequency=0, time=0, gap=0) for group in "ABC"}
    rows = []
    for plan in selected:
        stat = stats[plan["id"][0]]
        if plan["canceled"]:
            stat["canceled"] += 1
            rows.append([plan["id"], None, None, None, "是"])
        elif plan["df"] or plan["dt"] or plan["dg"]:
            stat["adjusted"] += 1
            stat["frequency" if plan["df"] else "time" if plan["dt"] else "gap"] += 1
            rows.append([plan["id"], interval(plan["lo"], plan["hi"]) if plan["df"] else None,
                         interval(plan["start"], plan["end"]) if plan["dt"] else None,
                         plan["gap"] if plan["dg"] else None, None])
        else:
            stat["unchanged"] += 1
    save_json(output, dict(plans=selected, rows=rows, stats=stats, stages=stages,
                           metadata=metadata,
                           shift_cost=sum(abs(plan["df"]) + 2 * abs(plan["dt"]) + abs(plan["dg"])
                                          for plan in selected)))


def solve(output=OUTPUT, primary_seconds=PRIMARY_SECONDS, later_seconds=LATER_SECONDS,
          workers=WORKERS):
    plans = read_plans()
    model = cp_model.CpModel()
    variables, cancel_terms, change_terms, shift_terms = {}, [], [], []

    for plan in plans:
        frequencies = frequency_values(plan)
        modes = modes_for(plan)
        f = model.new_int_var_from_domain(cp_model.Domain.FromValues(frequencies), f"f_{plan['id']}")
        mode = model.new_int_var(0, len(modes) - 1, f"mode_{plan['id']}")
        cancel = model.new_bool_var(f"cancel_{plan['id']}")
        changed = model.new_bool_var(f"changed_{plan['id']}")
        allowed = [(0, 0, 0)]
        allowed += [(value, 0, 1) for value in frequencies if value]
        allowed += [(0, index, 1) for index in range(1, len(modes))]
        model.add_allowed_assignments([f, mode, changed], allowed)
        model.add(f == 0).only_enforce_if(cancel)
        model.add(mode == 0).only_enforce_if(cancel)
        model.add(changed == 0).only_enforce_if(cancel)
        variables[plan["id"]] = dict(f=f, mode=mode, cancel=cancel, changed=changed,
                                      frequencies=frequencies, modes=modes)
        cancel_terms.append((plan, cancel))
        change_terms.append((plan, changed))

        # Cost is represented directly by the (frequency, mode) state.
        costs = []
        for frequency in frequencies:
            for index, (dt, dg, _) in enumerate(modes):
                if (frequency == 0 and index == 0) or (frequency != 0 and index == 0) or (frequency == 0 and index != 0):
                    costs.append((frequency, index, abs(frequency) + 2 * abs(dt) + abs(dg)))
        cost = model.new_int_var(0, 30, f"cost_{plan['id']}")
        model.add_allowed_assignments([f, mode, cost], costs)
        shift_terms.append(cost)

    hint = load_hint()
    for plan in plans:
        value, saved = variables[plan["id"]], hint.get(plan["id"])
        if not saved:
            continue
        df, dt, dg = int(saved.get("df", 0)), int(saved.get("dt", 0)), int(saved.get("dg", 0))
        try:
            index = next(i for i, item in enumerate(value["modes"]) if item[:2] == (dt, dg))
        except StopIteration:
            continue
        canceled = int(bool(saved.get("canceled", False)))
        if df not in value["frequencies"] or (canceled and (df or index)):
            continue
        model.add_hint(value["f"], df); model.add_hint(value["mode"], index)
        model.add_hint(value["cancel"], canceled)
        model.add_hint(value["changed"], int(not canceled and bool(df or dt or dg)))

    pair_count, safe_table_count = 0, 0
    for number, left in enumerate(plans):
        lv = variables[left["id"]]
        for right in plans[number + 1:]:
            rv = variables[right["id"]]
            # No frequency position can overlap, so the pair needs no constraint.
            if (left["hi"] + max(lv["frequencies"]) <= right["lo"] + min(rv["frequencies"]) or
                    right["hi"] + max(rv["frequencies"]) <= left["lo"] + min(lv["frequencies"])):
                continue
            safe_pairs = [(i, j) for i, a in enumerate(lv["modes"])
                          for j, b in enumerate(rv["modes"]) if not (a[2] & b[2])]
            # Every possible time/gap state is already disjoint.  This pair
            # cannot collide even when its frequency ranges intersect.
            if len(safe_pairs) == len(lv["modes"]) * len(rv["modes"]):
                continue
            left_before = model.new_bool_var(f"f_{left['id']}_before_{right['id']}")
            right_before = model.new_bool_var(f"f_{right['id']}_before_{left['id']}")
            model.add(left["hi"] + lv["f"] <= right["lo"] + rv["f"]).only_enforce_if(left_before)
            model.add(right["hi"] + rv["f"] <= left["lo"] + lv["f"]).only_enforce_if(right_before)
            terms = [lv["cancel"], rv["cancel"], left_before, right_before]
            if safe_pairs:
                time_safe = model.new_bool_var(f"t_{left['id']}_safe_{right['id']}")
                model.add_allowed_assignments([lv["mode"], rv["mode"]], safe_pairs).only_enforce_if(time_safe)
                terms.append(time_safe)
                safe_table_count += 1
            model.add_bool_or(terms)
            pair_count += 1

    metadata = dict(plans=len(plans), pair_constraints=pair_count,
                    time_safe_tables=safe_table_count, variables=len(model.proto.variables),
                    primary_seconds=primary_seconds, later_seconds=later_seconds,
                    workers=workers, seed=42)
    print(json.dumps(metadata), flush=True)
    objectives = [
        ("cancel_total", sum(term for _, term in cancel_terms), primary_seconds),
        ("cancel_A", sum(term for plan, term in cancel_terms if plan["id"].startswith("A")), later_seconds),
        ("cancel_B", sum(term for plan, term in cancel_terms if plan["id"].startswith("B")), later_seconds),
        ("adjust_total", sum(term for _, term in change_terms), later_seconds),
        ("adjust_A", sum(term for plan, term in change_terms if plan["id"].startswith("A")), later_seconds),
        ("adjust_B", sum(term for plan, term in change_terms if plan["id"].startswith("B")), later_seconds),
        ("shift_cost", sum(shift_terms), later_seconds),
    ]
    stages, selected = [], None
    for name, expression, seconds in objectives:
        model.minimize(expression)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = 42
        status = solver.solve(model)
        record = dict(objective=name, status=solver.status_name(status),
                      lower_bound=solver.best_objective_bound, seconds=round(solver.wall_time, 3))
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            record["note"] = "No solution for this stage; retained the preceding feasible result."
            stages.append(record); print(json.dumps(record), flush=True)
            if selected is None:
                raise RuntimeError(f"No feasible compact Q4 solution: {record}")
            save(selected, stages, metadata, output)
            break
        value = int(round(solver.objective_value))
        record["value"] = value
        stages.append(record); print(json.dumps(record), flush=True)
        selected = []
        for plan in plans:
            value_vars = variables[plan["id"]]
            frequency, index = solver.value(value_vars["f"]), solver.value(value_vars["mode"])
            dt, dg, _ = value_vars["modes"][index]
            selected.append(dict(plan, lo=plan["lo"] + frequency, hi=plan["hi"] + frequency,
                                 start=plan["start"] + dt, end=plan["end"] + dt,
                                 gap=plan["gap"] + dg, df=frequency, dt=dt, dg=dg,
                                 canceled=bool(solver.value(value_vars["cancel"])) ))
        model.add(expression == value)
        model.clear_hints()
        # Include auxiliary Booleans and table-cost variables too, so CP-SAT
        # receives a complete feasible assignment at the next lexicographic stage.
        for index in range(len(model.proto.variables)):
            variable = model.get_int_var_from_proto_index(index)
            model.add_hint(variable, solver.value(variable))
        save(selected, stages, metadata, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="compact.json")
    parser.add_argument("--primary-seconds", type=float, default=PRIMARY_SECONDS)
    parser.add_argument("--later-seconds", type=float, default=LATER_SECONDS)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    if min(args.primary_seconds, args.later_seconds, args.workers) <= 0:
        parser.error("time limits and workers must be positive")
    solve(CACHE / args.output, args.primary_seconds, args.later_seconds, args.workers)
