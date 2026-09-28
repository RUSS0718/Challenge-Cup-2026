"""Integration tests for the ARM-Harness v2 local experiment path."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ModeAwareClient:
    """Return scripted envelopes while recording request-local controls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record mode and timeout before returning the next response."""
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
    """Build an isolated v2 harness configuration for a test case."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMHarnessV2Test(unittest.TestCase):
    """Verify selective trust, consensus, conflict resolution, and salvage."""

    @staticmethod
    def _ledger(result):
        """Return the solve-local evidence ledger from a result trace."""
        return next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")

    @staticmethod
    def _summary(result):
        """Return the ARM v2 summary event from a result trace."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_trusted_direct_candidate_stops_after_one_call(self):
        client = ModeAwareClient([
            {"content": "Final answer: 2", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertEqual("off", client.calls[0]["reasoning_mode"])
        candidate = self._ledger(result)["candidates"][0]
        self.assertEqual("valid", candidate["structural_validity"])
        self.assertEqual("high", candidate["trust_confidence"])
        self.assertTrue(self._summary(result)["early_stop"])

    def test_high_risk_candidate_gets_one_blind_second_sample(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,-1}", "finish_reason": "stop"},
            {"content": "Final answer: {-1,1}", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求满足 x^2=1 的所有解", {})

        self.assertEqual("{-1,1}", result["final_response"])
        self.assertEqual(["off", "off"], [call["reasoning_mode"] for call in client.calls])
        self.assertTrue(self._summary(result)["agreement"])
        self.assertTrue(self._summary(result)["second_sample_triggered"])

    def test_conflict_uses_a_b_only_resolver(self):
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": "Final answer: {118,120}", "finish_reason": "stop"},
            "A",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})

        self.assertEqual("{117,119}", result["final_response"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual("off", client.calls[2]["reasoning_mode"])
        self.assertTrue(self._summary(result)["resolver_triggered"])
        self.assertTrue(self._summary(result)["conflict"])
        self.assertEqual("A", self._summary(result)["resolver_decision"])

    def test_timeout_uses_compact_salvage_without_entering_trust_on_failure(self):
        client = ModeAwareClient([
            TimeoutError("provider timeout"),
            {"content": "Final answer: 2", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(
                arm_v2_mode="salvage",
                arm_timeout_recovery_mode="compact_salvage",
                arm_primary_timeout_seconds=30,
            ),
        ).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual([30, 15], [call["timeout_seconds"] for call in client.calls])
        self.assertEqual("compact_salvage", self._summary(result)["runtime_recovery_action"])

    def test_resolver_cannot_create_a_third_candidate(self):
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": "Final answer: {118,120}", "finish_reason": "stop"},
            "C",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})

        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual(2, len(self._ledger(result)["candidates"]))
        self.assertEqual("UNKNOWN", self._summary(result)["resolver_decision"])


if __name__ == "__main__":
    unittest.main()
