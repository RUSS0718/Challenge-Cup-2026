import unittest

from reasoning_agent.math_harness import (
    ConstraintFitOrchestrator,
    HarnessConfig,
)


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        if not self.responses:
            raise AssertionError("scripted client exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class DeepLaneTest(unittest.TestCase):
    @staticmethod
    def _ledger(result):
        return next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")

    def _config(self):
        return HarnessConfig(enable_deep_lane=True)

    def test_deep_lane_requires_independent_agreement(self):
        client = ScriptedClient(["Final answer: 42", "Final answer: 42"])
        result = ConstraintFitOrchestrator(client, config=self._config()).solve(
            "有 60 个元素，满足多个排列条件，求排列数量。"
        )
        self.assertEqual("42", result["final_response"])
        self.assertEqual([8192, 4096], [call[2] for call in client.calls])
        ledger = self._ledger(result)
        states = [state["state"] for state in ledger["states"]]
        self.assertIn("selected", states)
        self.assertEqual(2, len(ledger["typed_parses"]))
        self.assertTrue(all(item["typed_complete"] for item in ledger["typed_parses"]))
        self.assertTrue(all(
            entry.get("method") == "typed_contract_adaptive_deep_v1"
            for entry in result["trace"]
            if isinstance(entry, dict) and entry.get("stage") in {"submission_gateway", "route", "evidence_ledger", "finalize"}
        ))
        self.assertEqual("independent_agreement", next(item for item in result["trace"] if item.get("stage") == "finalize")["source"])

    def test_deep_lane_does_not_use_candidate_unproven_on_single_answer(self):
        client = ScriptedClient(["Final answer: 42", RuntimeError("review unavailable")])
        result = ConstraintFitOrchestrator(client, config=self._config()).solve(
            "有 60 个元素，满足多个排列条件，求排列数量。"
        )
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual([8192, 4096], [call[2] for call in client.calls])
        self.assertNotIn(
            "candidate_unproven",
            [item.get("reason") for item in self._ledger(result)["states"]],
        )

    def test_truncated_deep_candidate_uses_continuation(self):
        client = ScriptedClient([
            {"content": "Final answer: 42", "finish_reason": "length"},
            "Final answer: 42",
        ])
        result = ConstraintFitOrchestrator(client, config=self._config()).solve(
            "有 60 个元素，满足多个排列条件，求排列数量。"
        )
        self.assertEqual("42", result["final_response"])
        self.assertEqual([8192, 4096], [call[2] for call in client.calls])
        self.assertEqual("deep_continuation_agreement", next(item for item in result["trace"] if item.get("stage") == "finalize")["source"])
        candidates = self._ledger(result)["candidates"]
        self.assertTrue(all(item["verification_status"] == "verified" for item in candidates))

    def test_deep_conflict_uses_one_critic(self):
        client = ScriptedClient(["Final answer: 42", "Final answer: 43", "SELECT: A"])
        result = ConstraintFitOrchestrator(client, config=self._config()).solve(
            "有 60 个元素，满足多个排列条件，求排列数量。"
        )
        self.assertEqual("42", result["final_response"])
        self.assertEqual([8192, 4096, 4096], [call[2] for call in client.calls])


if __name__ == "__main__":
    unittest.main()
