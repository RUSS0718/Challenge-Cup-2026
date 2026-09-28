"""Conservative ARM v2 trust decisions for structurally valid candidates."""

from __future__ import annotations

from typing import Any

from reasoning_agent.candidate_validation import validate_candidate_shape
from reasoning_agent.harness_contracts import (
    ANSWER_CHOICE,
    ANSWER_INTEGER,
    ANSWER_RATIONAL,
    REASONING_RISK_DIRECT,
    ROUTE_CONFIDENCE_HIGH,
)
from reasoning_agent.inference_policy import CandidateTrustDecision


class CandidateTrustPolicy:
    """Allow single-sample finalization only for a narrow low-risk contract."""

    def evaluate(
        self,
        *,
        contract: Any,
        candidate: Any,
        parsed: Any,
        call_result: Any,
    ) -> CandidateTrustDecision:
        """Classify trust separately from parser success and runtime health."""
        if getattr(call_result, "error_category", None):
            return CandidateTrustDecision(False, "low", True, "runtime_failure")

        valid, _reason = validate_candidate_shape(candidate, getattr(candidate, "answer_type", "unknown"))
        if not valid:
            return CandidateTrustDecision(False, "low", True, "structurally_invalid")
        if getattr(candidate, "answer_complete", True) is False:
            return CandidateTrustDecision(False, "low", True, "answer_incomplete")
        if bool(getattr(parsed, "truncated", False)):
            return CandidateTrustDecision(False, "low", True, "truncated")
        if getattr(call_result, "finish_reason", None) != "stop":
            return CandidateTrustDecision(False, "medium", True, "non_normal_completion")

        simple_direct = (
            getattr(contract, "reasoning_risk", None) == REASONING_RISK_DIRECT
            and getattr(contract, "route_confidence", None) == ROUTE_CONFIDENCE_HIGH
            and getattr(candidate, "answer_type", None)
            in {ANSWER_INTEGER, ANSWER_RATIONAL, ANSWER_CHOICE}
        )
        if simple_direct:
            return CandidateTrustDecision(
                True,
                "high",
                False,
                "direct_high_confidence_simple_shape",
            )
        reason = (
            "high_reasoning_risk_single_sample"
            if getattr(contract, "reasoning_risk", None) != REASONING_RISK_DIRECT
            else "low_route_confidence_single_sample"
        )
        return CandidateTrustDecision(False, "medium", True, reason)


__all__ = ["CandidateTrustPolicy"]
