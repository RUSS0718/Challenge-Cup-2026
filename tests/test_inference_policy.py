"""Unit tests for ARM policy decisions that do not call a model."""

import unittest

from reasoning_agent.harness_contracts import (
    ANSWER_CHOICE,
    ANSWER_SCALAR,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    ProblemContract,
    REASONING_RISK_DEEP,
    REASONING_RISK_DIRECT,
    ROUTE_CONFIDENCE_HIGH,
    ROUTE_CONFIDENCE_LOW,
)
from reasoning_agent.inference_policy import ReasoningModePolicy


class ReasoningModePolicyTest(unittest.TestCase):
    """Keep route decisions deterministic and Thinking OFF unless permitted."""

    def test_direct_high_confidence_scalar_and_choice_use_fast_off(self):
        policy = ReasoningModePolicy(allow_thinking_on=True)
        contract = ProblemContract(
            ANSWER_SHAPE_SINGLE_NUMERIC,
            REASONING_RISK_DIRECT,
            ROUTE_CONFIDENCE_HIGH,
        )

        scalar = policy.plan(contract, ANSWER_SCALAR)
        choice = policy.plan(contract, ANSWER_CHOICE)

        self.assertEqual("fast_off", scalar.lane)
        self.assertEqual("off", scalar.initial_mode)
        self.assertEqual("fast_off", choice.lane)
        self.assertEqual(2, scalar.max_calls)
        self.assertEqual(8192, scalar.token_budget)

    def test_other_contracts_use_adaptive_off_first(self):
        disabled = ReasoningModePolicy(allow_thinking_on=False)
        enabled = ReasoningModePolicy(allow_thinking_on=True)
        contract = ProblemContract(
            ANSWER_SHAPE_SINGLE_NUMERIC,
            REASONING_RISK_DEEP,
            ROUTE_CONFIDENCE_LOW,
        )

        off_plan = disabled.plan(contract, ANSWER_SCALAR)
        on_plan = enabled.plan(contract, ANSWER_SCALAR)

        self.assertEqual("adaptive", off_plan.lane)
        self.assertEqual(("off", "off"), (off_plan.initial_mode, off_plan.escalation_mode))
        self.assertEqual(("off", "on"), (on_plan.initial_mode, on_plan.escalation_mode))
        self.assertEqual(3, on_plan.max_calls)
        self.assertEqual(16384, on_plan.token_budget)

    def test_static_lane_does_not_escalate_when_on_is_disabled(self):
        policy = ReasoningModePolicy(allow_thinking_on=False, default_lane="static")
        contract = ProblemContract(
            ANSWER_SHAPE_SINGLE_NUMERIC,
            REASONING_RISK_DEEP,
            ROUTE_CONFIDENCE_LOW,
        )

        plan = policy.plan(contract, ANSWER_SCALAR)

        self.assertEqual("adaptive", plan.lane)
        self.assertEqual("off", plan.escalation_mode)


if __name__ == "__main__":
    unittest.main()
