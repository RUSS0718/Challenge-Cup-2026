"""Tests for ARM lane integration and candidate-first stopping."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ModeAwareClient:
    """Script model replies while retaining each request's mode and budget."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit"):
        """Record the selected mode and return the next scripted answer."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_mode": reasoning_mode,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class ARMHarnessTest(unittest.TestCase):
    """Verify per-solve ARM policy without contacting an external model."""

    def test_stable_direct_candidate_stops_after_one_explicit_off_call(self):
        client = ModeAwareClient(["Final answer: 2"])
        harness = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(enable_arm_harness=True, enable_deep_lane=True),
        )

        result = harness.solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertEqual("off", client.calls[0]["reasoning_mode"])
        ledger = next(event for event in result["trace"] if event.get("stage") == "evidence_ledger")
        self.assertEqual("off", ledger["budget"]["records"][0]["reasoning_mode"])
        self.assertEqual("off", ledger["candidates"][0]["reasoning_mode"])

    def test_unresolved_contract_escalates_from_off_to_on(self):
        client = ModeAwareClient(["暂时没有唯一结果", "Final answer: {1,-1}"])
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
        self.assertEqual(["off", "on"], [call["reasoning_mode"] for call in client.calls])
        policy = next(event for event in result["trace"] if event.get("stage") == "arm_policy")
        self.assertEqual("adaptive", policy["lane"])
        escalation = next(event for event in result["trace"] if event.get("stage") == "arm_escalation")
        self.assertEqual("triggered", escalation["status"])
        self.assertEqual("no_extractable_candidate", escalation["reason"])


if __name__ == "__main__":
    unittest.main()
