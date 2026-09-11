"""Rebuild Q4 from source, reproduce benchmark metrics, or search without a hint.

Reproduction is a constrained feasibility solve, not a new optimality proof.
Cold search never reads the reference decisions or fixes benchmark metrics.
"""
import argparse
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ortools
from ortools.sat.python import cp_model
from q4.model import build_model, objective_terms, OBJECTIVE_NAMES
from q4.solve import save
from q4.select import objective_vector
from scheduling import ANSWER, ROOT, digest, read_plans, save_json
from verify_schedule import check_operations, check_conflicts, source_plans
from console import heartbeat

REFERENCE = ANSWER / 'benchmarks/q4_reference.json'


def validate_reference(data, source, source_hash):
    benchmark = data['benchmark']
    if benchmark['source_sha256'] != source_hash:
        raise ValueError('Source SHA-256 does not match the benchmark')
    rows, stats = check_operations(source, data['plans'], 4)
    check_conflicts(data['plans'])
    if rows != data['rows'] or tuple(benchmark['objectives']) != objective_vector(data):
        raise ValueError('Benchmark rows or objective vector mismatch')
    for group in 'ABC':
        for key, value in data['stats'][group].items():
            if stats[group][key] != value:
                raise ValueError(f'Benchmark statistic mismatch: {group}.{key}')
    if data['shift_cost'] != objective_vector(data)[-1]:
        raise ValueError('Benchmark cost mismatch')


def run(mode='reproduce', seconds=60, workers=1, seed=20260911, output=None):
    if mode not in ('reproduce', 'search') or seconds <= 0 or workers <= 0:
        raise ValueError('Invalid mode, time limit or worker count')
    output = Path(output) if output else ANSWER / f'.cache/q4/{mode}'
    output.mkdir(parents=True, exist_ok=True)
    # Refuse reuse so an interrupted/failed run cannot expose stale success files.
    if any(output.iterdir()):
        raise ValueError(f'Output directory is not empty: {output}; choose --output with a new name')
    source_hash = digest(ROOT / '附件/附件1.xlsx')
    source = source_plans()
    reference = None
    if mode == 'reproduce':
        reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        validate_reference(reference, source, source_hash)
    model, candidates, variables, model_meta = build_model(read_plans())
    expressions = [sum(objective_terms(c)[i] * v for c, v in zip(candidates, variables))
                   for i in range(len(OBJECTIVE_NAMES))]
    expected = reference['benchmark']['objectives'] if reference else None
    if reference:
        for expr, value in zip(expressions, expected):
            model.add(expr == value)
        hints = {p['id']: p for p in reference['plans']}
        for candidate, variable in zip(candidates, variables):
            p = hints[candidate['id']]
            model.add_hint(variable, int(all(candidate[k] == p[k]
                                           for k in ('df', 'dt', 'dg', 'canceled'))))
    else:
        # The first step of the successful two-step recipe: cap 3 and retain A.
        # No benchmark file, previous Q2/Q4 plan, or fixed individual move is read.
        model.add(expressions[0] <= 3)
        model.add(expressions[1] == 0)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.stop_after_first_solution = True
    model_error = model.validate()
    if model_error:
        raise ValueError(model_error)
    report = dict(ok=False, mode=mode, source_sha256=source_hash,
                  reference_sha256=digest(REFERENCE) if reference else None,
                  model_sha256=digest(Path(__file__).with_name('model.py')),
                  runner_sha256=digest(Path(__file__)),
                  implementation_sha256={name: digest(ANSWER / 'src' / name) for name in
                      ('q4/model.py', 'q4/solve.py', 'q4/select.py', 'q4/reproduce.py',
                       'scheduling.py', 'verify_schedule.py', 'console.py')},
                  lock_sha256=digest(ANSWER / 'uv.lock'),
                  python=platform.python_version(), ortools=ortools.__version__,
                  platform=platform.platform(), parameters=dict(seconds=seconds, workers=workers, seed=seed),
                  fixed_objective_vector=expected, fixed_equipment_moves=False,
                  hint_used=bool(reference), optimality_proved=False,
                  note='Known objective-vector feasibility reconstruction' if reference
                       else 'Cold feasibility search for <=3 cancellations and zero A cancellations')
    print(f'Q4 {mode}: {len(source)} plans, {len(candidates)} candidates', flush=True)
    with heartbeat('问题4｜复测求解' if reference else '问题4｜无提示重新搜索'):
        status = solver.solve(model)
    report.update(solver_status=solver.status_name(status), seconds=solver.wall_time,
                  deterministic_time=solver.response_proto.deterministic_time)
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        selected = [c for c, v in zip(candidates, variables) if solver.value(v)]
        rows, stats = check_operations(source, selected, 4)
        pairs = check_conflicts(selected)
        vector = objective_vector({'plans': selected})
        if expected is not None and vector != tuple(expected):
            raise ValueError('Solver result does not reproduce benchmark objectives')
        if vector[0] > 3 or vector[1] != 0:
            raise ValueError('Three cancellations with A retention not achieved')
        stages = [dict(objective=name, value=value, lower_bound=0, status='FEASIBLE',
                       seconds=None, note='Feasibility only; no objective minimum proved')
                  for name, value in zip(OBJECTIVE_NAMES, vector)]
        metadata = dict(model_meta, method='benchmark_feasibility' if reference else 'cold_feasibility',
                        source_sha256=source_hash, seed=seed, workers=workers,
                        benchmark_constraints=expected, optimality_proved=False)
        save(selected, stages, metadata, output / 'solution.json')
        written = json.loads((output / 'solution.json').read_text(encoding='utf-8'))
        if written['rows'] != rows or objective_vector(written) != vector:
            raise ValueError('Saved solution verification failed')
        report.update(ok=True, objectives=list(vector), pair_checks=pairs, conflicts=0,
                      solution_sha256=digest(output / 'solution.json'),
                      same_plans_as_reference=(selected == reference['plans']) if reference else None)
    else:
        report['note'] += '; no feasible solution produced; UNKNOWN is not infeasibility'
    save_json(output / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('reproduce', 'search'), default='reproduce')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--seed', type=int, default=20260911)
    parser.add_argument('--output', type=Path, help='New empty directory for independent outputs')
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.mode, args.seconds, args.workers, args.seed, args.output))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'Reproduction failed: {error}\n')
