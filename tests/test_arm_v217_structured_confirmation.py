"""Regression tests for the opt-in v2.1.7 incumbent-only confirmation."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses while retaining the request prompts."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one public-contract call and return its scripted response."""
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
    """Build the explicit v2.1.7 profile without changing submission defaults."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.7",
        "arm_v2_mode": "selective",
        "arm_trust_policy": "positive_evidence",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV217StructuredConfirmationTest(unittest.TestCase):
    """Keep confirmation bounded and reject any attempted replacement value."""

    @staticmethod
    def _summary(result):
        """Return the final ARM summary entry from one solve result."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_pass_confirms_the_incumbent_and_uses_short_budget(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未收束\nFinal answer: 7", "finish_reason": "length"},
                {
                    "content": '{"status":"PASS","confirmed_value":"7","checked_issue":"value","check_result":"ok"}',
                    "finish_reason": "stop",
                },
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("structured_challenger_confirmation", summary["candidate_generation_b"]["backend"])
        self.assertTrue(summary["agreement"])
        self.assertEqual("consensus", summary["final_source"])
        self.assertLessEqual(client.calls[1]["max_tokens"], 1024)
        self.assertIn("JSON", client.calls[1]["messages"][0]["content"])

    def test_pass_with_new_value_keeps_the_incumbent(self):
        client = ScriptedClient(
            [
                {"content": "推导尚未收束\nFinal answer: 7", "finish_reason": "length"},
                {
                    "content": '{"status":"PASS","confirmed_value":"8","checked_issue":"value","check_result":"ok"}',
                    "finish_reason": "stop",
                },
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("7", result["final_response"])
        self.assertFalse(summary["agreement"])
        self.assertEqual("safe_candidate", summary["final_source"])
        self.assertTrue(summary["safe_fallback_used"])

    def test_marker_or_unknown_response_cannot_create_a_candidate(self):
        for confirmation in (
            {"content": "Final answer: 7", "finish_reason": "stop"},
            {"content": '{"status":"UNKNOWN","confirmed_value":"7"}', "finish_reason": "stop"},
        ):
            with self.subTest(confirmation=confirmation["content"]):
                client = ScriptedClient([
                    {"content": "推导尚未收束\nFinal answer: 7", "finish_reason": "length"},
                    confirmation,
                ])
                result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})
                summary = self._summary(result)
                self.assertEqual("7", result["final_response"])
                self.assertFalse(summary["agreement"])
                self.assertEqual("safe_candidate", summary["final_source"])


if __name__ == "__main__":
    unittest.main()
