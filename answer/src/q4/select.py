"""Select the lexicographically best valid Q4 checkpoint before export."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduling import ANSWER, save_json
from verify_schedule import check_conflicts, check_operations, require, source_plans


def objective_vector(data):
    plans = data['plans']
    canceled = lambda p: p['canceled']
    changed = lambda p: bool(p['df'] or p['dt'] or p['dg'])
    return (sum(canceled(p) for p in plans),
            sum(canceled(p) for p in plans if p['id'][0] == 'A'),
            sum(canceled(p) for p in plans if p['id'][0] == 'B'),
            sum(changed(p) for p in plans),
            sum(changed(p) for p in plans if p['id'][0] == 'A'),
            sum(changed(p) for p in plans if p['id'][0] == 'B'),
            sum(abs(p['df']) + 2 * abs(p['dt']) + abs(p['dg']) for p in plans))


def select(names):
    cache = ANSWER / '.cache/q4'
    source = source_plans()
    candidates = []
    for name in names:
        data = json.loads((cache / name).read_text(encoding='utf-8'))
        rows, stats = check_operations(source, data['plans'], 4)
        require(rows == data['rows'], f'{name}: cached submission rows mismatch')
        for group in 'ABC':
            for key in ('unchanged', 'adjusted', 'canceled', 'frequency', 'time', 'gap'):
                require(data['stats'][group][key] == stats[group][key], f'{name}: statistics mismatch')
        check_conflicts(data['plans'])
        vector = objective_vector(data)
        require(data['shift_cost'] == vector[-1], f'{name}: shift cost mismatch')
        print(json.dumps(dict(file=name, objectives=vector)))
        candidates.append((vector, name, data))
    vector, name, data = min(candidates, key=lambda entry: entry[0])
    data['comparison'] = dict(selected=name, candidates=[dict(file=n, objectives=v) for v, n, _ in candidates],
        cancel_lower_bound=max(max(d['stages'][0]['lower_bound'],
                                  d.get('comparison', {}).get('cancel_lower_bound', 0))
                               for _, _, d in candidates))
    save_json(cache / 'solution.json', data)
    print(json.dumps(dict(selected=name, objectives=vector)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='Checkpoint names inside .cache/q4')
    select(parser.parse_args().inputs)
