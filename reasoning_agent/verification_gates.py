"""Deterministic, gold-free verification gates for candidate evidence."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re

from reasoning_agent.answer_contract import AnswerType, Candidate, TaskContract, Verification


@dataclass(frozen=True)
class VerificationResult:
    """One deterministic check result with a stable reason."""

    status: Verification
    check: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe result."""
        return {"status": self.status.value, "check": self.check, "reason": self.reason}


def verify_candidate(candidate: Candidate, contract: TaskContract) -> VerificationResult:
    """Run structural checks only; no gold answer or model self-report is used."""
    value = candidate.canonical_value or candidate.value
    if not candidate.accepted:
        return VerificationResult(Verification.FAIL, "structure", candidate.rejection_reason or "candidate_not_complete")
    if contract.answer_type == AnswerType.CHOICE:
        return VerificationResult(Verification.PASS if re.fullmatch(r"[A-Da-d][.)]?", value) else Verification.FAIL, "choice_shape", "single_choice" if re.fullmatch(r"[A-Da-d][.)]?", value) else "choice_not_closed")
    if contract.answer_type in {AnswerType.INTEGER, AnswerType.RATIONAL}:
        try:
            Fraction(value)
        except (ValueError, ZeroDivisionError):
            return VerificationResult(Verification.UNKNOWN, "numeric_shape", "expression_requires_symbolic_check")
        return VerificationResult(Verification.PASS, "numeric_shape", "bounded_rational")
    if contract.answer_type == AnswerType.SET:
        return VerificationResult(Verification.PASS if value.startswith("{") and value.endswith("}") else Verification.UNKNOWN, "set_shape", "closed_set" if value.startswith("{") and value.endswith("}") else "set_shape_unknown")
    return VerificationResult(Verification.UNKNOWN, "generic_shape", "no_deterministic_checker_registered")


__all__ = ["VerificationResult", "verify_candidate"]
