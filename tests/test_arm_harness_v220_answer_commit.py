"""Regression tests for the opt-in v2.2 answer-commit contract."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Capture the first prompt and return deterministic model responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one public client call before returning its scripted response."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_mode": reasoning_mode,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.responses.pop(0)


class ARMV220AnswerCommitTest(unittest.TestCase):
    """Keep answer-first formation opt-in and preserve normal selection."""

    def test_first_call_requires_answer_commit_and_keeps_default_config_untouched(self):
        client = ScriptedClient(["Final answer: 2", "Final answer: 2"])
        harness = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(
                enable_arm_harness=True,
                arm_harness_version="v2.2",
                arm_v2_mode="selective",
                arm_trust_policy="positive_evidence",
                enable_deep_lane=True,
            ),
        )

        result = harness.solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertLessEqual(len(client.calls), 2)
        prompt = client.calls[0]["messages"][0]["content"]
        self.assertIn("第一行且只能第一行写：Final answer", prompt)
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("answer_commit_first_v1", summary["primary_prompt_variant"])


if __name__ == "__main__":
    unittest.main()
