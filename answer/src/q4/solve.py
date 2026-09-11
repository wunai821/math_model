"""Q4: exact candidate selection, including C-only idle-gap changes."""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, cells, interval, read_plans, save_json
from ortools.sat.python import cp_model

CACHE = ANSWER / '.cache/q4'


def candidates_for(p):
    moves = [(0, 0, 0)]
    moves += [(x, 0, 0) for x in range(-10, 11) if x]
    moves += [(0, x, 0) for x in range(-5, 6) if x]
    if p['id'].startswith('C'):
        moves += [(0, 0, x) for x in range(-10, 11) if x]
    for df, dt, dg in moves:
        if p['lo'] + df < 0 or p['hi'] + df > 100 or p['start'] + dt < 0 or p['gap'] + dg < 0:
            continue
        yield dict(p, lo=p['lo'] + df, hi=p['hi'] + df,
                   start=p['start'] + dt, end=p['end'] + dt,
                   gap=p['gap'] + dg, df=df, dt=dt, dg=dg, canceled=False)
    yield dict(p, df=0, dt=0, dg=0, canceled=True)


def save(selected, stages, metadata, output=CACHE / 'solution.json'):
    stats = {g: dict(unchanged=0, adjusted=0, canceled=0, frequency=0, time=0, gap=0) for g in 'ABC'}
    rows = []
    for p in selected:
        s = stats[p['id'][0]]
        if p['canceled']:
            s['canceled'] += 1
            rows.append([p['id'], None, None, None, '是'])
        elif p['df'] or p['dt'] or p['dg']:
            s['adjusted'] += 1
            s['frequency' if p['df'] else 'time' if p['dt'] else 'gap'] += 1
            rows.append([p['id'], interval(p['lo'], p['hi']) if p['df'] else None,
                         interval(p['start'], p['end']) if p['dt'] else None,
                         p['gap'] if p['dg'] else None, None])
        else:
            s['unchanged'] += 1
    save_json(output, dict(plans=selected, rows=rows, stats=stats,
              stages=stages, metadata=metadata,
              shift_cost=sum(abs(p['df']) + 2 * abs(p['dt']) + abs(p['dg']) for p in selected)))


def read_hint(name):
    """Load and independently validate a Q4 cache plan before using it."""
    if name is None:
        path = ANSWER / '.cache/q2/solution.json'
        if not path.exists():
            return {}, None, []
        return json.loads(path.read_text(encoding='utf-8')), path.name, []
    path = CACHE / name
    data = json.loads(path.read_text(encoding='utf-8'))
    from verify_schedule import check_conflicts, check_operations, source_plans
    check_operations(source_plans(), data['plans'], 4)
    check_conflicts(data['plans'])
    return data, path.name, data.get('stages', [])


