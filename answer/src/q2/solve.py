"""Question 2: finite candidate selection with exact time-frequency exclusions."""
import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import openpyxl
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / 'answer/.cache/q2'
CACHE.mkdir(parents=True, exist_ok=True)


def read_plans():
    rows = list(openpyxl.load_workbook(ROOT/'附件/附件1.xlsx', data_only=True).active.values)[1:]
    plans = []
    for ident, freq, interval, gap, count in rows:
        lo, hi = map(int, re.findall(r'\d+', freq))
        start, end = map(int, re.findall(r'\d+', interval))
        plans.append(dict(id=ident, lo=lo, hi=hi, start=start, end=end, gap=gap, count=count))
    return plans


def solve(seconds, resume=False):
    plans = read_plans()
    model = cp_model.CpModel()
    candidates, variables, by_plan = [], [], []
    cells = defaultdict(list)
    for p in plans:
        indices = []
        shifts = [(0, 0)] + [(df, 0) for df in range(-10, 11) if df] + [(0, dt) for dt in range(-5, 6) if dt]
        for df, dt in shifts:
            if p['lo']+df < 0 or p['hi']+df > 100 or p['start']+dt < 0:
                continue
            idx = len(variables)
            indices.append(idx)
            variables.append(model.new_bool_var(f"{p['id']}_{df}_{dt}"))
            candidates.append(dict(id=p['id'], df=df, dt=dt, cancel=False))
            d = p['end']-p['start']
            for k in range(p['count']):
                start = p['start'] + dt + k*(d+p['gap'])
                for t in range(start, start+d):
                    for f in range(p['lo']+df, p['hi']+df):
                        cells[t, f].append(idx)
        idx = len(variables)
        indices.append(idx)
        variables.append(model.new_bool_var(f"{p['id']}_cancel"))
        candidates.append(dict(id=p['id'], df=0, dt=0, cancel=True))
        model.add_exactly_one(variables[i] for i in indices)
        by_plan.append(indices)
    # Every resource cell admits at most one selected plan candidate.
    exclusions = set(tuple(v) for v in cells.values() if len(v) > 1)
    for ids in exclusions:
        model.add_at_most_one(variables[i] for i in ids)
    objectives = [
        ('cancel_total', lambda c: int(c['cancel'])),
        ('cancel_A', lambda c: int(c['cancel'] and c['id'][0]=='A')),
        ('cancel_B', lambda c: int(c['cancel'] and c['id'][0]=='B')),
        ('adjust_total', lambda c: int(not c['cancel'] and (c['df'] != 0 or c['dt'] != 0))),
        ('adjust_A', lambda c: int(c['id'][0]=='A' and (c['df'] != 0 or c['dt'] != 0))),
        ('adjust_B', lambda c: int(c['id'][0]=='B' and (c['df'] != 0 or c['dt'] != 0))),
        ('shift_cost', lambda c: abs(c['df'])+2*abs(c['dt'])),
    ]
    log, selected = [], None
    prior = None
    if resume:
        prior = json.loads((CACHE/'compact.json').read_text(encoding='utf-8'))
        hints = {p['id']: p for p in prior['plans']}
        for name, cost in objectives[:2]:
            old = next(s for s in prior['stages'] if s['objective'] == name)
            if old['status'] != 'OPTIMAL':
                raise ValueError(f'Resume requires a proven optimum for {name}')
            model.add(sum(cost(c)*v for c,v in zip(candidates,variables)) == old['value'])
            log.append(old)
        objectives = objectives[2:]
    # Valid initial solution: cancel every plan; the solver improves it.
    for ids in by_plan:
        for i in ids:
            c = candidates[i]
            h = hints[c['id']] if resume else None
            match = (c['cancel']==h['canceled'] and c['df']==h['df'] and c['dt']==h['dt']) if h else i == ids[-1]
            model.add_hint(variables[i], int(match))
    print(json.dumps(dict(candidates=len(variables), resource_constraints=len(exclusions))), flush=True)
    for name, cost in objectives:
        expr = sum(cost(c)*v for c,v in zip(candidates,variables))
        model.minimize(expr)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(seconds, 90) if resume and name=='adjust_total' else seconds
        solver.parameters.num_search_workers = min(8, os.cpu_count() or 1)
        solver.parameters.random_seed = 42
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if selected is None:
                raise RuntimeError(solver.status_name(status))
            log.append(dict(objective=name, status=solver.status_name(status), note='Previous feasible solution retained'))
            break
        values = [solver.value(v) for v in variables]
        selected = [c for c,val in zip(candidates,values) if val]
        value = int(round(solver.objective_value))
        record = dict(objective=name, value=value, lower_bound=solver.best_objective_bound, status=solver.status_name(status), seconds=round(solver.wall_time,3))
        log.append(record)
        print(json.dumps(record), flush=True)
        model.add(expr == value)
        model.clear_hints()
        for v,val in zip(variables,values):
            model.add_hint(v,val)
        save(plans, selected, log)
    save(plans, selected, log)


def save(plans, selected, log):
    choices = {c['id']: c for c in selected}
    adjusted, rows = [], []
    stats = {c: dict(unchanged=0, adjusted=0, canceled=0, frequency=0, time=0) for c in 'ABC'}
    for p in plans:
        c = choices[p['id']]
        q = dict(p, canceled=c['cancel'], df=c['df'], dt=c['dt'])
        if c['cancel']:
            stats[p['id'][0]]['canceled'] += 1
            rows.append([p['id'], None, None, '是'])
        elif c['df'] or c['dt']:
            stats[p['id'][0]]['adjusted'] += 1
            stats[p['id'][0]]['frequency' if c['df'] else 'time'] += 1
            q.update(lo=p['lo']+c['df'], hi=p['hi']+c['df'], start=p['start']+c['dt'], end=p['end']+c['dt'])
            rows.append([p['id'], f"[{q['lo']},{q['hi']})" if c['df'] else None, f"[{q['start']},{q['end']})" if c['dt'] else None, None])
        else:
            stats[p['id'][0]]['unchanged'] += 1
        adjusted.append(q)
    result = dict(plans=adjusted, rows=rows, stats=stats, stages=log, shift_cost=sum(abs(c['df'])+2*abs(c['dt']) for c in selected))
    (CACHE/'solution.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=45, help='Time limit per lexicographic objective')
    parser.add_argument('--resume', action='store_true', help='Use compact solution hints and fix its first two proven objectives')
    args = parser.parse_args()
    solve(args.seconds, args.resume)
