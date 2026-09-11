"""Shared exact candidate model for question 4."""
from collections import defaultdict

from ortools.sat.python import cp_model

from scheduling import cells

OBJECTIVE_NAMES = ('cancel_total', 'cancel_A', 'cancel_B', 'adjust_total',
                   'adjust_A', 'adjust_B', 'shift_cost')


def objective_terms(candidate):
    """Return Q4's seven lexicographic objective coefficients for a candidate."""
    canceled = int(candidate['canceled'])
    group = candidate['id'][0]
    adjusted = int(not canceled and bool(candidate['df'] or candidate['dt'] or candidate['dg']))
    return (canceled, canceled * (group == 'A'), canceled * (group == 'B'),
            adjusted, adjusted * (group == 'A'), adjusted * (group == 'B'),
            abs(candidate['df']) + 2 * abs(candidate['dt']) + abs(candidate['dg']))


def candidates_for(p):
    """Enumerate the Q4 legal one-parameter moves and cancellation option."""
    moves = [(0, 0, 0)]
    moves += [(x, 0, 0) for x in range(-10, 11) if x]
    moves += [(0, x, 0) for x in range(-5, 6) if x]
    if p['id'].startswith('C'):
        moves += [(0, 0, x) for x in range(-10, 11) if x]
    for df, dt, dg in moves:
        if p['lo'] + df < 0 or p['hi'] + df > 100 or p['start'] + dt < 0 or p['gap'] + dg < 0:
            continue
        yield dict(p, lo=p['lo'] + df, hi=p['hi'] + df,
                   start=p['start'] + dt, end=p['end'] + dt,
                   gap=p['gap'] + dg, df=df, dt=dt, dg=dg, canceled=False)
    yield dict(p, df=0, dt=0, dg=0, canceled=True)


def build_model(plans):
    """Build Q4's exact grid-selection model.

    Returns ``(model, candidates, variables, metadata)``.  Candidate ordering,
    resource-cell exclusions, and exactly-one selection constraints are shared
    by the lexicographic solver and cap-feasibility checks.
    """
    model = cp_model.CpModel()
    candidates, variables = [], []
    resource = defaultdict(list)
    for p in plans:
        indices = []
        for candidate in candidates_for(p):
            index = len(candidates)
            candidates.append(candidate)
            variables.append(model.new_bool_var(f'x{index}'))
            indices.append(index)
            if not candidate['canceled']:
                for cell in cells(candidate):
                    resource[cell].append(index)
        model.add_exactly_one(variables[index] for index in indices)
    exclusions = sorted({tuple(indices) for indices in resource.values() if len(indices) > 1})
    for indices in exclusions:
        model.add_at_most_one(variables[index] for index in indices)
    metadata = dict(candidates=len(candidates), resource_constraints=len(exclusions))
    return model, candidates, variables, metadata
