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
    """Classify whether one complete candidate needs another model sample."""

    def __init__(self, policy: str = "legacy") -> None:
        """Select the compatibility gate or v2.1.2 evidence-triggered gate."""
        if policy not in {"legacy", "evidence", "positive_evidence"}:
            raise ValueError("invalid_candidate_trust_policy")
        self.policy = policy

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
        if self.policy == "positive_evidence":
            verification_status = str(getattr(candidate, "verification_status", "")).casefold()
            if verification_status in {"deterministic_verified", "skill_supported", "consensus_supported"}:
                return CandidateTrustDecision(
                    True,
                    "high",
                    False,
                    "positive_verification_evidence",
                    (verification_status,),
                )
            if simple_direct:
                return CandidateTrustDecision(
                    True,
                    "high",
                    False,
                    "direct_simple_positive_evidence",
                    ("direct_simple_contract",),
                )
            if verification_status in {"rejected", "refuted", "skill_refuted"}:
                return CandidateTrustDecision(
                    False,
                    "low",
                    True,
                    "negative_verification_evidence",
                )
            return CandidateTrustDecision(
                False,
                "medium",
                True,
                "positive_evidence_required",
            )
        if self.policy == "evidence":
            verification_status = str(getattr(candidate, "verification_status", "")).casefold()
            if verification_status in {"rejected", "refuted", "skill_refuted"}:
                return CandidateTrustDecision(False, "low", True, "negative_verification_evidence")
            return CandidateTrustDecision(
                True,
                "high" if simple_direct else "medium",
                False,
                "complete_without_negative_evidence",
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
