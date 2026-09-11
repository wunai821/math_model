"""Q3: maximum packing of identical repeated C plans around fixed Q2 plans."""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, ROOT, cells, digest, interval, periods, read_plans, save_json
from ortools.sat.python import cp_model
from console import finished, header, heartbeat, stage, summary

CACHE = ANSWER / '.cache/q3'


def solve(seconds=180, workers=8):
    source = read_plans()
    shapes = {(p['hi'] - p['lo'], p['end'] - p['start'], p['gap'], p['count'])
              for p in source if p['id'].startswith('C')}
    if len(shapes) != 1:
        raise ValueError('Q3 requires a specified homogeneous C equipment profile')
    width, duration, gap, count = shapes.pop()
    horizon = max(end for p in source for _, end in periods(p))
    q2_path = ANSWER / '.cache/q2/solution.json'
    q2 = json.loads(q2_path.read_text(encoding='utf-8'))
    if {p['id'] for p in q2['plans']} != {p['id'] for p in source}:
        raise ValueError('Q2 plans do not match the source equipment')
    occupied = set()
    for p in q2['plans']:
        if p['canceled']:
            continue
        if p['lo'] < 0 or p['hi'] > 100 or p['start'] < 0 or periods(p)[-1][1] > horizon:
            raise ValueError('Q2 plan outside original resource window')
        pcells = set(cells(p))
        if occupied.intersection(pcells):
            raise ValueError('Q2 baseline contains conflicts')
        occupied.update(pcells)
    span = duration + (count - 1) * (duration + gap)
    model = cp_model.CpModel()
    candidates, variables = [], []
    resource = defaultdict(list)
    for start in range(horizon - span + 1):
        for lo in range(101 - width):
            p = dict(lo=lo, hi=lo + width, start=start, end=start + duration, gap=gap, count=count)
            pcells = tuple(cells(p))
            if occupied.isdisjoint(pcells):
                idx = len(candidates)
                candidates.append(p)
                variables.append(model.new_bool_var(f'x{idx}'))
                for cell in pcells:
                    resource[cell].append(idx)
    exclusions = set(tuple(ids) for ids in resource.values() if len(ids) > 1)
    for ids in sorted(exclusions):
        model.add_at_most_one(variables[i] for i in ids)
    # A constructive greedy incumbent, with the exact solver proving/improving it.
    used = set()
    for p, v in zip(candidates, variables):
        pcells = set(cells(p))
        take = used.isdisjoint(pcells)
        model.add_hint(v, int(take))
        if take:
            used.update(pcells)
    area_bound = (100 * horizon - len(occupied)) // (width * duration * count)
    model.add(sum(variables) <= area_bound)
    model.maximize(sum(variables))
    header('问题3｜新增C类装备布局')
    summary('模型规模', 候选位置数=len(candidates), 资源约束数=len(exclusions),
            时间窗口=f'[0,{horizon})', 面积上界=area_bound, 工作线程=workers)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = 42
    with heartbeat('最大化新增装备数量'):
        status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        raise RuntimeError(f'No feasible Q3 solution: {solver.status_name(status)}')
    selected = [dict(p, id=i + 1) for i, p in enumerate(
        p for p, v in zip(candidates, variables) if solver.value(v))]
    result = dict(plans=selected,
        rows=[[p['id'], interval(p['lo'], p['hi']), interval(p['start'], p['end'])] for p in selected],
        count=len(selected), status=solver.status_name(status), upper_bound=solver.best_objective_bound,
        horizon=horizon, profile=dict(width=width, duration=duration, gap=gap, count=count),
        occupied_cells=len(occupied), area_upper_bound=area_bound,
        candidates=len(candidates), resource_constraints=len(exclusions),
        q2_sha256=digest(q2_path), source_sha256=digest(ROOT / '附件/附件1.xlsx'),
        seconds=round(solver.wall_time, 3), workers=workers, seed=42)
    save_json(CACHE / 'solution.json', result)
    stage(dict(objective='新增装备数量', value=result['count'],
               upper_bound=result['upper_bound'], status=result['status'],
               seconds=result['seconds']), 1)
    finished('问题3求解', CACHE / 'solution.json', result['count'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=180)
    parser.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    if min(args.seconds, args.workers) <= 0:
        parser.error('time limit and workers must be positive')
    solve(args.seconds, args.workers)
