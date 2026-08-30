import tempfile
import unittest
from pathlib import Path

from scripts.archive.evaluate_deterministic_math import audit, load_items


class DeterministicAuditTest(unittest.TestCase):
    def test_audit_keeps_reference_answers_out_of_solver(self):
        items = [{"idx": 1, "problem": "计算 6!", "answer": "720", "task_type": "calculation"}]
        report = audit(items)
        self.assertEqual(1, report["correct"])
        self.assertEqual(1, report["supported"])

    def test_unsupported_is_not_counted_as_incorrect(self):
        items = [{"idx": 2, "problem": "计算 n!", "answer": "720", "task_type": "calculation"}]
        report = audit(items)
        self.assertEqual(1, report["unsupported"])
        self.assertEqual(0, report["incorrect"])

    def test_jsonl_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "items.jsonl"
            path.write_text('{"problem":"计算 3!","answer":"6"}\n', encoding="utf-8")
            self.assertEqual(1, len(load_items(path)))


if __name__ == "__main__":
    unittest.main()
