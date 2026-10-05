"""Regression tests for the route-gated v2.4 primary prompt."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return deterministic responses while exposing request prompts."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record a request and return the next scripted response."""
        self.calls.append(messages[0]["content"])
        return self.responses.pop(0)


def _config() -> HarnessConfig:
    """Build a bounded v2.4 configuration for prompt-routing tests."""
    return HarnessConfig(
        enable_arm_harness=True,
        arm_harness_version="v2.4",
        arm_v2_mode="selective",
        arm_trust_policy="positive_evidence",
        enable_deep_lane=True,
    )


class ARMV224RiskGateTest(unittest.TestCase):
    """Ensure only risky routes receive the answer reservation prompt."""

    def test_direct_high_confidence_preserves_v21_prompt(self):
        client = ScriptedClient(["Final answer: 2", "Final answer: 2"])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertNotIn("第一行且只能第一行写", client.calls[0])
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("v21_preserved", summary["primary_prompt_variant"])
        gate = next(item for item in result["trace"] if item.get("stage") == "risk_gated_answer_commit")
        self.assertEqual("bypassed", gate["status"])

    def test_deep_route_activates_answer_reservation(self):
        client = ScriptedClient(["Final answer: {-2,2}", "Final answer: {-2,2}"])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求所有实数 x，使 x^2=4，并给出解集。",
            {},
        )

        self.assertTrue(result["final_response"])
        self.assertIn("第一行且只能第一行写", client.calls[0])
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("risk_gated_answer_commit_v1", summary["primary_prompt_variant"])
        self.assertTrue(summary["risk_gate"]["active"])


if __name__ == "__main__":
    unittest.main()
