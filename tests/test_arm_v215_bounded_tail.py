"""Regression tests for the opt-in bounded truncated-tail confirmation path."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return bounded scripted responses while recording prompt metadata."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one request and return the next scripted response."""
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
    """Build the explicit v2.1.5 test configuration without changing defaults."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.5",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV215BoundedTailTest(unittest.TestCase):
    """Verify confirmation is narrow, bounded, and fail-closed."""

    @staticmethod
    def _summary(result):
        """Return the ARM summary entry from one solve result."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_marked_truncated_candidate_uses_short_confirmation(self):
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
        self.assertEqual("bounded_tail_confirmation", summary["candidate_generation_b"]["backend"])
        self.assertEqual("consensus", summary["final_source"])
        self.assertEqual("answer_complete_truncated_tail", summary["primary_candidate"]["answer_complete_reason"])
        self.assertLessEqual(client.calls[1]["max_tokens"], 1024)

    def test_confirmation_conflict_keeps_truncated_incumbent(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未收束\nFinal answer: 7", "finish_reason": "length"},
                {"content": "Final answer: 8", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("7", result["final_response"])
        self.assertEqual("safe_candidate", summary["final_source"])
        self.assertTrue(summary["safe_fallback_used"])
        self.assertEqual("v2.1.4_no_replacement_evidence", summary["fallback_reason"])

    def test_unmarked_truncated_candidate_stays_on_challenger_path(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未收束\n7", "finish_reason": "length"},
                {"content": "Final answer: 7", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertNotEqual("bounded_tail_confirmation", summary["candidate_generation_b"]["backend"])
        self.assertIn("Challenger", client.calls[1]["messages"][0]["content"])

    def test_truncated_confirmation_is_not_positive_evidence(self):
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "length"},
            {"content": "Final answer: 7", "finish_reason": "length"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})
        summary = self._summary(result)
        self.assertEqual("7", result["final_response"])
        self.assertFalse(summary["agreement"])
        self.assertEqual("safe_candidate", summary["final_source"])

    def test_confirmation_unknown_or_timeout_keeps_primary(self):
        for response in ({"content": "Final answer: UNKNOWN", "finish_reason": "stop"}, TimeoutError()):
            with self.subTest(response=type(response).__name__):
                client = ScriptedClient([
                    {"content": "Final answer: 7", "finish_reason": "length"}, response,
                ])
                result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})
                self.assertEqual("7", result["final_response"])
                self.assertFalse(self._summary(result)["agreement"])
                self.assertEqual(2, len(client.calls))

    def test_confirmation_without_finish_metadata_is_not_positive_evidence(self):
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "length"}, "Final answer: 7",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})
        self.assertEqual("7", result["final_response"])
        self.assertFalse(self._summary(result)["agreement"])


if __name__ == "__main__":
    unittest.main()
