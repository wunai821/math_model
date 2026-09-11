"""Solve an equipment subset to obtain a valid global cancellation lower bound.

Deleting other equipment relaxes the full problem. Every full solution restricts
to a feasible subset solution, so its total cancellations cannot be below this
subset's proven minimum (or the solver's valid minimization lower bound).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ortools.sat.python import cp_model
from scheduling import ANSWER, ROOT, cells, digest, read_plans, save_json
from q4.solve import candidates_for
from verify_schedule import check_conflicts, check_operations
from console import header, summary, stage


def solve(groups='AB', seconds=60, workers=2):
    header(f'问题4｜{groups}类撤销下界诊断')
    plans = [p for p in read_plans() if p['id'][0] in groups]
    model = cp_model.CpModel()
    candidates, variables, cancels = [], [], []
    resources = defaultdict(list)
    for p in plans:
        selected = []
        for c in candidates_for(p):
            idx = len(candidates)
            v = model.new_bool_var(f'x{idx}')
            selected.append(v)
            candidates.append(c)
            variables.append(v)
            if c['canceled']:
                cancels.append(v)
            else:
                for cell in cells(c):
                    resources[cell].append(idx)
        model.add_exactly_one(selected)
    for ids in sorted(set(tuple(v) for v in resources.values() if len(v) > 1)):
        model.add_at_most_one(variables[i] for i in ids)
    model.minimize(sum(cancels))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    result = dict(groups=groups, equipment=len(plans), source_sha256=digest(ROOT / '附件/附件1.xlsx'),
                  status=solver.status_name(status), lower_bound=solver.best_objective_bound,
                  seconds=round(solver.wall_time, 3), workers=workers)
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        chosen = [p for p, v in zip(candidates, variables) if solver.value(v)]
        check_operations({p['id']: p for p in plans}, chosen, 4)
        check_conflicts(chosen)
        result.update(value=round(solver.objective_value), plans=chosen)
    save_json(ANSWER / f'.cache/q4/lower_bound_{groups}.json', result)
    summary('模型规模', 计划数=len(plans), 工作线程=workers)
    stage(dict(objective=f'{groups}类撤销数', value=result.get('value'),
               lower_bound=result.get('lower_bound'), status=result['status'],
               seconds=result['seconds']), 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--groups', default='AB')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not args.groups or set(args.groups) - set('ABC') or min(args.seconds, args.workers) <= 0:
        parser.error('groups must be a nonempty subset of ABC; time/workers must be positive')
    solve(args.groups, args.seconds, args.workers)
