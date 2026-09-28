"""Acceptance tests for safe-candidate and solver-mode behavior."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses while recording request-local modes."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.default_state = {"thinking_mode": None, "timeout": 30}

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record the request-local controls without mutating defaults."""
        self.calls.append({"reasoning_mode": reasoning_mode, "timeout_seconds": timeout_seconds})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config(**overrides):
    """Build a v2.1 selective configuration for one test."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
        "arm_finalization_margin_seconds": 0,
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV21SafeCandidateTest(unittest.TestCase):
    """Verify downstream failures preserve the last usable candidate."""

    def test_second_sample_timeout_returns_candidate_a(self):
        client = ScriptedClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            TimeoutError("timeout"),
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求满足条件的所有值", {})
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("{1,2}", result["final_response"])
        self.assertTrue(summary["safe_fallback_used"])

    def test_resolver_unknown_returns_pre_resolver_candidate(self):
        client = ScriptedClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {3,4}", "finish_reason": "stop"},
            "UNKNOWN",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual(["off", "off", "off"], [call["reasoning_mode"] for call in client.calls])

    def test_on_changes_solver_calls_but_not_resolver(self):
        client = ScriptedClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {3,4}", "finish_reason": "stop"},
            "A",
        ])
        result = ConstraintFitOrchestrator(
            client, config=_config(arm_solver_reasoning_mode="on")
        ).solve("求所有可能的值", {})
        self.assertEqual(["on", "on", "off"], [call["reasoning_mode"] for call in client.calls])
        self.assertEqual("on", next(item for item in result["trace"] if item.get("stage") == "arm_v2_policy")["solver_reasoning_mode"])

    def test_no_safe_candidate_abstains(self):
        client = ScriptedClient(["UNKNOWN", TimeoutError("timeout")])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})
        self.assertEqual("UNKNOWN", result["final_response"])


if __name__ == "__main__":
    unittest.main()
