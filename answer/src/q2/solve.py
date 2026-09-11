"""问题2：枚举有限调整候选，并用精确资源冲突约束选择方案。"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console import OBJECTIVE_LABELS, finished, header, heartbeat, stage, summary

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / 'answer/.cache/q2'
CACHE.mkdir(parents=True, exist_ok=True)


def read_plans():
    # 统一把附件中的频段、时间段和周期参数读成整数计划记录。
    rows = list(openpyxl.load_workbook(ROOT/'附件/附件1.xlsx', data_only=True).active.values)[1:]
    plans = []
    for ident, freq, interval, gap, count in rows:
        lo, hi = map(int, re.findall(r'\d+', freq))
        start, end = map(int, re.findall(r'\d+', interval))
        plans.append(dict(id=ident, lo=lo, hi=hi, start=start, end=end, gap=gap, count=count))
    return plans


def solve(seconds, resume=False):
    # 每台装备从“不调整”、频移、时间平移和“撤销”中选择一个候选。
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
            # 候选占用的每个时频单元都记录下来，后面据此建立互斥约束。
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
    # 一个资源单元最多允许一个候选方案占用。
    exclusions = set(tuple(v) for v in cells.values() if len(v) > 1)
    for ids in exclusions:
        model.add_at_most_one(variables[i] for i in ids)
    # 按题目要求使用字典序目标，前一阶段锁定后再优化下一阶段。
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
    # 用“全部撤销”作为一定可行的初始提示，帮助求解器更快找到方案。
    for ids in by_plan:
        for i in ids:
            c = candidates[i]
            h = hints[c['id']] if resume else None
            match = (c['cancel']==h['canceled'] and c['df']==h['df'] and c['dt']==h['dt']) if h else i == ids[-1]
            model.add_hint(variables[i], int(match))
    header('问题2｜候选网格模型')
    summary('模型规模', 计划数=len(plans), 候选数=len(variables), 资源约束数=len(exclusions))
    for index, (name, cost) in enumerate(objectives, start=1):
        expr = sum(cost(c)*v for c,v in zip(candidates,variables))
        model.minimize(expr)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(seconds, 90) if resume and name=='adjust_total' else seconds
        solver.parameters.num_search_workers = min(8, os.cpu_count() or 1)
        solver.parameters.random_seed = 42
        with heartbeat(f"阶段{index}｜{OBJECTIVE_LABELS.get(name, name)}"):
            status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if selected is None:
                raise RuntimeError(solver.status_name(status))
            record = dict(objective=name, status=solver.status_name(status), note='上一阶段可行方案已保留')
            log.append(record)
            stage(record, index)
            break
        # 读取本阶段选择结果，并将目标值固定后进入下一阶段。
        values = [solver.value(v) for v in variables]
        selected = [c for c,val in zip(candidates,values) if val]
        value = int(round(solver.objective_value))
        record = dict(objective=name, value=value, lower_bound=solver.best_objective_bound, status=solver.status_name(status), seconds=round(solver.wall_time,3))
        log.append(record)
        stage(record, index)
        model.add(expr == value)
        model.clear_hints()
        for v,val in zip(variables,values):
            model.add_hint(v,val)
        save(plans, selected, log)
    save(plans, selected, log)
    finished('问题2候选网格求解', CACHE / 'solution.json',
             tuple(record['value'] for record in log if 'value' in record))


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
