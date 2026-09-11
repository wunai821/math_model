"""问题4：允许C类调整空闲间隔的精确候选选择模型。"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, ROOT, digest, interval, read_plans, save_json
from ortools.sat.python import cp_model
from q4.model import build_model, candidates_for
from console import OBJECTIVE_LABELS, finished, header, heartbeat, stage, summary

CACHE = ANSWER / '.cache/q4'


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
    data = dict(plans=selected, rows=rows, stats=stats,
                stages=stages, metadata=metadata,
                shift_cost=sum(abs(p['df']) + 2 * abs(p['dt']) + abs(p['dg']) for p in selected))
    if metadata.get('inherited_cancel_lower_bound') is not None:
        data['comparison'] = dict(cancel_lower_bound=metadata['inherited_cancel_lower_bound'],
                                  note='Historical bound retained from independently checked hint; not reproved here')
    save_json(output, data)


def read_hint(name):
    """Load and independently validate a Q4 cache plan before using it."""
    # 提示方案只用于加速；使用前先独立检查来源、操作范围和冲突。
    if name is None:
        paths = (CACHE / 'solution.json', ANSWER / 'benchmarks/q4_reference.json',
                 ANSWER / '.cache/q2/solution.json')
        path = next((p for p in paths if p.exists()), None)
        if path is None:
            return {}, None, []
    else:
        path = CACHE / name
    data = json.loads(path.read_text(encoding='utf-8'))
    from verify_schedule import check_conflicts, check_operations, source_plans
    expected_hash = data.get('benchmark', {}).get('source_sha256') or data.get('metadata', {}).get('source_sha256')
    if expected_hash and expected_hash != digest(ROOT / '附件/附件1.xlsx'):
        raise ValueError('Hint source SHA-256 does not match the original attachment')
    data['plans'] = [dict(p, dg=p.get('dg', 0)) for p in data['plans']]
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
    # 构造所有候选及资源互斥约束。
    model, candidates, variables, model_metadata = build_model(plans)
    metadata = dict(model_metadata,
                    source_sha256=digest(ROOT / '附件/附件1.xlsx'),
                    seed=seed, workers=workers, seconds=seconds, primary_seconds=primary_seconds,
                    hint=hint_label, frozen_prefix=fix_prefix,
                    frozen_prefix_not_global=bool(fix_prefix))
    if hint_data:
        metadata['inherited_cancel_lower_bound'] = max(
            hint_data.get('comparison', {}).get('cancel_lower_bound', 0),
            next((s.get('lower_bound', 0) for s in hint_stages
                  if s.get('objective') == 'cancel_total'), 0))
    header('问题4｜候选网格模型')
    summary('模型规模', 计划数=len(plans), 候选数=len(candidates),
            资源约束数=model_metadata['resource_constraints'], 随机种子=seed, 工作线程=workers)
    for c, v in zip(candidates, variables):
        h = hints.get(c['id'], dict(df=0, dt=0, canceled=True))
        model.add_hint(v, int(c['df'] == h['df'] and c['dt'] == h['dt'] and
                             c['dg'] == h.get('dg', 0) and c['canceled'] == h['canceled']))
    changed = lambda c: int(bool(c['df'] or c['dt'] or c['dg']))
    # 七个目标按题目规定的优先级逐层最小化。
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
    selected = hint_data.get('plans')
    # 续算时只锁定提示方案中已确认的前缀目标。
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
        finished('问题4候选网格求解', output,
                 tuple(record['value'] for record in stages if 'value' in record))
        return
    for index, (name, _) in enumerate(objectives[fix_prefix:], start=fix_prefix):
        expr = expressions[index]
        # The independently checked incumbent is feasible for the frozen prefix.
        # Keeping its current objective as an upper bound prevents a short run
        # from replacing it with a worse solution. It does not fix its moves.
        if selected:
            cost = objectives[index][1]
            model.add(expr <= sum(cost(p) for p in selected))
        model.minimize(expr)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = primary_seconds if name == 'cancel_total' else seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed
        with heartbeat(f"阶段{index + 1}｜{OBJECTIVE_LABELS.get(name, name)}"):
            status = solver.solve(model)
        record = dict(objective=name, status=solver.status_name(status),
                      lower_bound=solver.best_objective_bound, seconds=round(solver.wall_time, 3))
        if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            # 限时没有新解时保留已独立验证的可行方案。
            if selected is None:
                raise RuntimeError(f'No feasible Q4 solution: {record}')
            if status != cp_model.UNKNOWN:
                raise RuntimeError(f'Validated incumbent rejected by model: {record}')
            record.update(solver_status=record['status'], status='FEASIBLE',
                          value=sum(objectives[index][1](p) for p in selected),
                          note='Time limit without a new solution; retained independently verified incumbent')
            stages.append(record)
            save(selected, stages, metadata, output)
            break
        values = [solver.value(v) for v in variables]
        selected = [c for c, val in zip(candidates, values) if val]
        record['value'] = round(solver.objective_value)
        stages.append(record)
        stage(record, index + 1)
        save(selected, stages, metadata, output)
        model.add(expr == record['value'])
        model.clear_hints()
        for v, val in zip(variables, values):
            model.add_hint(v, val)
    finished('问题4候选网格求解', output,
             tuple(record['value'] for record in stages if 'value' in record))


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
