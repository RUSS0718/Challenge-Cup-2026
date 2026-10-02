import json
from pathlib import Path
import unittest

from scripts.run_arm_v21_eval112_timing import load_eval112


DATASET = Path(__file__).resolve().parents[1] / "reasoning_agent" / "error_notebook" / "eval_112.json"


class Eval112DatasetTest(unittest.TestCase):
    """Keep local 112-item tests bound to the team eval112 contract."""

    def test_dataset_has_exact_count_unique_idx_and_non_empty_problems(self):
        items = load_eval112(DATASET)
        self.assertEqual(112, len(items))
        self.assertEqual(112, len({item["idx"] for item in items}))
        self.assertTrue(all(str(item["problem"]).strip() for item in items))

    def test_dataset_schema_does_not_require_answer_for_timing(self):
        payload = json.loads(DATASET.read_text(encoding="utf-8"))
        self.assertTrue(all("idx" in item and "problem" in item for item in payload))


if __name__ == "__main__":
    unittest.main()
