"""Acceptance tests for ARM-Harness v2.1.3 correctness-first policies."""

import unittest

from reasoning_agent.arm_solver_backend import choose_solver_backend
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return scripted responses while recording request modes and prompts."""

    def __init__(self, responses):
        """Initialize the response queue and call record."""
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record public controls and return the next response envelope."""
        self.calls.append(
            {
                "messages": messages,
                "reasoning_mode": reasoning_mode,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config(**overrides):
    """Build an explicit v2.1.3 local experiment configuration."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2.1.3",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_solver_reasoning_mode": "off",
        "arm_trust_policy": "positive_evidence",
        "arm_finalization_margin_seconds": 0,
        "arm_off_recovery_max_tokens": 4096,
    }
    values.update(overrides)
    return HarnessConfig(**values)


def _summary(result):
    """Return the bounded ARM summary from a solve result."""
    return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")


class ARMV213Test(unittest.TestCase):
    """Verify positive evidence, backend attribution, and recovery behavior."""

    def test_complex_candidate_requires_positive_evidence(self):
        """A complete deep candidate cannot early-stop on format alone."""
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "stop"},
            {"content": "Final answer: 7", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(),
        ).solve("计算一个复杂的函数极限", {})
        summary = _summary(result)
        self.assertEqual(2, len(client.calls))
        self.assertFalse(summary["trust_decision"]["trusted"])
        self.assertEqual("positive_evidence_required", summary["trust_decision"]["reason"])
        self.assertEqual("structured_solver", summary["candidate_generation"]["backend"])
        self.assertNotIn("7", client.calls[1]["messages"][0]["content"])

    def test_backend_policy_separates_direct_and_structured_routes(self):
        """Keep backend choice deterministic and independent from candidate text."""
        direct = type(
            "Route",
            (),
            {
                "answer_type": "scalar",
                "contract": type(
                    "Contract",
                    (),
                    {"reasoning_risk": "direct", "route_confidence": "high"},
                )(),
            },
        )()
        deep = type(
            "Route",
            (),
            {
                "answer_type": "scalar",
                "contract": type(
                    "Contract",
                    (),
                    {"reasoning_risk": "deep", "route_confidence": "high"},
                )(),
            },
        )()
        self.assertEqual("direct_solver", choose_solver_backend(direct, reasoning_mode="off").backend)
        self.assertEqual("structured_solver", choose_solver_backend(deep, reasoning_mode="off").backend)

    def test_direct_simple_candidate_can_early_stop(self):
        """A high-confidence direct integer retains the one-call fast path."""
        client = ScriptedClient([
            {"content": "Final answer: 2", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})
        summary = _summary(result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertTrue(summary["trust_decision"]["trusted"])
        self.assertEqual(["direct_simple_contract"], summary["trust_decision"]["positive_evidence"])

    def test_forced_ab_runs_two_candidates_without_resolver(self):
        """Forced A/B diagnostic spends two blind candidate calls and no resolver."""
        client = ScriptedClient([
            {"content": "Final answer: 2", "finish_reason": "stop"},
            {"content": "Final answer: 3", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_force_ab_diagnostic=True),
        ).solve("计算 1+1", {})
        summary = _summary(result)
        self.assertTrue(summary["forced_ab_diagnostic"])
        self.assertEqual(2, len(client.calls))
        self.assertFalse(summary["resolver_triggered"])
        self.assertEqual("2", summary["candidate_a"]["value"])
        self.assertEqual("3", summary["candidate_b"]["value"])

    def test_on_missing_candidate_uses_independent_off_recovery(self):
        """ON without usable work uses an independent 4096-token OFF recovery."""
        client = ScriptedClient([
            "无法完成",
            {"content": "Final answer: 9", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_solver_reasoning_mode="on"),
        ).solve("求一个复杂的函数极限", {})
        summary = _summary(result)
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        self.assertEqual("9", result["final_response"])
        self.assertEqual(["on", "off"], [call["reasoning_mode"] for call in client.calls])
        self.assertEqual(4096, client.calls[1]["max_tokens"])
        self.assertEqual("off_recovery", summary["on_recovery_action"])
        self.assertEqual("arm_v2_off_recovery", ledger["calls"][1]["stage"])

    def test_on_visible_incomplete_work_uses_continuation(self):
        """ON partial work uses continuation before independent recovery."""
        client = ScriptedClient([
            {"content": "Final answer: x_s", "finish_reason": "stop"},
            {"content": "Final answer: 9", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_solver_reasoning_mode="on"),
        ).solve("求一个数", {})
        summary = _summary(result)
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        self.assertEqual("continuation", summary["on_recovery_action"])
        self.assertEqual("arm_v2_on_continuation", ledger["calls"][1]["stage"])
        self.assertEqual("on", client.calls[1]["reasoning_mode"])


if __name__ == "__main__":
    unittest.main()
