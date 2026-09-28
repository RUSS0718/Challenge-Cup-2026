"""Host-side reasoning mode policy and bounded escalation decisions.

The module owns ARM lane selection only; model calls and candidate parsing
remain with the math harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from reasoning_agent.harness_contracts import (
    ANSWER_CHOICE,
    ANSWER_SCALAR,
    CANDIDATE_CONFLICT,
    CANDIDATE_PARSED,
    CANDIDATE_TRUNCATED,
    REASONING_RISK_DIRECT,
    ROUTE_CONFIDENCE_HIGH,
)


ReasoningMode = Literal["inherit", "off", "on"]
CandidateConfidence = Literal["low", "medium", "high"]
ARMLane = Literal["fast_off", "adaptive", "deep_on"]
ARM_DEFAULT_LANES = frozenset({"adaptive", "fast_off", "deep_on", "static"})


@dataclass(frozen=True)
class CallPolicy:
    """Per-request inference settings passed by the host scheduler."""

    stage: str
    reasoning_mode: ReasoningMode
    max_tokens: int
    temperature: float = 0.6


@dataclass(frozen=True)
class SolvePolicy:
    """Lane and hard budget selected for one solve."""

    lane: ARMLane
    initial_mode: ReasoningMode
    escalation_mode: ReasoningMode | None
    max_calls: int
    token_budget: int
    reason: str


@dataclass(frozen=True)
class CandidateTrustDecision:
    """Record trust separately from parseability and mathematical proof."""

    trusted: bool
    confidence: CandidateConfidence
    needs_second_sample: bool
    reason: str


@dataclass(frozen=True)
class ComputePolicy:
    """Bound the calls, tokens, and recovery actions available to one solve."""

    max_calls: int
    token_budget: int
    wall_time_budget: float
    allow_second_sample: bool
    allow_resolver: bool
    allow_thinking_on: bool

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.token_budget < 1 or self.wall_time_budget <= 0:
            raise ValueError("compute_policy_budgets_must_be_positive")


class ReasoningModePolicy:
    """Select a low-risk OFF lane or a bounded adaptive lane from host signals."""

    def __init__(
        self,
        *,
        allow_thinking_on: bool,
        default_lane: str = "adaptive",
        fast_max_calls: int = 2,
        adaptive_max_calls: int = 3,
        deep_max_calls: int = 3,
        fast_token_budget: int = 8192,
        adaptive_token_budget: int = 16384,
        deep_token_budget: int = 16384,
    ) -> None:
        """Freeze the explicit ON gate, default arm, and hard lane budgets."""
        if default_lane not in ARM_DEFAULT_LANES:
            raise ValueError("invalid_arm_default_lane")
        self.allow_thinking_on = bool(allow_thinking_on)
        self.default_lane = default_lane
        self._budgets = {
            "fast_off": (fast_max_calls, fast_token_budget),
            "adaptive": (adaptive_max_calls, adaptive_token_budget),
            "deep_on": (deep_max_calls, deep_token_budget),
        }
        if any(int(calls) < 1 or int(tokens) < 1 for calls, tokens in self._budgets.values()):
            raise ValueError("arm_budgets_must_be_positive")

    def plan(self, contract: Any, answer_type: str) -> SolvePolicy:
        """Choose the lane without adding a second problem classifier."""
        direct_easy = (
            contract.reasoning_risk == REASONING_RISK_DIRECT
            and contract.route_confidence == ROUTE_CONFIDENCE_HIGH
            and answer_type in {ANSWER_SCALAR, ANSWER_CHOICE}
        )
        if self.default_lane == "fast_off":
            lane: ARMLane = "fast_off"
            reason = "forced_off_baseline"
        elif self.default_lane == "deep_on":
            lane = "deep_on" if self.allow_thinking_on else "adaptive"
            reason = "forced_on_baseline" if self.allow_thinking_on else "thinking_on_disabled"
        elif direct_easy:
            lane = "fast_off"
            reason = "direct_high_confidence_answer"
        elif self.default_lane == "static" and self.allow_thinking_on:
            lane = "deep_on"
            reason = "static_high_risk_escalation"
        else:
            lane = "adaptive"
            reason = "thinking_on_disabled" if self.default_lane == "static" else "non_direct_contract"

        max_calls, token_budget = self._budgets[lane]
        if lane == "fast_off":
            initial_mode: ReasoningMode = "off"
            escalation_mode: ReasoningMode | None = "off"
        elif lane == "deep_on":
            initial_mode = "on"
            escalation_mode = None
        else:
            initial_mode = "off"
            escalation_mode = "on" if self.allow_thinking_on else "off"
        return SolvePolicy(
            lane=lane,
            initial_mode=initial_mode,
            escalation_mode=escalation_mode,
            max_calls=int(max_calls),
            token_budget=int(token_budget),
            reason=reason,
        )


def candidate_is_stable(parsed: Any, candidates: Sequence[Any]) -> bool:
    """Return the legacy v1 parseability predicate for compatibility."""
    status = getattr(parsed, "status", None)
    typed_complete = bool(getattr(parsed, "typed_complete", False))
    return (
        len(candidates) == 1
        and not bool(getattr(parsed, "truncated", False))
        and (status == CANDIDATE_PARSED or typed_complete)
    )


def candidate_is_parseable(parsed: Any, candidates: Sequence[Any]) -> bool:
    """Expose v2's parseability name without granting mathematical trust."""
    return candidate_is_stable(parsed, candidates)


def should_escalate(
    *,
    parsed: Any,
    candidates: Sequence[Any],
    call_result: Any,
    budget: Any,
) -> tuple[bool, str]:
    """Identify explicit unresolved states while respecting the remaining budget."""
    error = getattr(call_result, "error_category", None)
    if error:
        reason = "timeout" if error == "timeout" else "request_error"
    elif len(candidates) > 1 or getattr(parsed, "status", None) in {
        CANDIDATE_CONFLICT,
        "typed_conflict",
    }:
        reason = "candidate_conflict"
    elif (
        bool(getattr(parsed, "truncated", False))
        or getattr(parsed, "status", None) == CANDIDATE_TRUNCATED
        or getattr(parsed, "status", None) == "typed_incomplete"
    ):
        reason = "truncated_without_stable_candidate" if candidates else "no_extractable_candidate"
    elif not candidates:
        reason = "no_extractable_candidate"
    else:
        reason = "candidate_unresolved"

    if budget.calls_used >= budget.max_calls or budget.requested_tokens >= budget.total_tokens:
        return False, "budget_exhausted"
    return True, reason
