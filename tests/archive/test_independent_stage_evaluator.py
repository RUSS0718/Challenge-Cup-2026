import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.archive.evaluate_deterministic_math import audit
from scripts.archive.independent_stage_evaluator import evaluate_stage


class IndependentStageEvaluatorTest(unittest.TestCase):
    def test_stage_evaluator_passes_local_stages_and_blocks_missing_model_ab(self):
        root = Path(__file__).resolve().parents[2]
        items = [json.loads(line) for line in (root / "sample_data" / "medium_capability_freeze_60.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        report = audit(items)
        result = evaluate_stage(report, report)
        self.assertTrue(result["stage1_freeze_passed"])
        self.assertTrue(result["stage2_deterministic_passed"])
        self.assertTrue(result["stage3_retrieval_passed"])
        self.assertFalse(result["overall_passed"])
        self.assertIn("rag:model_ab_missing", result["failures"])


if __name__ == "__main__":
    unittest.main()
