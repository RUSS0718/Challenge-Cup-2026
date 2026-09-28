"""Support seam for ARM-Harness v2.1 state preservation and optional audits."""

from __future__ import annotations

from typing import Any

from reasoning_agent.harness_contracts import Candidate
from reasoning_agent.safe_candidate import SafeCandidateState
from reasoning_agent.skill_audit import SkillAuditResult


class ARMV21StateSupport:
    """Provide deadline, safe-candidate, and reviewer-only helper methods."""

    def remaining_wall_seconds(self) -> float:
        """Return the solve-local wall-clock budget still available."""
        elapsed = self.harness.clock() - self.harness._solve_started
        return max(0.0, float(self.harness.config.max_wall_seconds) - elapsed)

    def should_finalize_now(self) -> bool:
        """Stop optional work once only the finalization margin remains."""
        margin = float(getattr(self.harness.config, "arm_finalization_margin_seconds", 15.0))
        return self.remaining_wall_seconds() <= margin

    @staticmethod
    def _checkpoint(
        candidate: Candidate | None,
        parsed: Any,
        safe_state: SafeCandidateState,
        stage: str,
    ) -> bool:
        """Checkpoint a complete, structurally valid candidate before risky work."""
        if candidate is None or bool(getattr(parsed, "truncated", False)):
            return False
        return safe_state.update(
            candidate,
            source={"candidate_a": "candidate_a", "candidate_b": "candidate_b"}.get(stage, candidate.source),
            confidence=candidate.trust_confidence,
            checkpoint_stage=stage,
        )

    def _maybe_audit_skill(
        self,
        problem: str,
        route: Any,
        candidate: Candidate | None,
        decision: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> SkillAuditResult | None:
        """Run at most one cheap audit for a valid, medium-trust candidate."""
        config = self.harness.config
        if (
            candidate is None
            or candidate.structural_validity != "valid"
            or decision is None
            or not bool(getattr(config, "arm_enable_skill_audit", False))
            or int(getattr(config, "arm_max_skill_audits", 0)) <= 0
            or decision.confidence != "medium"
            or self.should_finalize_now()
        ):
            return None
        try:
            result = self.skill_auditor.audit(
                problem=problem,
                contract=route.contract,
                candidate=candidate,
            )
            if not isinstance(result, SkillAuditResult):
                result = SkillAuditResult(
                    str(getattr(result, "status", "unknown")),
                    str(getattr(result, "skill_id", "unknown")),
                    str(getattr(result, "reason", "invalid_audit_result")),
                )
        except BaseException as exc:
            result = SkillAuditResult("unknown", "unknown", f"audit_error:{type(exc).__name__}")
        summary["skill_triggered"] = True
        summary["skill_status"] = result.status
        trace.append(
            {
                "method": "arm_harness_v2",
                "stage": "skill_audit",
                "skill_id": result.skill_id,
                "status": result.status,
                "reason": result.reason[:240],
            }
        )
        return result

    @staticmethod
    def _best_candidate(primary: Candidate, secondary: Candidate) -> Candidate:
        """Prefer higher trust and keep primary on ties for deterministic fallback."""
        rank = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        return secondary if rank.get(secondary.trust_confidence, 0) > rank.get(primary.trust_confidence, 0) else primary

    def _return_safe_or_abstain(
        self,
        trace: list[dict[str, Any]],
        route_data: dict[str, Any],
        summary: dict[str, Any],
        safe_state: SafeCandidateState,
        candidates: list[Candidate],
        reason: str,
    ) -> dict[str, Any]:
        """Return the checkpointed candidate after optional work fails."""
        safe = safe_state.get()
        if safe is not None:
            summary["safe_fallback_used"] = True
            summary["final_source"] = "safe_candidate"
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "safe_candidate_fallback",
                    "reason": reason,
                    "source": safe_state.source,
                }
            )
            trace.append(summary)
            return self.harness._select(
                trace,
                route_data,
                safe,
                candidates or [safe],
                "arm_v2_safe_candidate_fallback",
            )
        summary["final_source"] = "abstain"
        trace.append(summary)
        return self.harness._abstain(trace, route_data, reason)
