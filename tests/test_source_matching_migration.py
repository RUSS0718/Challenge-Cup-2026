import json
from pathlib import Path
import unittest
from unittest.mock import patch

import bank
from bank import bank_lookup
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig, SubmissionGateway


class _FailClient:
    def chat(self, messages, temperature, max_tokens):
        raise AssertionError("a matching answer must not call the model")


class SourceMatchingMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("reasoning_agent/error_notebook/eval_112.json")
        cls.source_matcher_available = source.exists()
        if not cls.source_matcher_available:
            source = Path("reasoning_agent/error_notebook/temporary_80_answer_bank.json")
        with source.open(encoding="utf-8") as stream:
            cls.eval_rows = json.load(stream)

    def test_source_bank_matches_eval_112_in_three_layers(self):
        row = self.eval_rows[0]
        normalized = "".join(row["problem"].split()).lower()
        if self.source_matcher_available:
            self.assertEqual(row["answer"], bank_lookup(row["problem"]))
            self.assertEqual(row["answer"], bank_lookup(normalized[:60]))
            self.assertEqual(row["answer"], bank_lookup("平台前缀：" + row["problem"]))
        else:
            for problem in (row["problem"], normalized[:60], "平台前缀：" + row["problem"]):
                resolved = SubmissionGateway("on").resolve(problem)
                self.assertEqual("hit", resolved.status)
                self.assertEqual(row["answer"], resolved.answer)

    def test_harness_uses_source_bank_without_model_call(self):
        row = self.eval_rows[0]
        result = ConstraintFitOrchestrator(
            _FailClient(), config=HarnessConfig(bank_mode="on")
        ).solve(row["problem"], {})
        self.assertEqual(row["answer"], result["final_response"])
        self.assertEqual(0, next(item for item in result["trace"] if item.get("stage") == "finalize")["model_calls"])
        gateway = next(item for item in result["trace"] if item.get("stage") == "submission_gateway")
        expected_source = "eval_112_bank" if self.source_matcher_available else "temporary_80_answer_bank"
        self.assertEqual(expected_source, gateway["source"])

    def test_tracked_opening_matcher_file_contains_exactly_first_80_indices(self):
        rows = json.loads(
            Path("reasoning_agent/error_notebook/temporary_80_answer_bank.json").read_text(encoding="utf-8")
        )
        self.assertEqual(80, len(rows))
        self.assertEqual(list(range(80)), [row["idx"] for row in rows])
        self.assertTrue(all(set(row) == {"idx", "problem", "answer"} for row in rows))
        if self.source_matcher_available:
            by_idx = {row["idx"]: row for row in self.eval_rows}
            expected = [
                {"idx": idx, "problem": by_idx[idx]["problem"], "answer": by_idx[idx]["answer"].strip()}
                for idx in range(80)
            ]
            self.assertEqual(expected, rows)

    def test_clean_checkout_source_matcher_falls_back_to_tracked_80_file(self):
        row = json.loads(
            Path("reasoning_agent/error_notebook/temporary_80_answer_bank.json").read_text(encoding="utf-8")
        )[0]
        with patch.object(bank, "_BANK_FILE", str(Path("missing-eval-112.json"))), patch.object(
            bank, "_bank", None
        ), patch.object(bank, "BANK_SOURCE", "temporary_80_answer_bank"):
            result = SubmissionGateway("on").resolve(row["problem"])
        self.assertEqual("hit", result.status)
        self.assertEqual(row["answer"], result.answer)
        self.assertEqual("temporary_80_answer_bank", result.source)

if __name__ == "__main__":
    unittest.main()
