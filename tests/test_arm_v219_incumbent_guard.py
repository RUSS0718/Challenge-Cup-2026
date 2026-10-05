"""Regression tests for the opt-in v2.1.9 incumbent-preserving finalizer gate."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses while recording the public client calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one request and return its next scripted response."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
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
    """Build the explicit v2.1.9 profile without changing submission defaults."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.9",
        "arm_v2_mode": "selective",
        "arm_trust_policy": "positive_evidence",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV219IncumbentGuardTest(unittest.TestCase):
    """Keep a complete incumbent ahead of an unverified compact finalizer."""

    @staticmethod
    def _summary(result):
        """Return the final ARM summary entry from one solve result."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_truncated_complete_incumbent_uses_original_challenger(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未收束\nFinal answer: 7", "finish_reason": "length"},
                {"content": "Final answer: 7", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("challenger", summary["candidate_generation_b"]["backend"])
        self.assertTrue(summary["candidate_generation_b"]["incumbent_guard"])
        self.assertTrue(
            any(entry.get("stage") == "incumbent_preserving_finalizer_gate" for entry in result["trace"])
        )
        self.assertIn("Challenger", client.calls[1]["messages"][0]["content"])
        self.assertNotIn("收束器", client.calls[1]["messages"][0]["content"])

    def test_incomplete_primary_still_uses_bounded_finalizer(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未形成答案", "finish_reason": "length"},
                {"content": "Final answer: 42", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 40+2", {})

        summary = self._summary(result)
        self.assertEqual("42", result["final_response"])
        self.assertEqual("compact_finalizer", summary["candidate_generation_b"]["backend"])
        self.assertFalse(summary["candidate_generation_b"].get("incumbent_guard", False))
        self.assertLessEqual(client.calls[1]["max_tokens"], 2_048)

    def test_complete_non_truncated_primary_keeps_early_stop(self):
        client = ScriptedClient([{"content": "Final answer: 2", "finish_reason": "stop"}])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertTrue(summary["early_stop"])
        self.assertNotIn("candidate_generation_b", summary)


if __name__ == "__main__":
    unittest.main()
