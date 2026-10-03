"""Fail-closed classification and recovery policy for invalid answers.

This module decides whether a persisted response is eligible for host-side
replay.  It never consults gold answers and never creates a candidate when the
original artifact contains no answer evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from reasoning_agent.answer_contract import Candidate


class FailureClass(str, Enum):
    """Auditable invalid causes from the GRH v1.3 plan."""

    R1 = "R1_reasoning_failure"
    R2 = "R2_decision_failure"
    R3 = "R3_finalization_failure"
    R4 = "R4_parser_contract_failure"
    R5 = "R5_evaluator_boundary"
    R6 = "R6_timeout_truncation_health"
    UNKNOWN = "UNKNOWN"


class SalvageTier(str, Enum):
    """Ordered recovery tiers; S6 is explicit abstention."""

    S1 = "S1_surface_parser"
    S2 = "S2_truncated_closed_candidate"
    S3 = "S3_candidate_conflict"
    S4 = "S4_serialization_only"
    S5 = "S5_health_with_incumbent"
    S6 = "S6_no_forced_rescue"


class RecoveryAction(str, Enum):
    """Host actions permitted after classification."""

    SERIALIZE = "serialize"
    SAFE_INCUMBENT = "safe_incumbent"
    FINALIZER = "off_finalizer"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryDecision:
    """Record a deterministic, auditable salvage decision."""

    failure_class: FailureClass
    salvage_tier: SalvageTier
    action: RecoveryAction
    evidence_source: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        """Return the decision without exposing raw response content."""
        return {"failure_class": self.failure_class.value, "salvage_tier": self.salvage_tier.value, "action": self.action.value, "evidence_source": self.evidence_source, "reason": self.reason}


def _trace_has(row: dict[str, Any], needle: str) -> bool:
    """Search compact trace stages for one diagnostic token."""
    def visit(value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).casefold()
                if key_text == needle.casefold() and item is True:
                    return True
                if key_text in {"finish_reason", "status", "reason", "error_category", "runtime_recovery_action"} and needle.casefold() in str(item).casefold():
                    return True
                if visit(item):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(visit(item) for item in value)
        return False

    return visit(row.get("trace", []))


def classify_failure(row: dict[str, Any], candidate: Candidate | None = None) -> tuple[FailureClass, SalvageTier]:
    """Classify an invalid row from runtime evidence, without evaluator data."""
    finish_reasons = row.get("finish_reasons") or ()
    length_finish = row.get("finish_reason") == "length" or "length" in finish_reasons
    if row.get("timeout") or row.get("model_error") or length_finish or _trace_has(row, "timeout"):
        if candidate and candidate.accepted:
            return FailureClass.R6, SalvageTier.S5
        return FailureClass.R6, SalvageTier.S6
    if row.get("candidate_count", 0) and candidate and candidate.accepted:
        if _trace_has(row, "conflict"):
            return FailureClass.R2, SalvageTier.S3
        if row.get("final_response") in {"", "UNKNOWN"} or _trace_has(row, "final"):
            return FailureClass.R3, SalvageTier.S4
        return FailureClass.R4, SalvageTier.S1
    if row.get("candidate_count", 0):
        return FailureClass.R4, SalvageTier.S1
    if row.get("invalid") or row.get("outcome") == "invalid":
        return FailureClass.R1, SalvageTier.S6
    return FailureClass.UNKNOWN, SalvageTier.S6


def decide_recovery(row: dict[str, Any], candidate: Candidate | None = None) -> RecoveryDecision:
    """Select the only permitted host action for a classified artifact."""
    failure, tier = classify_failure(row, candidate)
    evidence = candidate.source if candidate and candidate.accepted else "none"
    if tier == SalvageTier.S1 and candidate and candidate.accepted:
        return RecoveryDecision(failure, tier, RecoveryAction.SERIALIZE, evidence, "closed_candidate_surface_replay")
    if tier == SalvageTier.S2 and candidate and candidate.accepted:
        return RecoveryDecision(failure, tier, RecoveryAction.SAFE_INCUMBENT, evidence, "closed_candidate_before_truncation")
    if tier == SalvageTier.S4 and candidate and candidate.accepted:
        return RecoveryDecision(failure, tier, RecoveryAction.FINALIZER, evidence, "format_only_candidate_repair")
    if tier == SalvageTier.S5 and candidate and candidate.accepted:
        return RecoveryDecision(failure, tier, RecoveryAction.SAFE_INCUMBENT, evidence, "health_failure_preserves_incumbent")
    return RecoveryDecision(failure, tier, RecoveryAction.UNKNOWN, evidence, "no_closed_candidate_no_forced_rescue")


def transition(old_verdict: str, new_verdict: str) -> str:
    """Return the stable paired transition label used by reports."""
    return f"{old_verdict or 'unknown'} → {new_verdict or 'unknown'}"


__all__ = ["FailureClass", "RecoveryAction", "RecoveryDecision", "SalvageTier", "classify_failure", "decide_recovery", "transition"]
