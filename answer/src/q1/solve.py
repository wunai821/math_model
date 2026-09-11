import json, re
import sys
from pathlib import Path
from itertools import combinations
from collections import Counter, defaultdict
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console import header, summary

root = Path(__file__).resolve().parents[3]
cache = root / 'answer/.cache/q1'
cache.mkdir(parents=True, exist_ok=True)
plans = []
for ident, freq, time, gap, count in list(openpyxl.load_workbook(root/'附件/附件1.xlsx', data_only=True).active.values)[1:]:
    lo, hi = map(int, re.findall(r'\d+', freq))
    start, end = map(int, re.findall(r'\d+', time))
    assert 0 <= lo < hi <= 100 and start < end and gap >= 0 and count >= 1
    duration = end-start
    slots = [(start+k*(duration+gap), end+k*(duration+gap)) for k in range(count)]
    plans.append(dict(id=ident, lo=lo, hi=hi, slots=slots))
assert len(plans) == len({p['id'] for p in plans}) == 150
pairs, events = [], []
for a,b in combinations(plans,2):
    if max(a['lo'],b['lo']) >= min(a['hi'],b['hi']):
        continue
    hits = [(i+1,j+1,max(s,u),min(t,v)) for i,(s,t) in enumerate(a['slots']) for j,(u,v) in enumerate(b['slots']) if max(s,u)<min(t,v)]
    if hits:
        pairs.append([a['id'],b['id']])
        events.extend([[a['id'],b['id'],*h] for h in hits])
# Independent exact verification using occupied discrete time-frequency cells.
occupants = defaultdict(list)
for p in plans:
    for s,t in p['slots']:
        for time in range(s,t):
            for freq in range(p['lo'],p['hi']):
                occupants[time,freq].append(p['id'])
grid_pairs = set()
for ids in occupants.values():
    grid_pairs.update(tuple(sorted(x)) for x in combinations(ids,2))
assert grid_pairs == {tuple(sorted(x)) for x in pairs}
degree = Counter(x for pair in pairs for x in pair)
types = Counter(''.join(sorted([a[0],b[0]])) for a,b in pairs)
counts = Counter(p['id'][0] for p in plans)
affected = Counter(x[0] for x in degree)
stats = dict(total=len(plans), pair_count=len(pairs), event_count=len(events), types=dict(types), counts=dict(counts), affected=dict(affected), involved_count=len(degree), unaffected=[p['id'] for p in plans if p['id'] not in degree], max_degree=max(degree.values()), max_degree_ids=[x for x,d in degree.items() if d==max(degree.values())], top=degree.most_common(10), example=events[0])
(cache/'data.json').write_text(json.dumps(dict(pairs=pairs,stats=stats,events=events),ensure_ascii=False,indent=2),encoding='utf-8')
header('问题1｜冲突检测')
summary('检测结果', 计划数=stats['total'], 冲突装备对=stats['pair_count'],
        涉及装备数=stats['involved_count'], 交叠事件数=stats['event_count'])
