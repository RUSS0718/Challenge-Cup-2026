"""Regression tests for the opt-in v2.1.8 compact finalizer."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses while retaining the public call contract."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one call and return the next scripted response."""
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "reasoning_mode": reasoning_mode,
                "timeout_seconds": timeout_seconds,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config(**overrides):
    """Build the explicit v2.1.8 profile without changing submission defaults."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.8",
        "arm_v2_mode": "selective",
        "arm_trust_policy": "positive_evidence",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV218CompactFinalizerTest(unittest.TestCase):
    """Keep incomplete primary responses recoverable without replacing incumbents."""

    @staticmethod
    def _summary(result):
        """Return the final ARM summary entry from one solve result."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_incomplete_primary_uses_bounded_finalizer(self):
        client = ScriptedClient(
            [
                {"content": "推导在预算边界处中断", "finish_reason": "length"},
                {"content": "Final answer: 42", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 40+2", {})

        summary = self._summary(result)
        self.assertEqual("42", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("compact_finalizer", summary["candidate_generation_b"]["backend"])
        self.assertIn(summary["final_source"], {"candidate_b", "safe_candidate"})
        self.assertLessEqual(client.calls[1]["max_tokens"], 2048)
        self.assertIn("只输出一行", client.calls[1]["messages"][0]["content"])

    def test_complete_primary_keeps_existing_early_stop(self):
        client = ScriptedClient([{"content": "Final answer: 2", "finish_reason": "stop"}])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertTrue(summary["early_stop"])
        self.assertNotIn("candidate_generation_b", summary)

    def test_unknown_finalizer_does_not_promote_an_empty_candidate(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未形成答案", "finish_reason": "length"},
                {"content": "UNKNOWN", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 40+2", {})

        summary = self._summary(result)
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("abstain", summary["final_source"])
        self.assertEqual("second_sample_incomplete", summary["final_failure_reason"])
        self.assertEqual("", result["extracted_answer"])


if __name__ == "__main__":
    unittest.main()
