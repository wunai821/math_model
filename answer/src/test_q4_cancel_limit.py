"""Check cancellation feasibility and proof status on an unavoidable conflict."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from q4 import check_cancel_limit


class CancellationLimitTests(unittest.TestCase):
    def run_limit(self, limit, keep_a=False):
        plans = [dict(id=ident, lo=0, hi=100, start=0, end=20, gap=0, count=1)
                 for ident in ('A001', 'A002')]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(check_cancel_limit, 'ANSWER', Path(folder)), \
                 patch.object(check_cancel_limit, 'read_plans', return_value=plans), \
                 patch.object(check_cancel_limit, 'source_plans', return_value={p['id']: p for p in plans}), \
                 patch.object(check_cancel_limit, 'digest', return_value='fixture'):
                return check_cancel_limit.solve(limit, seconds=5, workers=1, keep_a=keep_a)

    def test_impossible_cap_proves_lower_bound(self):
        result = self.run_limit(0)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertEqual(result['proven_cancellation_lower_bound'], 1)

    def test_feasible_cap_does_not_claim_minimum(self):
        result = self.run_limit(1)
        self.assertEqual(result['cancellations'], 1)
        self.assertNotIn('proven_cancellation_lower_bound', result)
        self.assertIn('minimum not proved', result['conclusion'])

    def test_a_retention_bound_is_conditional(self):
        result = self.run_limit(1, keep_a=True)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('proven_cancellation_lower_bound', result)
        self.assertEqual(result['conditional_cancellation_lower_bound'], 2)


if __name__ == '__main__':
    unittest.main()
