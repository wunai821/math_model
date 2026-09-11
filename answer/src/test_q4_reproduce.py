"""Reproduction must reject stale source data and corrupt benchmark results."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from q4.reproduce import REFERENCE, validate_reference, run
from scheduling import ROOT, digest
from verify_schedule import source_plans


class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
        cls.source = source_plans()
        cls.source_hash = digest(ROOT / '附件/附件1.xlsx')

    def test_reference_is_consistent(self):
        validate_reference(self.reference, self.source, self.source_hash)

    def test_changed_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            validate_reference(self.reference, self.source, 'different source')

    def test_corrupt_target_is_rejected(self):
        reference = copy.deepcopy(self.reference)
        reference['benchmark']['objectives'][0] = 2
        with self.assertRaisesRegex(ValueError, 'objective vector'):
            validate_reference(reference, self.source, self.source_hash)

    def test_old_output_cannot_masquerade_as_new_success(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'verification.json').write_text('{"ok":true}')
            with self.assertRaisesRegex(ValueError, 'not empty'):
                run(output=folder)


if __name__ == '__main__':
    unittest.main()
