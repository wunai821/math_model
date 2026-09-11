"""Boundary regressions for operations and independent conflict validation."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from q4.solve import candidates_for
from q4 import solve_compact
from q4 import solve as grid_solver
from q4.improve_local import MAX_VALUES, run_round, weights
from verify_schedule import check_conflicts, check_operations, parse_interval


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(id='C001', lo=0, hi=3, start=0, end=2, gap=8, count=12)

    def test_gap_domain_and_single_operation(self):
        candidates = list(candidates_for(self.base))
        gaps = {p['gap'] for p in candidates if p['dg']}
        self.assertEqual(gaps, set(range(19)) - {8})
        self.assertIn(0, gaps)
        for p in candidates:
            check_operations({'C001': self.base}, [p], 4)

    def test_non_c_cannot_change_gap(self):
        for group in 'AB':
            base = dict(self.base, id=group + '001')
            self.assertTrue(all(p['dg'] == 0 for p in candidates_for(base)))
            bad = dict(base, gap=9, df=0, dt=0, dg=1, canceled=False)
            with self.assertRaisesRegex(ValueError, 'forbidden gap'):
                check_operations({base['id']: base}, [bad], 4)

    def test_reject_simultaneous_operations(self):
        bad = dict(self.base, lo=1, hi=4, gap=9, df=1, dt=0, dg=1, canceled=False)
        with self.assertRaisesRegex(ValueError, 'multiple parameters'):
            check_operations({'C001': self.base}, [bad], 4)

    def test_reject_cancellation_with_move(self):
        bad = dict(self.base, gap=9, df=0, dt=0, dg=1, canceled=True)
        with self.assertRaisesRegex(ValueError, 'canceled and changed'):
            check_operations({'C001': self.base}, [bad], 4)

    def test_half_open_endpoints(self):
        a = dict(self.base, count=1)
        check_conflicts([a, dict(a, id='other', lo=3, hi=6)])
        check_conflicts([a, dict(a, id='other', start=2, end=4)])
        with self.assertRaisesRegex(ValueError, 'Conflict'):
            check_conflicts([a, dict(a, id='other', start=1, end=3)])

    def test_later_repeat_collision(self):
        other = dict(self.base, id='other', start=110, end=112, count=1)
        with self.assertRaisesRegex(ValueError, 'Conflict'):
            check_conflicts([self.base, other])

    def test_negative_and_fractional_intervals(self):
        self.assertEqual(parse_interval('[-1,2)'), (-1, 2))
        for value in ('[0.5,2)', '[0,2]', '[0,2,3)'):
            with self.assertRaises(ValueError):
                parse_interval(value)

    def test_compact_model_and_complete_hints(self):
        # Identical A/C plans must separate. Keeping A unchanged and moving C
        # by three frequency units attains the seven-stage optimum below.
        bases = [dict(self.base, id='A001', count=2), dict(self.base, count=2)]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'solution.json'
            with patch.object(solve_compact, 'read_plans', return_value=bases), \
                    patch.object(solve_compact, 'load_hint', return_value={}):
                solve_compact.solve(output, primary_seconds=5, later_seconds=5, workers=1)
            data = json.loads(output.read_text(encoding='utf-8'))
        check_operations({p['id']: p for p in bases}, data['plans'], 4)
        check_conflicts(data['plans'])
        self.assertEqual([s['value'] for s in data['stages']], [0, 0, 0, 1, 0, 0, 3])
        self.assertTrue(all(s['status'] == 'OPTIMAL' for s in data['stages']))

    def test_local_neighborhood_keeps_other_equipment_fixed(self):
        bases = [dict(self.base, id='A001', count=2), dict(self.base, count=2)]
        current = [dict(bases[0], df=0, dt=0, dg=0, canceled=False),
                   dict(bases[1], lo=6, hi=9, df=6, dt=0, dg=0, canceled=False)]
        result, _ = run_round(bases, current, {'C001'}, 5, 1)
        self.assertIsNotNone(result)
        by_id = {p['id']: p for p in result}
        self.assertEqual(by_id['A001'], current[0])
        self.assertEqual(by_id['C001']['df'], 3)
        check_operations({p['id']: p for p in bases}, result, 4)
        check_conflicts(result)

    def test_local_cost_preserves_priority(self):
        w = weights()
        # One cancellation must outweigh every possible improvement in all
        # lower-priority objectives, including the full 1500-unit shift cost.
        self.assertGreater(w[0], sum(v * weight for v, weight in zip(MAX_VALUES[1:], w[1:])))
        self.assertGreater(w[3], sum(v * weight for v, weight in zip(MAX_VALUES[4:], w[4:])))

    def test_grid_resume_freezes_counts_not_shift_cost(self):
        bases = [dict(self.base, id='A001', count=2), dict(self.base, count=2)]
        current = [dict(bases[0], df=0, dt=0, dg=0, canceled=False),
                   dict(bases[1], lo=6, hi=9, df=6, dt=0, dg=0, canceled=False)]
        prefix = [dict(objective=name, value=0, lower_bound=0, status='OPTIMAL', seconds=0)
                  for name in ('cancel_total', 'cancel_A', 'cancel_B')]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(grid_solver, 'CACHE', Path(tmp)), \
                    patch.object(grid_solver, 'read_plans', return_value=bases), \
                    patch.object(grid_solver, 'read_hint', return_value=({'plans': current}, 'hint.json', prefix)):
                grid_solver.solve(5, 5, 1, 'hint.json', 'out.json', 3)
            result = json.loads((Path(tmp) / 'out.json').read_text(encoding='utf-8'))
        self.assertEqual([s['value'] for s in result['stages']], [0, 0, 0, 1, 0, 0, 3])
        self.assertTrue(all(s['frozen'] for s in result['stages'][:3]))
        check_operations({p['id']: p for p in bases}, result['plans'], 4)
        check_conflicts(result['plans'])


if __name__ == '__main__':
    unittest.main()
