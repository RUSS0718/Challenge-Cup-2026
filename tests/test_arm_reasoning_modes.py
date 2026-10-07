"""Regression tests for explicit per-call ARM modes and lane budgets."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ModeAwareClient:
    """Capture mode-local calls and return a fixed sequence of model outputs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit"):
        """Capture request mode and token cap before returning the scripted response."""
        self.calls.append((reasoning_mode, max_tokens))
        return self.responses.pop(0)


class ARMReasoningModesTest(unittest.TestCase):
    """Keep OFF-only fallback and conflict handling inside the solve budget."""

    def test_disabled_on_uses_only_off_for_recovery(self):
        client = ModeAwareClient(["没有候选", "Final answer: {1,-1}"])
        harness = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(enable_arm_harness=True, enable_deep_lane=True),
        )

        result = harness.solve("求满足 x^2=1 的所有解", {})

        self.assertEqual("{1,-1}", result["final_response"])
        self.assertEqual(["off", "off"], [mode for mode, _tokens in client.calls])
        self.assertLessEqual(len(client.calls), 3)

    def test_conflicting_candidates_use_one_off_critic_within_budget(self):
        client = ModeAwareClient(
            [
                {"content": "Final answer: {1,-1}", "finish_reason": "length"},
                "Final answer: {1,-1,0}",
                "SELECT: A",
            ]
        )
        harness = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(
                enable_arm_harness=True,
                enable_deep_lane=True,
                arm_allow_thinking_on=True,
            ),
        )

        result = harness.solve("求满足 x^2=1 的所有解", {})

        self.assertEqual("{1,-1}", result["final_response"])
        self.assertEqual(["off", "on", "off"], [mode for mode, _tokens in client.calls])
        ledger = next(event for event in result["trace"] if event.get("stage") == "evidence_ledger")
        self.assertEqual(["off", "on", "off"], [row["reasoning_mode"] for row in ledger["budget"]["records"]])
        self.assertLessEqual(ledger["budget"]["requested_tokens"], 16384)
        self.assertEqual(
            {"off", "on"},
            {candidate["reasoning_mode"] for candidate in ledger["candidates"]},
        )


if __name__ == "__main__":
    unittest.main()
