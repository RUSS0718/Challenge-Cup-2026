"""State holder for the last structurally safe ARM candidate.

The holder deliberately knows only the host-side candidate contract.  It does
not claim that a candidate is mathematically correct; it preserves a usable
answer when an optional downstream operation fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reasoning_agent.harness_contracts import Candidate, _is_placeholder


_REJECTED_STATUSES = frozenset({"placeholder", "invalid", "empty", "truncated"})


@dataclass
class SafeCandidateState:
    """Remember one candidate that is safe to return at an interruption."""

    candidate: Candidate | None = None
    source: str | None = None
    confidence: str = "none"
    checkpoint_stage: str | None = None

    def update(
        self,
        candidate: Candidate | None,
        *,
        source: str | None = None,
        confidence: str | None = None,
        checkpoint_stage: str | None = None,
    ) -> bool:
        """Store only a non-empty candidate already marked structurally valid."""
        if not self._is_safe(candidate):
            return False
        self.candidate = candidate
        self.source = source or candidate.source
        self.confidence = confidence or candidate.trust_confidence or "unknown"
        self.checkpoint_stage = checkpoint_stage
        return True

    def clear(self) -> None:
        """Discard a candidate that a later deterministic audit refuted."""
        self.candidate = None
        self.source = None
        self.confidence = "none"
        self.checkpoint_stage = None

    def get(self) -> Candidate | None:
        """Return the current safe candidate, if one has been checkpointed."""
        return self.candidate

    @staticmethod
    def _is_safe(candidate: Candidate | None) -> bool:
        """Apply the structural, placeholder, and empty-value safe gate."""
        if candidate is None or candidate.structural_validity != "valid":
            return False
        if getattr(candidate, "answer_complete", True) is False:
            return False
        value = str(candidate.normalized_value or candidate.value or "").strip()
        if not value or _is_placeholder(value) or value.upper() == "TBD":
            return False
        if str(candidate.verification_status or "").casefold() in {"rejected", "skill_refuted", "refuted"}:
            return False
        status = str(candidate.extraction_status or "").casefold()
        return status not in _REJECTED_STATUSES and not bool(getattr(candidate, "truncated", False))


__all__ = ["SafeCandidateState"]
