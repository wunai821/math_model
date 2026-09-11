"""Reject incomplete or inconsistent checkpoints before freezing objectives."""
import copy
import unittest

from q2.solve_compact import validate_resume


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(id='A001', lo=0, hi=3, start=0, end=2, gap=8, count=2)
        self.data = dict(plans=[dict(self.base, df=0, dt=0, canceled=False)],
                         stages=[dict(objective=name, value=0, lower_bound=0,
                                      status='OPTIMAL')
                                 for name in ('cancel_total', 'cancel_A')])

    def test_valid_prefix(self):
        self.assertEqual(len(validate_resume([self.base], self.data, 2)), 2)

    def test_missing_stage(self):
        self.data['stages'].pop()
        with self.assertRaisesRegex(ValueError, 'fewer stages'):
            validate_resume([self.base], self.data, 2)

    def test_missing_plan(self):
        self.data['plans'] = []
        with self.assertRaisesRegex(ValueError, 'every original'):
            validate_resume([self.base], self.data, 2)

    def test_inconsistent_value_or_bound(self):
        for key in ('value', 'lower_bound'):
            bad = copy.deepcopy(self.data)
            bad['stages'][0][key] = 1
            with self.assertRaisesRegex(ValueError, 'inconsistent'):
                validate_resume([self.base], bad, 2)

    def test_infeasible_hint(self):
        self.data['plans'][0].update(df=1, dt=1, lo=1, hi=4, start=1, end=3)
        with self.assertRaisesRegex(ValueError, 'multiple parameters'):
            validate_resume([self.base], self.data, 2)


if __name__ == '__main__':
    unittest.main()
