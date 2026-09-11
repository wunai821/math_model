"""Shared data and finite-grid helpers for questions 3 and 4."""
import hashlib
import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
ANSWER = ROOT / 'answer'


def read_plans():
    book = openpyxl.load_workbook(ROOT / '附件/附件1.xlsx', data_only=True)
    plans = []
    for ident, freq, time, gap, count in list(book.active.values)[1:]:
        lo, hi = map(int, re.findall(r'\d+', freq))
        start, end = map(int, re.findall(r'\d+', time))
        plans.append(dict(id=ident, lo=lo, hi=hi, start=start, end=end,
                          gap=int(gap), count=int(count)))
    book.close()
    return plans


def periods(p):
    d = p['end'] - p['start']
    return [(p['start'] + k * (d + p['gap']), p['end'] + k * (d + p['gap']))
            for k in range(p['count'])]


def cells(p):
    for start, end in periods(p):
        for t in range(start, end):
            for f in range(p['lo'], p['hi']):
                yield t * 100 + f


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace atomically so interrupted solves do not leave half a checkpoint.
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def interval(lo, hi):
    return f'[{lo},{hi})'
