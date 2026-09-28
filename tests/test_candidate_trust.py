"""Tests for the ARM v2 candidate trust gate."""

from types import SimpleNamespace
import unittest

from reasoning_agent.candidate_trust import CandidateTrustPolicy
from reasoning_agent.harness_contracts import (
    ANSWER_INTEGER,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    Candidate,
    ParsedResponse,
    ProblemContract,
    REASONING_RISK_DEEP,
    REASONING_RISK_DIRECT,
    ROUTE_CONFIDENCE_HIGH,
    ROUTE_CONFIDENCE_LOW,
)


def _candidate(value: str = "117") -> Candidate:
    """Build an integer candidate for trust-policy cases."""
    return Candidate(
        candidate_id="test",
        value=value,
        normalized_value=value,
        answer_type=ANSWER_INTEGER,
        source="test",
        extraction_status="parsed",
    )


def _parsed(*, truncated: bool = False) -> ParsedResponse:
    """Build a parser result with only the fields used by the policy."""
    return ParsedResponse([], "parsed", ANSWER_INTEGER, truncated, "test", "stop")


def _call(*, finish_reason: str = "stop", error_category: str | None = None):
    """Build a public-call-shaped result for the trust gate."""
    return SimpleNamespace(finish_reason=finish_reason, error_category=error_category)


class CandidateTrustPolicyTest(unittest.TestCase):
    """Keep single-sample early stop restricted to low-risk direct work."""

    def setUp(self):
        self.policy = CandidateTrustPolicy()
        self.direct = ProblemContract(ANSWER_SHAPE_SINGLE_NUMERIC, REASONING_RISK_DIRECT, ROUTE_CONFIDENCE_HIGH)

    def test_direct_high_confidence_integer_is_trusted(self):
        decision = self.policy.evaluate(
            contract=self.direct,
            candidate=_candidate(),
            parsed=_parsed(),
            call_result=_call(),
        )
        self.assertTrue(decision.trusted)
        self.assertEqual("high", decision.confidence)
        self.assertFalse(decision.needs_second_sample)

    def test_deep_contract_requires_a_second_sample(self):
        contract = ProblemContract(ANSWER_SHAPE_SINGLE_NUMERIC, REASONING_RISK_DEEP, ROUTE_CONFIDENCE_HIGH)
        decision = self.policy.evaluate(
            contract=contract,
            candidate=_candidate(),
            parsed=_parsed(),
            call_result=_call(),
        )
        self.assertFalse(decision.trusted)
        self.assertTrue(decision.needs_second_sample)
        self.assertEqual("high_reasoning_risk_single_sample", decision.reason)

    def test_truncated_candidate_is_not_trusted(self):
        decision = self.policy.evaluate(
            contract=self.direct,
            candidate=_candidate(),
            parsed=_parsed(truncated=True),
            call_result=_call(finish_reason="length"),
        )
        self.assertFalse(decision.trusted)
        self.assertEqual("truncated", decision.reason)

    def test_structural_invalidity_is_not_a_runtime_escalation(self):
        decision = self.policy.evaluate(
            contract=ProblemContract(ANSWER_SHAPE_SINGLE_NUMERIC, REASONING_RISK_DIRECT, ROUTE_CONFIDENCE_LOW),
            candidate=_candidate("有："),
            parsed=_parsed(),
            call_result=_call(),
        )
        self.assertFalse(decision.trusted)
        self.assertTrue(decision.needs_second_sample)
        self.assertEqual("structurally_invalid", decision.reason)


if __name__ == "__main__":
    unittest.main()
