"""Support seam for ARM-Harness v2.1 state preservation and optional audits."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

from reasoning_agent.arm_v21_diagnostics import candidate_diagnostics, parse_diagnostics
from reasoning_agent.harness_contracts import Candidate
from reasoning_agent.inference_policy import ReasoningMode
from reasoning_agent.math_harness import ATTEMPT_A_PROMPT
from reasoning_agent.safe_candidate import SafeCandidateState
from reasoning_agent.skill_audit import SkillAuditResult


ARM_V2_PRIMARY_PROMPT = ATTEMPT_A_PROMPT
ARM_V21_MARKER_ONLY_PRIMARY_PROMPT = f"""{ATTEMPT_A_PROMPT}
最后单独一行且必须使用：Final answer: <完整答案>"""
ARM_V21_PRIMARY_PROMPT = """你是数学推理求解器。独立解决题目，先完成必要计算，再给出唯一结论。
不要输出 Thinking Process、计划或多个候选；推导应简洁。
最后单独一行且必须使用：Final answer: <完整答案>"""
ARM_V21_SECOND_PROMPT = """你是独立的数学复核求解器。不要参考先前回答；从原题重新计算，检查定义域、边界和算术。
只给一个最可信的结论及最少量理由。
最后单独一行且必须使用：Final answer: <完整答案>"""
ARM_V21_OFF_FINALIZER_PROMPT = """你是数学答案收束器。只根据原题独立完成必要的最短计算。
不要输出计划、多个候选或 Thinking Process；尽快给出唯一结论。
最后单独一行且必须使用：Final answer: <完整答案>"""


class ARMV214StateSupport:
    """Provide deadline, safe-candidate, and reviewer-only helper methods."""

    def remaining_wall_seconds(self) -> float:
        """Return the solve-local wall-clock budget still available."""
        elapsed = self.harness.clock() - self.harness._solve_started
        return max(0.0, float(self.harness.config.max_wall_seconds) - elapsed)

    def should_finalize_now(self) -> bool:
        """Stop optional work once only the finalization margin remains."""
        margin = float(getattr(self.harness.config, "arm_finalization_margin_seconds", 15.0))
        return self.remaining_wall_seconds() <= margin

    def effective_timeout_seconds(self, configured_timeout: int | None) -> int | None:
        """Clamp one request to the remaining solve budget minus finalization."""
        margin = float(getattr(self.harness.config, "arm_finalization_margin_seconds", 15.0))
        available = self.remaining_wall_seconds() - margin
        if available <= 0:
            return None
        effective = math.floor(available)
        if configured_timeout is not None:
            effective = min(effective, int(configured_timeout))
        return max(1, effective)

    @staticmethod
    def _record_parse(summary: dict[str, Any], name: str, parsed: Any, candidates: list[Any]) -> None:
        """Store the bounded parser contract for one ARM sample."""
        summary[name] = parse_diagnostics(parsed, candidates)

    @staticmethod
    def _record_candidate(summary: dict[str, Any], name: str, candidate: Any) -> None:
        """Store the bounded candidate contract for one ARM sample."""
        summary[name] = candidate_diagnostics(candidate)

    @staticmethod
    def _candidate_summary(candidate: Candidate | None) -> dict[str, Any] | None:
        """Return bounded candidate telemetry for the result trace."""
        result = candidate_diagnostics(candidate)
        if result is not None:
            result["valid"] = result["structural_validity"] == "valid"
        return result

    @staticmethod
    def _append_summary(trace: list[dict[str, Any]], summary: dict[str, Any]) -> None:
        """Append one complete final-decision record to the solve trace."""
        summary["final"] = {
            "source": summary.get("final_source"),
            "failure_reason": summary.get("final_failure_reason"),
        }
        trace.append(summary)

    def _call(
        self,
        stage: str,
        prompt: str,
        problem: str,
        max_tokens: int,
        reasoning_mode: ReasoningMode,
        route: Any,
        *,
        source: str,
        timeout_seconds: int | None = None,
    ) -> tuple[Any, list[Candidate]]:
        """Apply v2.1 deadline clamping before using the shared scheduler."""
        effective_timeout = self.effective_timeout_seconds(timeout_seconds)
        if effective_timeout is None:
            record = {
                "stage": stage,
                "status": "skipped",
                "reason": "finalization_margin",
                "requested_tokens": 0,
                "error_category": "timeout",
                "finish_reason": None,
                "completion_tokens": None,
                "duration_ms": 0,
            }
            if reasoning_mode != "inherit":
                record["reasoning_mode"] = reasoning_mode
            if self.harness.ledger is not None:
                self.harness.ledger.add_call(record)
            self._last_call_result = SimpleNamespace(
                content=None,
                error_category="timeout",
                finish_reason=None,
            )
            return SimpleNamespace(
                status="missing",
                truncated=False,
                reason_summary="deadline_without_request",
            ), []
        return super()._call(
            stage,
            prompt,
            problem,
            max_tokens,
            reasoning_mode,
            route,
            source=source,
            timeout_seconds=effective_timeout,
        )

    def _primary_prompt(
        self,
        problem: str,
        route: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Inject only explicit method guidance into the independent A prompt."""
        base_prompt = self._primary_base_prompt()
        if not bool(getattr(self.harness.config, "arm_enable_skill_guidance", False)):
            trace.append({"method": "arm_harness_v2", "stage": "skill_guidance", "status": "disabled"})
            return base_prompt
        try:
            decision = self.skill_router.route(problem, route.contract)
            skill_id = getattr(decision, "skill_id", None)
            guidance = self.skill_router.guidance(decision) if skill_id else ""
            guidance = str(guidance or "").strip()
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "skill_guidance",
                    "status": "injected" if skill_id and guidance else "no_skill",
                    "skill_id": skill_id,
                    "confidence": float(getattr(decision, "confidence", 0.0)),
                    "reason": str(getattr(decision, "reason", ""))[:240],
                }
            )
            if skill_id and guidance:
                summary["skill_guidance"] = {
                    "skill_id": str(skill_id),
                    "confidence": float(getattr(decision, "confidence", 0.0)),
                }
                return f"方法指导（仅供推理，不是答案）：\n{guidance[:4000]}\n\n{base_prompt}"
        except BaseException as exc:
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "skill_guidance",
                    "status": "error",
                    "reason": f"router_error:{type(exc).__name__}",
                }
            )
        return base_prompt

    def _primary_base_prompt(self) -> str:
        """Select one prompt variant for a primary-only isolation experiment."""
        variants = {
            "v2": ARM_V2_PRIMARY_PROMPT,
            "marker_only": ARM_V21_MARKER_ONLY_PRIMARY_PROMPT,
            "v21": ARM_V21_PRIMARY_PROMPT,
        }
        return variants.get(
            str(getattr(self.harness.config, "arm_primary_prompt_variant", "v21")),
            ARM_V21_PRIMARY_PROMPT,
        )

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, ReasoningMode, int]:
        """Choose an orthogonal OFF finalizer after an incomplete ON solve."""
        primary_complete = (
            primary is not None
            and getattr(primary, "structural_validity", "") == "valid"
            and getattr(primary, "answer_complete", True)
        )
        if self.solver_mode == "on" and not primary_complete:
            summary["on_recovery_action"] = "off_finalizer"
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "on_to_off_recovery",
                    "status": "triggered",
                    "reason": "primary_incomplete_or_missing",
                    "from": "on",
                    "to": "off",
                }
            )
            return (
                "arm_v2_off_finalizer",
                ARM_V21_OFF_FINALIZER_PROMPT,
                "off",
                int(getattr(self.harness.config, "arm_off_finalizer_max_tokens", 1024)),
            )
        return (
            "arm_v2_second_sample",
            self._second_prompt(problem, route, trace, summary),
            self.solver_mode,
            self.harness.config.tokens_for("attempt_b"),
        )

    def _second_prompt(
        self,
        problem: str,
        route: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Use an independently routed skill only when explicitly enabled."""
        if not bool(getattr(self.harness.config, "arm_enable_skill_for_second", False)):
            return ARM_V21_SECOND_PROMPT
        try:
            decision = self.skill_router.route(problem, route.contract)
            skill_id = getattr(decision, "skill_id", None)
            guidance = str(self.skill_router.guidance(decision) if skill_id else "").strip()
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "second_skill_guidance",
                    "status": "injected" if skill_id and guidance else "no_skill",
                    "skill_id": skill_id,
                    "confidence": float(getattr(decision, "confidence", 0.0)),
                    "reason": str(getattr(decision, "reason", ""))[:240],
                }
            )
            if skill_id and guidance:
                summary["second_skill_guidance"] = {"skill_id": str(skill_id)}
                return f"方法指导（独立 B）：\n{guidance[:4000]}\n\n{ARM_V21_SECOND_PROMPT}"
        except BaseException as exc:
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "second_skill_guidance",
                    "status": "error",
                    "reason": f"router_error:{type(exc).__name__}",
                }
            )
        return ARM_V21_SECOND_PROMPT

    @staticmethod
    def _second_sample_trigger_reason(primary: Candidate | None, decision: Any, route: Any) -> str:
        """Explain why B ran without consulting any gold answer."""
        if primary is None:
            return "primary_missing"
        if getattr(primary, "answer_complete", True) is False:
            return "primary_incomplete"
        if getattr(primary, "structural_validity", "") != "valid":
            return "primary_invalid"
        if getattr(route.contract, "route_confidence", "") == "low":
            return "low_route_confidence"
        if getattr(route.contract, "reasoning_risk", "") == "deep":
            return "deep_contract"
        confidence = str(getattr(decision, "confidence", "low"))
        return "primary_medium_trust" if confidence == "medium" else "primary_low_trust"

    def _run_verification(self, candidate_a: Candidate, candidate_b: Candidate, problem: str) -> dict[str, Any]:
        """Run the cheap verifier and fail open to the LLM resolver."""
        try:
            result = self.deterministic_verifier.verify(candidate_a, candidate_b, problem)
            status = str(getattr(result, "status", "UNKNOWN")).upper()
            candidate_id = getattr(result, "candidate_id", None)
            reason = str(getattr(result, "reason", ""))[:240]
            if status not in {"A", "B", "UNKNOWN", "NOT_APPLICABLE"}:
                status, candidate_id, reason = "UNKNOWN", None, "invalid_verification_result"
            if status == "A" and candidate_id != candidate_a.candidate_id:
                status, candidate_id, reason = "UNKNOWN", None, "verification_candidate_mismatch"
            if status == "B" and candidate_id != candidate_b.candidate_id:
                status, candidate_id, reason = "UNKNOWN", None, "verification_candidate_mismatch"
            return {"status": status, "candidate_id": candidate_id, "reason": reason}
        except BaseException as exc:
            return {
                "status": "UNKNOWN",
                "candidate_id": None,
                "reason": f"verifier_error:{type(exc).__name__}",
            }

    @staticmethod
    def _checkpoint(
        candidate: Candidate | None,
        parsed: Any,
        safe_state: SafeCandidateState,
        stage: str,
    ) -> bool:
        """Checkpoint a complete, structurally valid candidate before risky work."""
        if (
            candidate is None
            or getattr(candidate, "answer_complete", True) is False
        ):
            return False
        existing = safe_state.get()
        if stage == "candidate_b" and existing is not None:
            # Challenger formation must not erase the incumbent before an
            # evidence-backed repair and fresh review exist.
            return False
        candidate.candidate_role = "primary" if stage == "candidate_a" or existing is None else "challenger"
        candidate.candidate_version = 1
        candidate.incumbent = existing is None or stage == "candidate_a"
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
            or getattr(candidate, "answer_complete", True) is False
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
        summary["safe_candidate"] = candidate_diagnostics(safe)
        if safe is not None:
            summary["safe_fallback_used"] = True
            summary["final_source"] = (
                "deadline_fallback" if reason.startswith("deadline_") else "safe_candidate"
            )
            summary["fallback_reason"] = reason
            summary["final_failure_reason"] = None
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "safe_candidate_fallback",
                    "reason": reason,
                    "source": safe_state.source,
                }
            )
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                safe,
                candidates or [safe],
                "arm_v2_safe_candidate_fallback",
            )
        summary["final_source"] = "abstain"
        summary["final_failure_reason"] = reason
        self._append_summary(trace, summary)
        result = self.harness._abstain(trace, route_data, reason)
        result["final_failure_reason"] = reason
        result["final_source"] = "abstain"
        return result

