import json
import unittest
from pathlib import Path

from scripts.independent_audit_deterministic import audit, independent_expected


class IndependentDeterministicAuditTest(unittest.TestCase):
    def test_independent_recompute_matches_all_supported_freeze_items(self):
        path = Path(__file__).resolve().parents[1] / "sample_data" / "medium_capability_freeze_60.jsonl"
        items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        report = audit(items)
        self.assertEqual(12, report["supported"])
        self.assertEqual(12, report["independent_correct"])
        self.assertEqual([], report["mismatches"])

    def test_unsupported_form_is_not_guessed(self):
        self.assertIsNone(independent_expected("证明任意奇数平方除以8余1。"))


if __name__ == "__main__":
    unittest.main()
