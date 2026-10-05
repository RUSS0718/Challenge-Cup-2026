"""Regression tests for the opt-in v2.3 primary-tail continuation."""

import json
import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Capture public calls and return deterministic response envelopes."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record one request before returning its scripted response."""
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


def _config() -> HarnessConfig:
    """Build a positive-evidence v2.3 configuration for focused tests."""
    return HarnessConfig(
        enable_arm_harness=True,
        arm_harness_version="v2.3",
        arm_v2_mode="selective",
        arm_trust_policy="positive_evidence",
        enable_deep_lane=True,
    )


class ARMV223ContinuationTest(unittest.TestCase):
    """Check continuation activation and the complete-incumbent guard."""

    def test_partial_primary_uses_same_tail_for_one_bounded_continuation(self):
        partial = "先完成必要计算，但输出在结论前结束；中间推导如下：" + "x" * 120
        client = ScriptedClient(
            [
                {"content": partial, "finish_reason": "length"},
                {"content": "Final answer: 2", "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual(2, len(client.calls))
        continuation_prompt = client.calls[1]["messages"][0]["content"]
        self.assertIn("续写", continuation_prompt)
        self.assertIn(partial[-80:], continuation_prompt)
        trace_text = json.dumps(result["trace"], ensure_ascii=False)
        self.assertNotIn(partial, trace_text)
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("primary_tail_continuation", summary["candidate_generation_b"]["backend"])
        self.assertEqual("arm_v223_primary_continuation", summary["candidate_generation_b"]["stage"])

    def test_complete_primary_keeps_cfr_challenger_path(self):
        client = ScriptedClient(
            [
                {"content": "Final answer: 2", "finish_reason": "stop"},
                {"content": '{"verdict":"NO_OBJECTION","coverage":"candidate_value_equivalence"}\nFinal answer: 2', "finish_reason": "stop"},
            ]
        )
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "请计算 1+1，并简要说明计算过程。",
            {},
        )

        self.assertEqual("2", result["final_response"])
        self.assertEqual(2, len(client.calls))
        challenger_prompt = client.calls[1]["messages"][0]["content"]
        self.assertIn("Challenger", challenger_prompt)
        self.assertNotIn("续写器", challenger_prompt)


if __name__ == "__main__":
    unittest.main()
