"""Small backend-selection policy for ARM v2.1.3 experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SolverBackendPlan:
    """Describe which bounded solver lane should generate one candidate."""

    backend: str
    reasoning_mode: str
    token_stage: str
    positive_evidence_required: bool


def choose_solver_backend(
    route: Any,
    *,
    reasoning_mode: str,
    skill_id: str | None = None,
    secondary: bool = False,
) -> SolverBackendPlan:
    """Choose direct, structured, or skill-guided generation from route facts."""
    contract = getattr(route, "contract", route)
    risk = str(getattr(contract, "reasoning_risk", ""))
    confidence = str(getattr(contract, "route_confidence", ""))
    answer_type = str(getattr(route, "answer_type", ""))
    direct = (
        not secondary
        and risk == "direct"
        and confidence == "high"
        and answer_type in {"scalar", "integer", "rational", "choice"}
    )
    if skill_id:
        return SolverBackendPlan("skill_guided_solver", reasoning_mode, "attempt_a", True)
    if direct:
        return SolverBackendPlan("direct_solver", reasoning_mode, "attempt_a", False)
    return SolverBackendPlan(
        "structured_solver",
        reasoning_mode,
        "deep_primary" if secondary else "attempt_a",
        True,
    )


__all__ = ["SolverBackendPlan", "choose_solver_backend"]
