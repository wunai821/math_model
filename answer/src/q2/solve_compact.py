"""Compact CP-SAT model for question 2."""
import json
import os
import sys
from pathlib import Path

from ortools.sat.python import cp_model
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from q2.solve import read_plans
from verify_schedule import check_operations, check_conflicts
from console import OBJECTIVE_LABELS, finished, header, heartbeat, stage, summary

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "answer/.cache/q2"
# Keep the normal command compatible with the report/export workflow.  For an
# exploratory compact run use --output compact.json, which is what this run did.
OUTPUT = CACHE / "solution.json"
HINT = CACHE / "solution.json"
LOG = CACHE / "compact.log"
PRIMARY_SECONDS, MID_SECONDS, LATE_SECONDS = 180, 90, 30
OBJECTIVE_NAMES = ('cancel_total', 'cancel_A', 'cancel_B', 'adjust_total',
                   'adjust_A', 'adjust_B', 'shift_cost')


def validate_resume(plans, data, fix_prefix):
    """Check feasibility and the complete proven prefix before reusing it."""
    if not 0 <= fix_prefix <= len(OBJECTIVE_NAMES):
        raise ValueError('fix_prefix must be in [0, 7]')
    historical = data.get('stages', [])
    if len(historical) < fix_prefix:
        raise ValueError('hint has fewer stages than the requested prefix')
    current = data.get('plans', [])
    _, stats = check_operations({p['id']: p for p in plans}, current, 2)
    check_conflicts(current)
    values = (sum(s['canceled'] for s in stats.values()), stats['A']['canceled'],
              stats['B']['canceled'], sum(s['adjusted'] for s in stats.values()),
              stats['A']['adjusted'], stats['B']['adjusted'],
              sum(abs(p['df']) + 2 * abs(p['dt']) for p in current))
    for name, value, record in zip(OBJECTIVE_NAMES[:fix_prefix], values, historical):
        if (record.get('objective') != name or record.get('status') != 'OPTIMAL'
                or record.get('value') != value or record.get('lower_bound') != value):
            raise ValueError(f'cannot lock {name}: inconsistent or unproven hint stage')
    return historical


def intervals(p):
    duration = p["end"] - p["start"]
    return [(p["start"] + k * (duration + p["gap"]),
             p["start"] + k * (duration + p["gap"]) + duration)
            for k in range(p["count"])]


def safe_differences(a, b):
    """t_a-t_b values in [-10, 10] which make all repeated periods disjoint."""
    result = []
    for d in range(-10, 11):
        overlap = any(sa + d < eb and sb < ea + d
                      for sa, ea in intervals(a) for sb, eb in intervals(b))
        if not overlap:
            result.append(d)
    return result


