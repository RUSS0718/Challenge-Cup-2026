import unittest
from pathlib import Path

from scripts.validate_medium_freeze_set import validate


class MediumFreezeSetTest(unittest.TestCase):
    def test_checked_in_medium_freeze_set_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "sample_data" / "medium_capability_freeze_60.jsonl"
        self.assertEqual([], validate(path))

    def test_public_source_gate_passes_after_filtering_non_public_items(self):
        path = Path(__file__).resolve().parents[1] / "sample_data" / "medium_capability_freeze_60.jsonl"
        errors = validate(path, require_public_sources=True)
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
