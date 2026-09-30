"""Deterministic verification seam for ARM-Harness v2.1 conflicts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


VerificationStatus = Literal["A", "B", "UNKNOWN", "NOT_APPLICABLE"]
_STATUSES = frozenset({"A", "B", "UNKNOWN", "NOT_APPLICABLE"})


@dataclass(frozen=True)
class VerificationResult:
    """Describe a bounded check between two existing candidates."""

    status: VerificationStatus
    candidate_id: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        """Reject unsupported decisions before they reach the resolver seam."""
        if self.status not in _STATUSES:
            raise ValueError("invalid_verification_status")
        if self.status in {"A", "B"} and not str(self.candidate_id or "").strip():
            raise ValueError("selected_verification_requires_candidate_id")


class DeterministicVerifier:
    """Provide the default no-op verifier without changing ARM behavior."""

    def verify(self, candidate_a: Any, candidate_b: Any, problem: str) -> VerificationResult:
        """Return ``NOT_APPLICABLE`` until a concrete check is configured."""
        del candidate_a, candidate_b, problem
        return VerificationResult("NOT_APPLICABLE", None, "no_deterministic_check")


__all__ = ["DeterministicVerifier", "VerificationResult", "VerificationStatus"]
