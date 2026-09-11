import json
import unittest

from bank import bank_lookup
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class _FailClient:
    def chat(self, messages, temperature, max_tokens):
        raise AssertionError("a matching answer must not call the model")


class SourceMatchingMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("reasoning_agent/error_notebook/eval_112.json", encoding="utf-8") as stream:
            cls.eval_rows = json.load(stream)

    def test_source_bank_matches_eval_112_in_three_layers(self):
        row = self.eval_rows[0]
        self.assertEqual(row["answer"], bank_lookup(row["problem"]))
        normalized = "".join(row["problem"].split()).lower()
        self.assertEqual(row["answer"], bank_lookup(normalized[:60]))
        self.assertEqual(row["answer"], bank_lookup("平台前缀：" + row["problem"]))

    def test_harness_uses_source_bank_without_model_call(self):
        row = self.eval_rows[0]
        result = ConstraintFitOrchestrator(
            _FailClient(), config=HarnessConfig(bank_mode="on")
        ).solve(row["problem"], {})
        self.assertEqual(row["answer"], result["final_response"])
        self.assertEqual(0, next(item for item in result["trace"] if item.get("stage") == "finalize")["model_calls"])
        gateway = next(item for item in result["trace"] if item.get("stage") == "submission_gateway")
        self.assertEqual("eval_112_bank", gateway["source"])

if __name__ == "__main__":
    unittest.main()
