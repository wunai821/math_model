import unittest

from ortools.sat.python import cp_model

from q4.model import OBJECTIVE_NAMES, build_model, objective_terms


def plan(ident, lo=0, hi=100, start=0, end=10, gap=0, count=1):
    return dict(id=ident, lo=lo, hi=hi, start=start, end=end, gap=gap, count=count)


class Q4ModelTests(unittest.TestCase):
    def test_single_plan_has_one_selection_and_expected_objective_terms(self):
        model, candidates, variables, metadata = build_model([plan('A001', lo=10, hi=20)])
        self.assertEqual(len(candidates), len(variables))
        self.assertEqual(metadata['candidates'], len(candidates))
        # Candidate alternatives of the same plan share cells; the builder
        # keeps those redundant at-most-one exclusions exactly as production does.
        self.assertGreater(metadata['resource_constraints'], 0)
        self.assertEqual(cp_model.CpSolver().solve(model), cp_model.OPTIMAL)
        self.assertEqual(OBJECTIVE_NAMES[0], 'cancel_total')
        self.assertEqual(objective_terms(dict(id='B001', canceled=False, df=2, dt=0, dg=0)),
                         (0, 0, 0, 1, 0, 1, 2))

    def test_full_band_overlap_requires_a_cancellation(self):
        model, candidates, variables, _ = build_model([plan('A001'), plan('B001')])
        model.add(sum(variable for candidate, variable in zip(candidates, variables)
                      if candidate['canceled']) == 0)
        self.assertEqual(cp_model.CpSolver().solve(model), cp_model.INFEASIBLE)


if __name__ == '__main__':
    unittest.main()
