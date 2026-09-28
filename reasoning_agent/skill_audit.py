"""Small, reviewer-only checks that can inspect an existing candidate.

This module never solves a problem and never constructs a replacement answer.
It returns a bounded status so the ARM state machine can decide whether to keep
or resample the candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from deterministic_math import solve_deterministic
from reasoning_agent.harness_contracts import value_equivalence


SkillAuditStatus = Literal["supported", "refuted", "unknown", "not_applicable"]
_STATUSES = frozenset({"supported", "refuted", "unknown", "not_applicable"})


@dataclass(frozen=True)
class SkillAuditResult:
    """Describe evidence about an existing candidate without replacing it."""

    status: SkillAuditStatus
    skill_id: str
    reason: str

    def __post_init__(self) -> None:
        """Reject malformed statuses and empty skill identifiers at the seam."""
        if self.status not in _STATUSES:
            raise ValueError("invalid_skill_audit_status")
        if not str(self.skill_id).strip():
            raise ValueError("skill_id_must_be_non_empty")


class SkillAuditor:
    """Audit existing host evidence with at most one cheap, bounded skill."""

    def audit(
        self,
        *,
        problem: str,
        contract: Any,
        candidate: Any,
    ) -> SkillAuditResult:
        """Return a status for an applicable check; never emit a new candidate."""
        skill_id = self._skill_id(problem, contract, candidate)
        if skill_id is None:
            return SkillAuditResult("not_applicable", "none", "no_cheap_skill")

        # Existing deterministic checks may be supplied by the parser or a
        # test double.  The auditor only interprets them; it does not derive a
        # value or call a model.
        for check in getattr(candidate, "checks", ()) or ():
            if not isinstance(check, dict) or check.get("source") != skill_id:
                continue
            status = str(check.get("claim_status", "")).casefold()
            if status == "supported":
                return SkillAuditResult("supported", skill_id, "existing_check_supported")
            if status == "refuted":
                return SkillAuditResult("refuted", skill_id, "existing_check_refuted")

        if skill_id == "exact-evaluation":
            evaluated = solve_deterministic(problem)
            if evaluated.get("status") == "supported" and isinstance(evaluated.get("answer"), str):
                candidate_value = str(getattr(candidate, "normalized_value", "") or getattr(candidate, "value", ""))
                relation = value_equivalence(candidate_value, evaluated["answer"])
                if relation == "EQUIVALENT":
                    return SkillAuditResult("supported", skill_id, "deterministic_exact_evaluation")
                return SkillAuditResult("refuted", skill_id, "deterministic_exact_evaluation_mismatch")

        return SkillAuditResult("unknown", skill_id, "cheap_check_not_decisive")

    @staticmethod
    def _skill_id(problem: str, contract: Any, candidate: Any) -> str | None:
        """Choose zero or one cheap audit from explicit lexical host signals."""
        contract_shape = contract.get("answer_shape", "") if isinstance(contract, Mapping) else getattr(contract, "answer_shape", "")
        answer_type = str(contract_shape or getattr(candidate, "answer_type", ""))
        if answer_type not in {
            "integer",
            "rational",
            "scalar",
            "exact_expression",
            "single_numeric",
        }:
            return None
        text = str(problem or "").casefold()
        markers = ("计算", "求值", "代入", "代回", "compute", "calculate", "evaluate", "substitution")
        return "exact-evaluation" if any(marker in text for marker in markers) else None


__all__ = ["SkillAuditResult", "SkillAuditStatus", "SkillAuditor"]
