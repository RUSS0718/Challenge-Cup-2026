"""Regression tests for v2.1.6 missing-candidate recovery."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses and retain prompts for route assertions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record a request and return the next response."""
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
    """Build an explicit v2.1.6 configuration without changing defaults."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.6",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV216MissingCandidateTest(unittest.TestCase):
    """Keep the recovery path independent and narrowly gated."""

    @staticmethod
    def _summary(result):
        """Return the bounded ARM summary from a solve result."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_missing_primary_forms_independent_candidate(self):
        client = ScriptedClient(
            [
                {"content": "推理尚未收束", "finish_reason": "length"},
                {"content": "Final answer: 2", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual("independent_missing_candidate_recovery", summary["candidate_generation_b"]["backend"])
        self.assertEqual("primary_missing", summary["second_sample_trigger_reason"])
        self.assertIn("答案形成器", client.calls[1]["messages"][0]["content"])
        self.assertNotIn("Primary 候选", client.calls[1]["messages"][0]["content"])

    def test_missing_primary_unknown_remains_fail_closed(self):
        client = ScriptedClient(
            [
                {"content": "推理尚未收束", "finish_reason": "length"},
                {"content": "Final answer: UNKNOWN", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("abstain", self._summary(result)["final_source"])

    def test_existing_primary_keeps_challenger_path(self):
        client = ScriptedClient(
            [
                {"content": "Final answer: 2", "finish_reason": "length"},
                {"content": "Final answer: 2", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        summary = self._summary(result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual("challenger", summary["candidate_generation_b"]["backend"])
        self.assertIn("Challenger", client.calls[1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
