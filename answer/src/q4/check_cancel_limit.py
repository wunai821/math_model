"""Test a global Q4 cancellation cap without overwriting the official solution."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ortools.sat.python import cp_model
from scheduling import ANSWER, ROOT, digest, read_plans, save_json
from q4.model import build_model
from q4.solve import save
from verify_schedule import check_conflicts, check_operations, source_plans


def solve(limit=3, seconds=180, workers=3, keep_a=False):
    model, candidates, variables, metadata = build_model(read_plans())
    cancels = []
    for candidate, variable in zip(candidates, variables):
        if candidate['canceled']:
            cancels.append(variable)
            if keep_a and candidate['id'].startswith('A'):
                model.add(variable == 0)
    model.add(sum(cancels) <= limit)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = 20260911
    status = solver.solve(model)
    suffix = '_keep_a' if keep_a else ''
    result = dict(status=solver.status_name(status), cancellation_limit=limit, keep_a=keep_a,
                  seconds=solver.wall_time, workers=workers, seed=20260911,
                  source_sha256=digest(ROOT / '附件/附件1.xlsx'),
                  candidates=metadata['candidates'], resource_constraints=metadata['resource_constraints'],
                  scope='Q4 model; no final time horizon; A retention enforced only if keep_a is true')
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        selected = [candidate for candidate, variable in zip(candidates, variables) if solver.value(variable)]
        check_operations(source_plans(), selected, 4)
        check_conflicts(selected)
        result['cancellations'] = sum(plan['canceled'] for plan in selected)
        # OPTIMAL here proves feasibility only, not cancellation minimality.
        stages = [dict(objective='cancel_total', status='FEASIBLE',
                       value=result['cancellations'], lower_bound=0,
                       seconds=solver.wall_time,
                       note='Feasibility search only; cancellation minimum not proved')]
        save(selected, stages, result, ANSWER / f'.cache/q4/cancel_limit_{limit}{suffix}_candidate.json')
        result['conclusion'] = 'Verified feasible candidate; cancellation minimum not proved'
    elif status == cp_model.INFEASIBLE:
        result['conditional_cancellation_lower_bound' if keep_a else 'proven_cancellation_lower_bound'] = limit + 1
        result['conclusion'] = 'Cancellation cap proved infeasible'
    else:
        result['conclusion'] = 'No conclusion; neither feasibility nor infeasibility proved'
    save_json(ANSWER / f'.cache/q4/cancel_limit_{limit}{suffix}_check.json', result)
    print(result, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--seconds', type=float, default=180)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--keep-a', action='store_true', help='Require every A plan to remain active')
    args = parser.parse_args()
    if args.limit < 0 or min(args.seconds, args.workers) <= 0:
        parser.error('limit must be nonnegative; seconds and workers must be positive')
    solve(args.limit, args.seconds, args.workers, args.keep_a)
