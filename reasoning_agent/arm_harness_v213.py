"""ARM-Harness v2.1.3 correctness-first orchestration extensions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

from reasoning_agent.arm_harness_v2 import AdaptiveReliabilityHarness
from reasoning_agent.candidate_trust import CandidateTrustDecision
from reasoning_agent.harness_contracts import Candidate
from reasoning_agent.inference_policy import ReasoningMode
from reasoning_agent.math_harness import (
    DEEP_CONTINUATION_PROMPT,
    DEEP_PRIMARY_PROMPT,
    DEEP_REVIEW_PROMPT,
)
from reasoning_agent.arm_solver_backend import choose_solver_backend


ARM_V213_OFF_RECOVERY_PROMPT = """你是独立的数学恢复求解器。原先的 ON 求解没有形成可用终答。
请从原题重新求解，保留必要的关键计算，直接形成唯一完整结论。
不要参考或复述此前失败过程，不要输出多个候选。
最后单独一行且必须使用：Final answer: <完整答案>"""


class AdaptiveReliabilityHarnessV213(AdaptiveReliabilityHarness):
    """Run v2.1.3 positive-evidence, backend, and recovery policies."""

    def __init__(self, harness: Any) -> None:
        """Bind v2.1.3 diagnostics without changing the public solve contract."""
        super().__init__(harness)
        self._forced_ab_active = bool(getattr(harness.config, "arm_force_ab_diagnostic", False))
        self._decisions: list[CandidateTrustDecision | None] = []

    def solve(self, problem: str, route: Any, prefix_trace: list[dict[str, Any]]) -> dict[str, Any]:
        """Run the inherited state machine with optional forced A/B accounting."""
        original_policy = self.compute_policy
        if self._forced_ab_active:
            self.compute_policy = replace(
                self.compute_policy,
                max_calls=min(2, self.compute_policy.max_calls),
                allow_resolver=False,
            )
        self._decisions = []
        try:
            result = super().solve(problem, route, prefix_trace)
        finally:
            self.compute_policy = original_policy
        summary = next(
            (item for item in result.get("trace", []) if item.get("stage") == "arm_v2_summary"),
            None,
        )
        if isinstance(summary, dict):
            summary["forced_ab_diagnostic"] = self._forced_ab_active
            summary["primary_math_status"] = "unknown"
            summary["false_trusted_primary"] = None
            summary["recovery_transition"] = "not_applicable"
            summary["trust_decision"] = self._decision_summary(
                self._decisions[0] if self._decisions else None
            )
        return result

    def _evaluate_one(
        self,
        candidates: Sequence[Candidate],
        parsed: Any,
        call_result: Any,
    ) -> tuple[Candidate | None, CandidateTrustDecision | None]:
        """Record positive evidence and suppress early stop in forced A/B mode."""
        candidate, decision = super()._evaluate_one(candidates, parsed, call_result)
        if candidate is not None and decision is not None:
            candidate.positive_evidence = list(decision.positive_evidence)
            if self._forced_ab_active:
                candidate.trust_confidence = decision.confidence
                candidate.trust_reason = "forced_ab_diagnostic"
                self.harness.ledger.update_candidate(candidate)
                decision = replace(
                    decision,
                    trusted=False,
                    needs_second_sample=True,
                    reason="forced_ab_diagnostic",
                )
        self._decisions.append(decision)
        return candidate, decision

    def _primary_prompt(
        self,
        problem: str,
        route: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Select direct, structured, or skill-guided generation for A."""
        prompt = super()._primary_prompt(problem, route, trace, summary)
        skill = summary.get("skill_guidance")
        skill_id = skill.get("skill_id") if isinstance(skill, dict) else None
        plan = choose_solver_backend(
            route,
            reasoning_mode=self.solver_mode,
            skill_id=str(skill_id) if skill_id else None,
        )
        summary["candidate_generation"] = {
            "backend": plan.backend,
            "reasoning_mode": plan.reasoning_mode,
            "skill_id": skill_id,
        }
        if plan.backend == "structured_solver" and not skill_id:
            return DEEP_PRIMARY_PROMPT
        return prompt

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, ReasoningMode, int]:
        """Use continuation for visible ON work or independent OFF recovery."""
        primary_complete = (
            primary is not None
            and getattr(primary, "structural_validity", "") == "valid"
            and getattr(primary, "answer_complete", True)
        )
        if self.solver_mode == "on" and not primary_complete:
            visible = str(getattr(primary, "response", "") or "").strip()
            if visible:
                summary["on_recovery_action"] = "continuation"
                return (
                    "arm_v2_on_continuation",
                    f"{DEEP_CONTINUATION_PROMPT}\n\n待核对片段（不可信）：\n{visible[:4000]}",
                    "on",
                    self.harness.config.tokens_for("deep_continuation"),
                )
            summary["on_recovery_action"] = "off_recovery"
            return (
                "arm_v2_off_recovery",
                ARM_V213_OFF_RECOVERY_PROMPT,
                "off",
                int(getattr(self.harness.config, "arm_off_recovery_max_tokens", 4096)),
            )

        contract = getattr(route, "contract", route)
        risk = str(getattr(contract, "reasoning_risk", ""))
        confidence = str(getattr(contract, "route_confidence", ""))
        if risk != "direct" or confidence != "high":
            summary["candidate_generation_b"] = {
                "backend": "structured_solver",
                "reasoning_mode": self.solver_mode,
                "skill_id": None,
            }
            return (
                "arm_v2_structured_second",
                DEEP_REVIEW_PROMPT,
                self.solver_mode,
                self.harness.config.tokens_for("deep_primary"),
            )
        summary["candidate_generation_b"] = {
            "backend": "direct_solver",
            "reasoning_mode": self.solver_mode,
            "skill_id": None,
        }
        return super()._second_call_plan(problem, route, primary, trace, summary)

    @staticmethod
    def _decision_summary(decision: CandidateTrustDecision | None) -> dict[str, Any]:
        """Project trust decisions without retaining model text."""
        if decision is None:
            return {
                "trusted": False,
                "confidence": "unknown",
                "reason": "not_available",
                "positive_evidence": [],
            }
        return {
            "trusted": bool(decision.trusted),
            "confidence": decision.confidence,
            "reason": decision.reason,
            "positive_evidence": list(decision.positive_evidence),
        }


__all__ = ["AdaptiveReliabilityHarnessV213", "ARM_V213_OFF_RECOVERY_PROMPT"]
