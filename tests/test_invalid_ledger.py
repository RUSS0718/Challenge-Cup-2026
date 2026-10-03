"""Regression tests for P0/P1 artifact transforms."""

import json
from pathlib import Path
import tempfile
import unittest

from reasoning_agent.invalid_ledger import ledger_row
from scripts.replay_invalid_rescue import replay


class InvalidLedgerTests(unittest.TestCase):
    """Ensure ledger and replay outputs are compact and gold-free."""

    def test_ledger_excludes_gold_and_hashes_response(self):
        row = ledger_row({"item_id": "q1", "verdict": "unknown", "outcome": "invalid", "final_response": "UNKNOWN", "gold": "42", "candidate_count": 0})
        self.assertNotIn("gold", row)
        self.assertEqual(64, len(row["raw_response_hash"]))

    def test_replay_does_not_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answers.jsonl"
            source.write_text(json.dumps({"item_id": "q1", "verdict": "unknown", "outcome": "invalid", "final_response": "UNKNOWN"}) + "\n", encoding="utf-8")
            output = root / "out"
            summary = replay(source, output, expected_records=1)
            self.assertEqual(1, summary["records"])
            self.assertTrue(source.exists())
            self.assertNotIn("gold", (output / "replay.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
