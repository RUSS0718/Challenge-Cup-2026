"""Default-off pre-solve skill guidance seam for ARM-Harness v2.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillRouteDecision:
    """Describe zero or one skill route without containing an answer."""

    skill_id: str | None
    confidence: float
    reason: str

    def __post_init__(self) -> None:
        """Keep route confidence bounded and allow an explicit no-skill result."""
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("skill_confidence_out_of_range")
        if self.skill_id is not None and not str(self.skill_id).strip():
            raise ValueError("skill_id_must_be_non_empty")


class SkillRouter:
    """Return no route until an experiment injects a concrete router."""

    def route(self, problem: str, contract: Any) -> SkillRouteDecision:
        """Choose no skill by default; the seam never guesses an answer."""
        del problem, contract
        return SkillRouteDecision(None, 0.0, "skill_guidance_disabled")

    def guidance(self, decision: SkillRouteDecision) -> str:
        """Render bounded method guidance for an explicitly selected route."""
        del decision
        return ""


__all__ = ["SkillRouteDecision", "SkillRouter"]
