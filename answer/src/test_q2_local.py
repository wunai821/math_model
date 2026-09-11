"""Validate q2 local-search hints and fixed-prefix semantics on small schedules."""
import random
import unittest

from q2.improve_local import options_for, select_neighborhood, solve_round, vector, weights, LIMITS
from verify_schedule import check_conflicts, check_operations


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.a = dict(id='A001', lo=0, hi=3, start=0, end=2, gap=8, count=2)
        self.b = dict(self.a, id='B001')
        self.source = [self.a, self.b]
        self.current = [dict(self.a, df=0, dt=0, canceled=False),
                        dict(self.b, lo=6, hi=9, df=6, dt=0, canceled=False)]
        self.options = {p['id']: options_for(p) for p in self.source}

    def test_cost_improvement_keeps_fixed_plan_and_prefix(self):
        chosen, _, status = solve_round(self.source, self.current, {'B001'},
                                       self.options, 3, 1, 12, fix_prefix=6)
        self.assertEqual(status, 'OPTIMAL')
        self.assertEqual(chosen[0], self.current[0])
        self.assertEqual(vector(chosen), (0, 0, 0, 1, 0, 1, 3))
        check_operations({p['id']: p for p in self.source}, chosen, 2)
        check_conflicts(chosen)

    def test_unfrozen_cancellation_can_be_repaired(self):
        current = [self.current[0], dict(self.b, df=0, dt=0, canceled=True)]
        chosen, _, _ = solve_round(self.source, current, {'B001'}, self.options, 3, 1, 12)
        self.assertEqual(vector(chosen)[0], 0)
        check_conflicts(chosen)

    def test_neighborhood_has_requested_distinct_equipment(self):
        free = select_neighborhood(self.source, self.current, self.options, random.Random(1), 2)
        self.assertEqual(free, {'A001', 'B001'})

    def test_lexicographic_dominance(self):
        w = weights()
        for i in range(len(w) - 1):
            self.assertGreater(w[i], sum(a * b for a, b in zip(LIMITS[i+1:], w[i+1:])))


if __name__ == '__main__':
    unittest.main()
