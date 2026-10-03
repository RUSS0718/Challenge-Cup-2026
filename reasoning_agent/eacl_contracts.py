"""Small data contracts shared by the EACL control plane and its tests.

The module owns only immutable configuration and bounded per-question ledger
records.  It deliberately contains no model calls, parsing, or evaluator
logic so callers can exercise the state surface without network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

from reasoning_agent.answer_contract import AnswerType


METHOD_ID = "grh_eacl_v1"
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EACLConfig:
    """Bound one solve to a small, auditable candidate ladder."""

    max_model_calls: int = 3
    total_token_budget: int = 12_288
    route_a_max_tokens: int = 4_096
    route_b_max_tokens: int = 4_096
    recovery_max_tokens: int = 1_024
    finalizer_max_tokens: int = 512
    temperature: float = 0.6
    allow_thinking_on: bool = True
    allow_route_b_on_unknown: bool = True
    enable_off_finalizer: bool = False
    soft_deadline_seconds: float = 1_080.0
    hard_deadline_seconds: float = 1_200.0
    max_problem_chars: int = 12_000

    def __post_init__(self) -> None:
        """Reject impossible budgets before a model request is attempted."""

        if int(self.max_model_calls) < 1 or int(self.max_model_calls) > 3:
            raise ValueError("eacl_max_model_calls_must_be_between_1_and_3")
        if int(self.total_token_budget) < 1:
            raise ValueError("eacl_token_budget_must_be_positive")
        if any(int(value) < 1 for value in (
            self.route_a_max_tokens,
            self.route_b_max_tokens,
            self.recovery_max_tokens,
            self.finalizer_max_tokens,
        )):
            raise ValueError("eacl_stage_token_budgets_must_be_positive")
        if not math.isfinite(float(self.temperature)) or float(self.temperature) < 0:
            raise ValueError("eacl_temperature_must_be_nonnegative")
        if not math.isfinite(float(self.soft_deadline_seconds)) or self.soft_deadline_seconds <= 0:
            raise ValueError("eacl_soft_deadline_must_be_positive")
        if not math.isfinite(float(self.hard_deadline_seconds)) or self.hard_deadline_seconds <= 0:
            raise ValueError("eacl_hard_deadline_must_be_positive")
        if self.soft_deadline_seconds > self.hard_deadline_seconds:
            raise ValueError("eacl_soft_deadline_must_not_exceed_hard_deadline")


@dataclass
class CandidateRecord:
    """Keep one extracted candidate and its host-side evidence."""

    candidate_id: str
    route: str
    value: str
    canonical_value: str
    source: str
    answer_type: str
    complete: bool
    shape_valid: bool
    truncated: bool
    reasoning_mode: str
    raw_span_hash: str
    verification: str = UNKNOWN
    verification_reason: str = ""
    rejection_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return bounded diagnostics without retaining model responses."""

        return {
            "candidate_id": self.candidate_id,
            "route": self.route,
            "value": self.value[:256],
            "canonical_value": self.canonical_value[:256],
            "source": self.source,
            "answer_type": self.answer_type,
            "complete": self.complete,
            "shape_valid": self.shape_valid,
            "truncated": self.truncated,
            "reasoning_mode": self.reasoning_mode,
            "raw_span_hash": self.raw_span_hash,
            "verification": self.verification,
            "verification_reason": self.verification_reason[:240],
            "rejection_reason": self.rejection_reason[:240],
        }


@dataclass(frozen=True)
class VerificationResult:
    """Three-state deterministic verification result."""

    status: str
    reason: str


@dataclass(frozen=True)
class DecisionRecord:
    """Conservative selection outcome for one solve."""

    action: str
    selected_id: str | None
    selected_route: str | None
    verification: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe decision summary."""

        return {
            "action": self.action,
            "selected_id": self.selected_id,
            "selected_route": self.selected_route,
            "verification": self.verification,
            "reason": self.reason,
        }


@dataclass
class CandidateLedger:
    """Bounded per-question event ledger used by the control plane."""

    candidates: list[CandidateRecord] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(self, stage: str, **fields: Any) -> None:
        """Append a compact event with a stable method identifier."""

        self.events.append({"method": METHOD_ID, "stage": stage, **fields})

    def add_candidates(self, candidates: Iterable[CandidateRecord]) -> None:
        """Append candidate metadata while preserving route provenance."""

        self.candidates.extend(candidates)

    def as_trace(self, *, model_calls: int, requested_tokens: int) -> list[dict[str, Any]]:
        """Render bounded trace events suitable for the platform response."""

        return [
            *self.events,
            {
                "method": METHOD_ID,
                "stage": "candidate_ledger",
                "candidate_count": len(self.candidates),
                "candidates": [candidate.as_dict() for candidate in self.candidates[:6]],
                "model_calls": model_calls,
                "requested_tokens": requested_tokens,
            },
        ]


@dataclass(frozen=True)
class RoutePlan:
    """ARM route and request-local reasoning mode for one candidate call."""

    risk: str
    answer_type: AnswerType
    reasoning_mode: str
    reason: str


__all__ = [
    "CandidateLedger",
    "CandidateRecord",
    "DecisionRecord",
    "EACLConfig",
    "FAIL",
    "METHOD_ID",
    "PASS",
    "RoutePlan",
    "UNKNOWN",
    "VerificationResult",
]