def solve(seconds=60, primary_seconds=180, workers=8, hint_name=None,
          output_name='solution.json', fix_prefix=0, seed=42):
    if Path(output_name).name != output_name:
        raise ValueError('--output must be a filename inside .cache/q4')
    if hint_name is not None and Path(hint_name).name != hint_name:
        raise ValueError('--hint must be a filename inside .cache/q4')
    output = CACHE / output_name
    plans = read_plans()
    hint_data, hint_label, hint_stages = read_hint(hint_name)
    hints = {p['id']: p for p in hint_data.get('plans', [])} if hint_data else {}
    model = cp_model.CpModel()
    candidates, variables, groups = [], [], []
    resource = defaultdict(list)
    for p in plans:
        ids = []
        for c in candidates_for(p):
            idx = len(candidates)
            ids.append(idx)
            candidates.append(c)
            variables.append(model.new_bool_var(f'x{idx}'))
            if not c['canceled']:
                for cell in cells(c):
                    resource[cell].append(idx)
        model.add_exactly_one(variables[i] for i in ids)
        groups.append(ids)
    exclusions = set(tuple(ids) for ids in resource.values() if len(ids) > 1)
    for ids in sorted(exclusions):
        model.add_at_most_one(variables[i] for i in ids)
    metadata = dict(candidates=len(candidates), resource_constraints=len(exclusions),
                    seed=seed, workers=workers, seconds=seconds, primary_seconds=primary_seconds,
                    hint=hint_label, frozen_prefix=fix_prefix,
                    frozen_prefix_not_global=bool(fix_prefix))
    print(json.dumps(metadata), flush=True)
    for c, v in zip(candidates, variables):
        h = hints.get(c['id'], dict(df=0, dt=0, canceled=True))
        model.add_hint(v, int(c['df'] == h['df'] and c['dt'] == h['dt'] and
                             c['dg'] == h.get('dg', 0) and c['canceled'] == h['canceled']))
    changed = lambda c: int(bool(c['df'] or c['dt'] or c['dg']))
    objectives = [
        ('cancel_total', lambda c: int(c['canceled'])),
        ('cancel_A', lambda c: int(c['canceled'] and c['id'][0] == 'A')),
        ('cancel_B', lambda c: int(c['canceled'] and c['id'][0] == 'B')),
        ('adjust_total', changed),
        ('adjust_A', lambda c: changed(c) * (c['id'][0] == 'A')),
        ('adjust_B', lambda c: changed(c) * (c['id'][0] == 'B')),
        ('shift_cost', lambda c: abs(c['df']) + 2 * abs(c['dt']) + abs(c['dg'])),
    ]
    if not 0 <= fix_prefix <= len(objectives):
        raise ValueError(f'--fix-prefix must be between 0 and {len(objectives)}')
    expressions = [sum(cost(c) * v for c, v in zip(candidates, variables))
                   for _, cost in objectives]
    stages = []
    selected = hint_data.get('plans') if hint_name is not None else None
    for index in range(fix_prefix):
        name, cost = objectives[index]
        value = sum(cost(p) for p in hints.values())
        prior = next((record for record in hint_stages if record.get('objective') == name and 'value' in record), None)
        if prior is None or int(round(prior['value'])) != value:
            raise ValueError(f'Cannot freeze {name}: hint has no matching stage value')
        lower_bound = prior.get('lower_bound', 0)
        if lower_bound > value:
            raise ValueError(f'Cannot freeze {name}: invalid hint lower bound')
        model.add(expressions[index] == value)
        record = dict(prior, objective=name, value=value, lower_bound=lower_bound,
                      frozen=True,
                      note=(str(prior.get('note', '')).strip() +
                            ' Frozen from hint; this fixed prefix is not a global optimality claim.').strip())
        stages.append(record)
    if fix_prefix == len(objectives):
        save(selected, stages, metadata, output)
        return
    for index, (name, _) in enumerate(objectives[fix_prefix:], start=fix_prefix):
        expr = expressions[index]
        model.minimize(expr)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = primary_seconds if name == 'cancel_total' else seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed
        status = solver.solve(model)
        record = dict(objective=name, status=solver.status_name(status),
                      lower_bound=solver.best_objective_bound, seconds=round(solver.wall_time, 3))
        if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            stages.append(record)
            if selected is None:
                raise RuntimeError(f'No feasible Q4 solution: {record}')
            save(selected, stages, metadata, output)
            break
        values = [solver.value(v) for v in variables]
        selected = [c for c, val in zip(candidates, values) if val]
        record['value'] = round(solver.objective_value)
        stages.append(record)
        print(json.dumps(record), flush=True)
        save(selected, stages, metadata, output)
        model.add(expr == record['value'])
        model.clear_hints()
        for v, val in zip(variables, values):
            model.add_hint(v, val)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=60, help='Seconds per later objective')
    parser.add_argument('--primary-seconds', type=float, default=180)
    parser.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument('--hint', help='Validated cache filename used as a warm start')
    parser.add_argument('--output', default='solution.json', help='Cache filename for this run')
    parser.add_argument('--fix-prefix', type=int, default=0,
                        help='Fix this many leading objectives from --hint; values need not be globally optimal')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if min(args.seconds, args.primary_seconds, args.workers) <= 0:
        parser.error('time limits and workers must be positive')
    solve(args.seconds, args.primary_seconds, args.workers, args.hint, args.output, args.fix_prefix, args.seed)