def load_hint(path=HINT):
    try:
        return {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8")).get("plans", [])}
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


def save(plans, choices, stages, output=OUTPUT, metadata=None):
    adjusted, rows = [], []
    stats = {g: dict(unchanged=0, adjusted=0, canceled=0, frequency=0, time=0) for g in "ABC"}
    for p in plans:
        c = choices[p["id"]]
        item = dict(p, canceled=c["cancel"], df=c["df"], dt=c["dt"])
        group = p["id"][0]
        if c["cancel"]:
            stats[group]["canceled"] += 1
            rows.append([p["id"], None, None, "是"])
        elif c["df"] or c["dt"]:
            stats[group]["adjusted"] += 1
            stats[group]["frequency" if c["df"] else "time"] += 1
            item.update(lo=p["lo"] + c["df"], hi=p["hi"] + c["df"],
                        start=p["start"] + c["dt"], end=p["end"] + c["dt"])
            rows.append([p["id"], f"[{item['lo']},{item['hi']})" if c["df"] else None,
                         f"[{item['start']},{item['end']})" if c["dt"] else None, None])
        else:
            stats[group]["unchanged"] += 1
        adjusted.append(item)
    CACHE.mkdir(parents=True, exist_ok=True)
    result = dict(plans=adjusted, rows=rows, stats=stats, stages=stages,
                  shift_cost=sum(abs(c["df"]) + 2 * abs(c["dt"])
                                 for c in choices.values()))
    if metadata is not None:
        result["metadata"] = metadata
    output.write_text(json.dumps(result,
                                 ensure_ascii=False, indent=2), encoding="utf-8")


def validate_cancel_b_experiment(output, hint_path, fix_prefix):
    """Keep capped B-cancellation runs distinct from global lexicographic solves."""
    if fix_prefix != 2:
        raise ValueError('cancel_b_limit requires fix_prefix=2')
    if Path(output).resolve() == Path(hint_path).resolve():
        raise ValueError('cancel_b_limit requires an output distinct from the hint')


def solve(output=OUTPUT, hint_path=HINT, primary_seconds=PRIMARY_SECONDS,
          mid_seconds=MID_SECONDS, late_seconds=LATE_SECONDS, workers=None,
          fix_prefix=0, cancel_b_seconds=None, cancel_b_limit=None):
    """Solve lexicographically, optionally continuing from proven prefix stages.

    ``fix_prefix`` is intentionally limited to stages marked OPTIMAL in the
    hint artifact.  This makes exploratory continuation safe: it never turns
    a time-limited incumbent into a claimed global prefix optimum.
    """
    if not 0 <= fix_prefix <= 7:
        raise ValueError('fix_prefix must be in [0, 7]')
    if any(v <= 0 for v in (primary_seconds, mid_seconds, late_seconds)) or (workers is not None and workers <= 0) or (cancel_b_seconds is not None and cancel_b_seconds <= 0):
        raise ValueError('time limits and workers must be positive')
    if cancel_b_limit is not None and cancel_b_limit < 0:
        raise ValueError('cancel_b_limit must be nonnegative')
    if cancel_b_limit is not None:
        validate_cancel_b_experiment(output, hint_path, fix_prefix)
    plans, model, hint = read_plans(), cp_model.CpModel(), load_hint(hint_path)
    historical = []
    if fix_prefix:
        historical = validate_resume(plans, json.loads(hint_path.read_text(encoding='utf-8')), fix_prefix)
    variables, cancels, changes = {}, [], []
    for p in plans:
        fv = list(range(max(-10, -p["lo"]), min(10, 100 - p["hi"]) + 1))
        tv = list(range(max(-5, -p["start"]), 6))
        f = model.new_int_var_from_domain(cp_model.Domain.FromValues(fv), f"f_{p['id']}")
        t = model.new_int_var_from_domain(cp_model.Domain.FromValues(tv), f"t_{p['id']}")
        cancel, changed = model.new_bool_var(f"cancel_{p['id']}"), model.new_bool_var(f"changed_{p['id']}")
        model.add_allowed_assignments([f, t, changed], [(0, 0, 0)] +
                                      [(x, 0, 1) for x in fv if x] + [(0, x, 1) for x in tv if x])
        model.add(f == 0).only_enforce_if(cancel)
        model.add(t == 0).only_enforce_if(cancel)
        model.add(changed == 0).only_enforce_if(cancel)
        variables[p["id"]] = dict(f=f, t=t, cancel=cancel, changed=changed, fv=fv)
        cancels.append((p, cancel)); changes.append((p, changed))
        h = hint.get(p["id"])
        if h:
            df, dt, cn = int(h.get("df", 0)), int(h.get("dt", 0)), int(bool(h.get("canceled", False)))
            if df in fv and dt in tv:
                model.add_hint(f, df); model.add_hint(t, dt); model.add_hint(cancel, cn)
                model.add_hint(changed, int(not cn and bool(df or dt)))

    pair_count = 0
    for n, a in enumerate(plans):
        va = variables[a["id"]]
        for b in plans[n + 1:]:
            vb = variables[b["id"]]
            # The pair has no possible frequency collision over either shift domain.
            if a["hi"] + max(va["fv"]) <= b["lo"] + min(vb["fv"]) or b["hi"] + max(vb["fv"]) <= a["lo"] + min(va["fv"]):
                continue
            safe = safe_differences(a, b)
            if len(safe) == 21:
                continue
            a_before = model.new_bool_var(f"f_{a['id']}_before_{b['id']}")
            b_before = model.new_bool_var(f"f_{b['id']}_before_{a['id']}")
            model.add(a["hi"] + va["f"] <= b["lo"] + vb["f"]).only_enforce_if(a_before)
            model.add(b["hi"] + vb["f"] <= a["lo"] + va["f"]).only_enforce_if(b_before)
            terms = [va["cancel"], vb["cancel"], a_before, b_before]
            if safe:
                time_safe = model.new_bool_var(f"t_{a['id']}_safe_{b['id']}")
                model.add_linear_expression_in_domain(va["t"] - vb["t"], cp_model.Domain.FromValues(safe)).only_enforce_if(time_safe)
                terms.append(time_safe)
            model.add_bool_or(terms)
            pair_count += 1

    costs = []
    for p in plans:
        v = variables[p["id"]]
        af, at = model.new_int_var(0, 10, f"abs_f_{p['id']}"), model.new_int_var(0, 5, f"abs_t_{p['id']}")
        model.add_abs_equality(af, v["f"]); model.add_abs_equality(at, v["t"])
        costs.append(af + 2 * at)
    objectives = [
        ("cancel_total", sum(v for _, v in cancels), primary_seconds),
        ("cancel_A", sum(v for p, v in cancels if p["id"].startswith("A")), late_seconds),
        ("cancel_B", sum(v for p, v in cancels if p["id"].startswith("B")), cancel_b_seconds or late_seconds),
        ("adjust_total", sum(v for _, v in changes), mid_seconds),
        ("adjust_A", sum(v for p, v in changes if p["id"].startswith("A")), late_seconds),
        ("adjust_B", sum(v for p, v in changes if p["id"].startswith("B")), late_seconds),
        ("shift_cost", sum(costs), late_seconds),
    ]
    if cancel_b_limit is not None:
        model.add(sum(v for p, v in cancels if p["id"].startswith("B")) <= cancel_b_limit)
    CACHE.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    def report(record, index=None):
        line = json.dumps(record, ensure_ascii=False)
        stage(record, index)
        with LOG.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    header('问题2｜紧凑模型')
    summary('模型规模', 计划数=len(plans), 装备对约束数=pair_count,
            变量数=len(model.proto.variables))
    stages, selected = [], None
    if fix_prefix:
        for (name, expr, _), record in zip(objectives[:fix_prefix], historical[:fix_prefix]):
            model.add(expr == int(record["value"]))
            stages.append(dict(record, resumed=True))
        selected = {p['id']: dict(cancel=hint[p['id']]['canceled'],
                                  df=hint[p['id']]['df'], dt=hint[p['id']]['dt'])
                    for p in plans}
    def experiment_metadata():
        if cancel_b_limit is None:
            return None
        b_canceled = sum(choice['cancel'] for ident, choice in selected.items()
                         if ident.startswith('B'))
        return dict(cancel_b_limit=cancel_b_limit,
                    cap_satisfied=b_canceled <= cancel_b_limit,
                    fallback=b_canceled > cancel_b_limit)
    for index, (name, expr, seconds) in enumerate(objectives[fix_prefix:], start=fix_prefix + 1):
        model.minimize(expr)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = seconds
        solver.parameters.num_search_workers = min(workers or 8, os.cpu_count() or 1)
        solver.parameters.random_seed = 42
        with heartbeat(f"阶段{index}｜{OBJECTIVE_LABELS.get(name, name)}"):
            status = solver.solve(model)
        record = dict(objective=name, status=solver.status_name(status), seconds=round(solver.wall_time, 3), lower_bound=solver.best_objective_bound)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if cancel_b_limit is not None and name == 'cancel_B':
                b_canceled = sum(choice['cancel'] for ident, choice in selected.items()
                                 if ident.startswith('B'))
                record["note"] = (f"No solution found under cancel_B <= {cancel_b_limit}; "
                                  f"retained fallback baseline has cancel_B={b_canceled} "
                                  "and does not satisfy this cap.")
            else:
                record["note"] = "No solution for this stage; retained the preceding feasible result."
            stages.append(record); report(record, index); break
        value = int(round(solver.objective_value))
        record["value"] = value
        if cancel_b_limit is not None and name == 'cancel_B':
            record["note"] = (f"Experimental run under cancel_B <= {cancel_b_limit}; "
                              "this status does not prove an unrestricted global optimum.")
        stages.append(record); report(record, index)
        selected = {p["id"]: dict(cancel=bool(solver.value(v["cancel"])), df=solver.value(v["f"]), dt=solver.value(v["t"]))
                    for p in plans for v in [variables[p["id"]]]}
        model.add(expr == value); model.clear_hints()
        for p in plans:
            v, c = variables[p["id"]], selected[p["id"]]
            model.add_hint(v["f"], c["df"]); model.add_hint(v["t"], c["dt"])
            model.add_hint(v["cancel"], int(c["cancel"]))
            model.add_hint(v["changed"], int(not c["cancel"] and bool(c["df"] or c["dt"])))
        # Persist every completed lexicographic stage so long later stages do
        # not hide a usable solution if their process is interrupted.
        save(plans, selected, stages, output, experiment_metadata())
    if selected is None:
        raise RuntimeError("No feasible compact solution")
    save(plans, selected, stages, output, experiment_metadata())
    finished('问题2紧凑模型求解', output,
             tuple(record['value'] for record in stages if 'value' in record))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="solution.json",
                        help="cache filename (use compact.json for an independent run)")
    parser.add_argument("--hint", default="solution.json", help="cache filename used for warm start and optional prefix")
    parser.add_argument("--fix-prefix", type=int, default=0,
                        help="lock this many leading objectives, only when the hint proves each OPTIMAL")
    parser.add_argument("--primary-seconds", type=float, default=PRIMARY_SECONDS)
    parser.add_argument("--mid-seconds", type=float, default=MID_SECONDS)
    parser.add_argument("--late-seconds", type=float, default=LATE_SECONDS)
    parser.add_argument("--cancel-b-seconds", type=float, default=None)
    parser.add_argument("--cancel-b-limit", type=int, default=None,
                        help="independent feasibility cap for B-category cancellations")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    solve(CACHE / args.output, CACHE / args.hint, args.primary_seconds,
          args.mid_seconds, args.late_seconds, args.workers, args.fix_prefix,
          args.cancel_b_seconds, args.cancel_b_limit)
