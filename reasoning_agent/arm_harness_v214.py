"""ARM-Harness v2: selective candidate verification under bounded compute."""

from __future__ import annotations

from typing import Any, Sequence

from reasoning_agent.answer_completeness_v214 import assess_answer_completeness
from reasoning_agent.arm_v21_diagnostics import pair_relation, second_sample_outcome
from reasoning_agent.arm_v214_verification import (
    ChallengerFinding,
    DeterministicVerifier,
    FreshReview,
    replacement_decision,
    parse_challenger_finding,
)
from reasoning_agent.arm_harness import AdaptiveReasoningHarness
from reasoning_agent.candidate_trust import CandidateTrustPolicy
from reasoning_agent.candidate_validation import validate_candidate_shape
from reasoning_agent.harness_contracts import (
    ANSWER_SHAPE_SINGLE_NUMERIC,
    ANSWER_SHAPE_UNKNOWN,
    CANDIDATE_CONFLICT,
    Candidate,
    HostParser,
    TypedParser,
    STATE_ATTEMPT_A,
    STATE_ATTEMPT_B,
    STATE_CANDIDATE_A,
    STATE_CANDIDATE_B,
    STATE_CONFLICT,
    STATE_CRITIC,
    STATE_REPAIR,
    value_equivalence,
)
from reasoning_agent.inference_policy import ComputePolicy
from reasoning_agent.math_harness import BudgetLedger
from reasoning_agent.runtime_policy import (
    RuntimeRecoveryPolicy,
    classify_runtime_failure,
)
from reasoning_agent.arm_v214_support import ARMV214StateSupport, ARM_V21_PRIMARY_PROMPT
from reasoning_agent.safe_candidate import SafeCandidateState
from reasoning_agent.skill_audit import SkillAuditor
from reasoning_agent.skill_guidance import SkillRouter


ARM_COMPACT_SALVAGE_PROMPT = """请直接重新求解并尽快形成最终答案。

不要展开长证明，只保留必要计算。

最后一行：Final answer: <answer>"""

ARM_V2_RESOLVER_PROMPT = """给定同一道数学题的两个候选答案。

只能输出一行：A、B 或 UNKNOWN。
只能选择已有候选，不能生成第三个答案，也不要重新求解。"""

ARM_V2_REPAIR_PROMPT = """只修复候选中 Challenger 指出的局部错误。
必须保留原候选的其余结论，不要整题重解，不要输出多个候选。
最后单独一行：Final answer: <完整答案>"""

ARM_V2_FRESH_REVIEW_PROMPT = """复核修复后的候选是否解决了指定异议。
只输出一行 PASS、FAIL 或 UNKNOWN。"""

ARM_V214_CHALLENGER_PROMPT = """你是 Primary 候选的 Challenger。
只检查下面候选在原题约束下是否有具体可核查错误，不要凭“看起来不同”提出异议。
严格输出一个 JSON 对象，字段为 verdict、issue_type、issue_location、claim、evidence、repairable、coverage。
verdict 只能是 NO_OBJECTION、OBJECTION、UNKNOWN；没有具体位置和证据就用 UNKNOWN。
若发现可修复错误，可在 JSON 后追加一行：Final answer: <修复后的完整答案>。
若没有错误，也追加一行：Final answer: <原候选值>。
"""


class AdaptiveReliabilityHarnessV214(ARMV214StateSupport, AdaptiveReasoningHarness):
    """Run ARM v2 trust gating, selective resampling, and bounded resolution."""

    def __init__(self, harness: Any) -> None:
        """Bind v2 policies to the existing parser, ledger, and scheduler seams."""
        super().__init__(harness)
        config = harness.config
        self.compute_policy = self._build_compute_policy(config)
        self.trust_policy = CandidateTrustPolicy(getattr(config, "arm_trust_policy", "legacy"))
        self.runtime_policy = RuntimeRecoveryPolicy(
            config.arm_timeout_recovery_mode,
            salvage_max_tokens=config.arm_salvage_max_tokens,
            salvage_timeout_seconds=config.arm_salvage_timeout_seconds,
        )
        self.solver_mode_policy = getattr(config, "arm_solver_reasoning_mode", "off")
        self.solver_mode = self.solver_mode_policy
        provided_auditor = getattr(harness, "skill_auditor", None)
        self.skill_auditor = provided_auditor if provided_auditor is not None else SkillAuditor()
        provided_verifier = getattr(harness, "deterministic_verifier", None)
        self.deterministic_verifier = provided_verifier or DeterministicVerifier()
        provided_router = getattr(harness, "skill_router", None)
        self.skill_router = provided_router or SkillRouter()

    @staticmethod
    def _build_compute_policy(config: Any) -> ComputePolicy:
        """Translate an explicit v2 profile into one solve-local budget."""
        mode = config.arm_v2_mode
        if mode == "single":
            return ComputePolicy(1, config.arm_fast_token_budget, config.max_wall_seconds, False, False, False)
        if mode == "long_timeout":
            return ComputePolicy(1, config.arm_adaptive_token_budget, config.max_wall_seconds, False, False, False)
        if mode == "salvage":
            return ComputePolicy(2, config.arm_adaptive_token_budget, config.max_wall_seconds, False, False, False)
        return ComputePolicy(
            max(4, int(config.arm_adaptive_max_calls)),
            config.arm_adaptive_token_budget,
            config.max_wall_seconds,
            True,
            True,
            bool(config.arm_allow_thinking_on),
        )

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Use the second call as a structured Challenger review."""
        del problem, route, trace
        value = str(getattr(primary, "normalized_value", "") or "")
        summary["candidate_generation_b"] = {"backend": "challenger", "reasoning_mode": self.solver_mode}
        return (
            "arm_v214_challenger",
            f"{ARM_V214_CHALLENGER_PROMPT}\n\nPrimary 候选：{value}",
            self.solver_mode,
            self.harness.config.tokens_for("attempt_b"),
        )

    def solve(self, problem: str, route: Any, prefix_trace: list[dict[str, Any]]) -> dict[str, Any]:
        """Run the v2.1 state machine while preserving a safe checkpoint."""
        policy = self.compute_policy
        self._current_route_contract = route.contract
        self.harness.budget = BudgetLedger(
            max_calls=policy.max_calls,
            total_tokens=policy.token_budget,
            clock=self.harness.clock,
        )
        trace = list(prefix_trace)
        route_data = route.as_dict()
        route_data.update(target="harness", lane=policy_name(self.harness.config.arm_v2_mode), arm_lane="v2")
        self.solver_mode, solver_mode_reason = self._resolve_solver_mode(route)
        for event in trace:
            if event.get("stage") == "route":
                event.update(target="harness", lane=route_data["lane"], arm_lane="v2")

        summary: dict[str, Any] = {
            "method": "arm_harness_v2",
            "stage": "arm_v2_summary",
            "profile": self.harness.config.arm_v2_mode,
            "trust_policy": getattr(self.harness.config, "arm_trust_policy", "legacy"),
            "configured_solver_reasoning_mode": self.solver_mode_policy,
            "solver_reasoning_mode": self.solver_mode,
            "solver_mode_policy_reason": solver_mode_reason,
            "early_stop": False,
            "second_sample_triggered": False,
            "agreement": False,
            "conflict": False,
            "resolver_triggered": False,
            "resolver_decision": None,
            "runtime_recovery_action": None,
            "skill_triggered": False,
            "skill_status": None,
            "safe_fallback_used": False,
            "deadline_finalized": False,
            "final_source": None,
            "final_failure_reason": None,
            "primary_parse": {"status": "not_run", "reason": "not_started", "truncated": False, "candidate_count": 0},
            "primary_candidate": None,
            "candidate_a": None,
            "second_parse": {"status": "not_run", "reason": "not_triggered", "truncated": False, "candidate_count": 0},
            "second_candidate": None,
            "candidate_b": None,
            "safe_candidate": None,
            "a_b_relation": "NO_VALID_PAIR",
            "pair_relation": "NO_VALID_PAIR",
            "second_sample_trigger_reason": None,
            "second_sample_outcome": "no_value",
            "resolver": {
                "candidate_a_value": None,
                "candidate_b_value": None,
                "candidate_a_trust": None,
                "candidate_b_trust": None,
                "resolver_decision": None,
                "selected_source": None,
                "resolver_verdict": None,
            },
            "verification": {"status": "NOT_APPLICABLE", "candidate_id": None, "reason": "not_run"},
            "challenger_shadow": False,
            "challenger_status": "UNKNOWN",
            "challenger": None,
            "replacement_reason": "",
            "repair_attempted": False,
            "fresh_review_status": "NOT_RUN",
        }
        trace.append(
            {
                "method": "arm_harness_v2",
                "stage": "arm_v2_policy",
                "profile": self.harness.config.arm_v2_mode,
                "max_calls": policy.max_calls,
                "token_budget": policy.token_budget,
                "allow_second_sample": policy.allow_second_sample,
                "allow_resolver": policy.allow_resolver,
                "allow_thinking_on": policy.allow_thinking_on,
                "configured_solver_reasoning_mode": self.solver_mode_policy,
                "solver_reasoning_mode": self.solver_mode,
                "solver_mode_policy_reason": solver_mode_reason,
                "skill_guidance_enabled": bool(getattr(self.harness.config, "arm_enable_skill_guidance", False)),
                "skill_audit_enabled": bool(getattr(self.harness.config, "arm_enable_skill_audit", False)),
            }
        )
        self.harness.ledger.transition("arm_v2_policy", reason=self.harness.config.arm_v2_mode)
        safe_state = SafeCandidateState()

        primary_timeout = self.harness.config.arm_primary_timeout_seconds
        if self.harness.config.arm_v2_mode == "long_timeout" and primary_timeout is None:
            primary_timeout = 60
        self.harness.ledger.transition(STATE_ATTEMPT_A)
        parsed_a, candidates_a = self._call(
            "arm_v2_primary",
            self._primary_prompt(problem, route, trace, summary),
            problem,
            self.harness.config.tokens_for("attempt_a"),
            self.solver_mode,
            route,
            source="arm_primary",
            timeout_seconds=primary_timeout,
        )
        call_a = self._last_call_result
        self._record(STATE_CANDIDATE_A, parsed_a, candidates_a)
        self._record_parse(summary, "primary_parse", parsed_a, candidates_a)

        runtime_failure = classify_runtime_failure(call_a)
        if runtime_failure is not None:
            parsed_a, candidates_a, call_a = self._recover_runtime(
                problem,
                route,
                parsed_a,
                candidates_a,
                call_a,
                runtime_failure,
                primary_timeout,
                trace,
                summary,
                self.solver_mode,
            )
            if classify_runtime_failure(call_a) is not None:
                return self._return_safe_or_abstain(
                    trace, route_data, summary, safe_state, candidates_a, "runtime_recovery_failed"
                )
            self._record_parse(summary, "primary_parse", parsed_a, candidates_a)

        primary, primary_decision = self._evaluate_one(candidates_a, parsed_a, call_a)
        summary["candidate_a"] = self._candidate_summary(primary)
        summary["primary_candidate"] = self._candidate_summary(primary)
        summary["safe_candidate"] = self._candidate_summary(safe_state.get())
        if self._checkpoint(primary, parsed_a, safe_state, "candidate_a"):
            summary["safe_candidate_source"] = safe_state.source
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "safe_candidate_checkpoint",
                    "source": safe_state.source,
                    "checkpoint_stage": safe_state.checkpoint_stage,
                }
            )
        summary["safe_candidate"] = self._candidate_summary(safe_state.get())
        if primary_decision is not None and primary_decision.trusted:
            summary["early_stop"] = True
            summary["final_source"] = "candidate_a"
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                primary,
                candidates_a,
                "arm_v2_trusted_primary",
                problem=problem,
            )

        skill_result = self._maybe_audit_skill(
            problem,
            route,
            primary,
            primary_decision,
            trace,
            summary,
        )
        if skill_result is not None and skill_result.status == "supported" and primary is not None:
            primary.verification_status = "skill_supported"
            primary.trust_confidence = "high"
            primary.trust_reason = skill_result.reason
            self.harness.ledger.update_candidate(primary)
            safe_state.update(
                primary,
                source="candidate_a",
                confidence="high",
                checkpoint_stage="skill_supported",
            )
            summary["final_source"] = "skill_supported"
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                primary,
                candidates_a,
                "arm_v2_skill_supported",
                problem=problem,
            )
        if skill_result is not None and skill_result.status == "refuted":
            safe_state.clear()

        if not policy.allow_second_sample:
            return self._return_safe_or_abstain(
                trace, route_data, summary, safe_state, candidates_a, "candidate_untrusted"
            )

        if self.should_finalize_now():
            summary["deadline_finalized"] = True
            return self._return_safe_or_abstain(
                trace, route_data, summary, safe_state, candidates_a, "deadline_before_second_sample"
            )

        summary["second_sample_triggered"] = True
        summary["second_sample_trigger_reason"] = self._second_sample_trigger_reason(
            primary, primary_decision, route
        )
        self.harness.ledger.transition(STATE_ATTEMPT_B, reason="candidate_trust_gate")
        second_stage, second_prompt, second_mode, second_tokens = self._second_call_plan(
            problem, route, primary, trace, summary
        )
        parsed_b, candidates_b = self._call(
            second_stage,
            second_prompt,
            problem,
            second_tokens,
            second_mode,
            route,
            source="arm_second",
            timeout_seconds=primary_timeout,
        )
        call_b = self._last_call_result
        self._record(STATE_CANDIDATE_B, parsed_b, candidates_b)
        self._record_parse(summary, "second_parse", parsed_b, candidates_b)
        if classify_runtime_failure(call_b) is not None:
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "second_sample_runtime_failure",
            )

        secondary, secondary_decision = self._evaluate_one(candidates_b, parsed_b, call_b)
        summary["candidate_b"] = self._candidate_summary(secondary)
        summary["second_candidate"] = self._candidate_summary(secondary)
        if self._checkpoint(secondary, parsed_b, safe_state, "candidate_b"):
            summary["safe_candidate_source"] = safe_state.source
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "safe_candidate_checkpoint",
                    "source": safe_state.source,
                    "checkpoint_stage": safe_state.checkpoint_stage,
                }
            )
        primary_valid = (
            primary
            if primary is not None
            and primary.structural_validity == "valid"
            and primary.answer_complete
            else None
        )
        secondary_valid = (
            secondary
            if secondary is not None
            and secondary.structural_validity == "valid"
            and secondary.answer_complete
            else None
        )
        summary["a_b_relation"] = pair_relation(primary_valid, secondary_valid)
        summary["pair_relation"] = summary["a_b_relation"]
        summary["second_sample_outcome"] = second_sample_outcome(summary["a_b_relation"])
        summary["safe_candidate"] = self._candidate_summary(safe_state.get())
        if primary_valid is None and secondary_decision is not None and secondary_decision.trusted:
            summary["final_source"] = "candidate_b"
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                secondary_valid,
                candidates_b,
                "arm_v2_trusted_second_sample",
                problem=problem,
            )
        if primary_valid is None or secondary_valid is None:
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "second_sample_incomplete",
            )

        relation = value_equivalence(primary_valid.value, secondary_valid.value)
        if relation == "EQUIVALENT":
            finding = ChallengerFinding(verdict="NO_OBJECTION", coverage="candidate_value_equivalence")
            summary["challenger"] = finding.as_dict()
            summary["challenger_status"] = finding.verdict
            for candidate in (primary_valid, secondary_valid):
                candidate.verification_status = "consensus_supported"
                candidate.extraction_status = "verified"
                candidate.trust_confidence = "high"
                candidate.trust_reason = "independent_agreement"
                self.harness.ledger.update_candidate(candidate)
            summary["agreement"] = True
            summary["final_source"] = "consensus"
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                secondary,
                [*candidates_a, *candidates_b],
                "arm_v2_consensus_supported",
                problem=problem,
            )

        summary["conflict"] = True
        finding = self._challenger_finding(primary_valid, secondary_valid, problem)
        summary["challenger"] = finding.as_dict()
        summary["challenger_status"] = finding.verdict
        primary_valid.challenge_status = finding.verdict.casefold()
        primary_valid.challenge_id = "challenger-1"
        secondary_valid.challenge_status = finding.verdict.casefold()
        secondary_valid.challenge_id = "challenger-1"
        if bool(getattr(self.harness.config, "arm_challenger_shadow", False)):
            summary["challenger_shadow"] = True
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "challenger_shadow",
            )
        if (
            finding.supports_replacement
            and bool(getattr(self.harness.config, "arm_enable_targeted_repair", False))
            and bool(getattr(self.harness.config, "arm_enable_fresh_review", False))
        ):
            repaired, review = self._targeted_repair(
                problem, route, primary_valid, finding, trace, summary
            )
            allowed, replacement_reason = replacement_decision(finding, review)
            summary["replacement_reason"] = replacement_reason
            if allowed and repaired is not None:
                repaired.candidate_role = "repair"
                repaired.candidate_version = primary_valid.candidate_version + 1
                repaired.incumbent = True
                repaired.replacement_reason = replacement_reason
                summary["final_source"] = "repair"
                self._append_summary(trace, summary)
                return self.harness._select(
                    trace,
                    route_data,
                    repaired,
                    [*candidates_a, *candidates_b, repaired],
                    "arm_v2_fresh_review_replacement",
                    problem=problem,
                )
            return self._return_safe_or_abstain(
                trace, route_data, summary, safe_state,
                [*candidates_a, *candidates_b], replacement_reason,
            )
        if not policy.allow_resolver or self.harness.budget.calls_used >= self.harness.budget.max_calls:
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "arm_v2_conflict_unresolved",
            )

        self.harness.ledger.transition(STATE_CONFLICT, reason="arm_v2_candidate_conflict")
        self.harness.ledger.add_conflict([primary_valid, secondary_valid])
        if self.should_finalize_now():
            summary["deadline_finalized"] = True
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "deadline_before_resolver",
            )
        verification = self._run_verification(primary_valid, secondary_valid, problem)
        summary["verification"] = verification
        if verification["status"] in {"A", "B"}:
            selected = primary_valid if verification["status"] == "A" else secondary_valid
            selected.verification_status = "deterministic_verified"
            selected.trust_confidence = "high"
            selected.trust_reason = verification["reason"] or "deterministic_verification"
            self.harness.ledger.update_candidate(selected)
            summary["final_source"] = "candidate_a" if verification["status"] == "A" else "candidate_b"
            self._append_summary(trace, summary)
            return self.harness._select(
                trace,
                route_data,
                selected,
                [*candidates_a, *candidates_b],
                "arm_v2_deterministic_verification",
                problem=problem,
            )
        self.harness.ledger.transition(STATE_CRITIC, reason="arm_v2_conflict")
        summary["resolver_triggered"] = True
        resolver_tokens = min(1_024, self.harness.budget.total_tokens - self.harness.budget.requested_tokens)
        resolver_timeout = self.effective_timeout_seconds(None)
        if resolver_timeout is None:
            summary["deadline_finalized"] = True
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "deadline_before_resolver",
            )
        resolver = self.harness.scheduler.call(
            "arm_v2_resolver",
            ARM_V2_RESOLVER_PROMPT,
            self.harness._critic_prompt(problem, [primary_valid, secondary_valid]),
            resolver_tokens,
            reasoning_mode="off",
            timeout_seconds=resolver_timeout,
        )
        if classify_runtime_failure(resolver) is not None:
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "resolver_runtime_failure",
            )
        decision = self._parse_resolver(resolver.content)
        summary["resolver_decision"] = decision
        summary["resolver"].update(
            {
                "candidate_a_value": primary_valid.normalized_value,
                "candidate_b_value": secondary_valid.normalized_value,
                "candidate_a_trust": primary_valid.trust_confidence,
                "candidate_b_trust": secondary_valid.trust_confidence,
                "resolver_decision": decision,
                "selected_source": f"candidate_{decision.lower()}" if decision in {"A", "B"} else None,
                "resolver_verdict": None,
            }
        )
        if decision == "A":
            selected = primary_valid
        elif decision == "B":
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "resolver_b_without_review",
            )
        else:
            return self._return_safe_or_abstain(
                trace,
                route_data,
                summary,
                safe_state,
                [*candidates_a, *candidates_b],
                "arm_v2_resolver_unknown",
            )
        selected.verification_status = "bounded_resolver"
        selected.trust_confidence = "medium"
        selected.trust_reason = "bounded_resolver_selected"
        self.harness.ledger.update_candidate(selected)
        summary["final_source"] = f"resolver_{decision.lower()}"
        self._append_summary(trace, summary)
        return self.harness._select(
            trace,
            route_data,
            selected,
            [*candidates_a, *candidates_b],
            "arm_v2_bounded_resolver",
            problem=problem,
        )

    def _recover_runtime(
        self,
        problem: str,
        route: Any,
        parsed: Any,
        candidates: list[Candidate],
        call_result: Any,
        failure: Any,
        current_timeout: int | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
        solver_mode: str,
    ) -> tuple[Any, list[Candidate], Any]:
        """Apply one runtime recovery action without invoking the trust gate."""
        assert self.harness.budget is not None
        decision = self.runtime_policy.decide(
            failure,
            current_max_tokens=self.harness.config.tokens_for("attempt_a"),
            current_timeout_seconds=current_timeout,
            remaining_calls=self.harness.budget.max_calls - self.harness.budget.calls_used,
            remaining_tokens=self.harness.budget.total_tokens - self.harness.budget.requested_tokens,
        )
        summary["runtime_recovery_action"] = decision.action
        trace.append(
            {
                "method": "arm_harness_v2",
                "stage": "arm_v2_runtime_recovery",
                "failure": failure,
                "action": decision.action,
                "reason": decision.reason,
            }
        )
        if decision.action == "abstain":
            return parsed, candidates, call_result
        prompt = (
            ARM_COMPACT_SALVAGE_PROMPT
            if decision.action == "compact_salvage"
            else ARM_V21_PRIMARY_PROMPT
        )
        recovered_parsed, recovered_candidates = self._call(
            "arm_v2_runtime_recovery",
            prompt,
            problem,
            decision.max_tokens,
            solver_mode,
            route,
            source="arm_salvage" if decision.action == "compact_salvage" else "arm_runtime_retry",
            timeout_seconds=decision.timeout_seconds,
        )
        recovered_call = self._last_call_result
        self._record(STATE_CANDIDATE_A, recovered_parsed, recovered_candidates)
        return recovered_parsed, recovered_candidates, recovered_call

    def _challenger_finding(
        self,
        primary: Candidate,
        secondary: Candidate,
        problem: str,
    ) -> ChallengerFinding:
        """Return a bounded objection record without selecting either answer."""
        del primary, problem
        finding = parse_challenger_finding(getattr(secondary, "response", ""))
        if finding.verdict != "UNKNOWN":
            return finding
        return ChallengerFinding(verdict="UNKNOWN", coverage="challenger_response_unparseable")

    def _targeted_repair(
        self,
        problem: str,
        route: Any,
        incumbent: Candidate,
        finding: ChallengerFinding,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[Candidate | None, FreshReview | None]:
        """Run one local repair and one fresh review behind explicit flags."""
        repair_prompt = (
            f"{ARM_V2_REPAIR_PROMPT}\n\n"
            f"原候选：{incumbent.normalized_value}\n"
            f"异议位置：{finding.issue_location}\n"
            f"异议主张：{finding.claim}\n"
            f"证据：{finding.evidence}"
        )
        parsed, candidates = self._call(
            "arm_v2_targeted_repair",
            repair_prompt,
            problem,
            self.harness.config.tokens_for("repair"),
            self.solver_mode,
            route,
            source="arm_repair",
            timeout_seconds=self.effective_timeout_seconds(None),
        )
        call_result = self._last_call_result
        self._record(STATE_REPAIR, parsed, candidates)
        repaired, _decision = self._evaluate_one(candidates, parsed, call_result)
        review = None
        if repaired is not None:
            review_call = self.harness.scheduler.call(
                "arm_v2_fresh_review",
                ARM_V2_FRESH_REVIEW_PROMPT,
                f"原题：{problem}\n修复候选：{repaired.normalized_value}\n异议：{finding.evidence}",
                min(512, self.harness.budget.total_tokens - self.harness.budget.requested_tokens),
                reasoning_mode="off",
                timeout_seconds=self.effective_timeout_seconds(None),
            )
            token = str(getattr(review_call, "content", "") or "").strip().splitlines()
            status = token[0].upper() if token and token[0].upper() in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
            review = FreshReview(status, "fresh_review")
        summary["repair_attempted"] = True
        summary["fresh_review_status"] = review.status if review else "UNKNOWN"
        return repaired, review

    def _evaluate_one(self, candidates: Sequence[Candidate], parsed: Any, call_result: Any):
        """Annotate one candidate with structural and trust metadata."""
        if len(candidates) != 1:
            for candidate in candidates:
                candidate.structural_validity = "invalid"
                candidate.answer_complete = False
                candidate.answer_complete_reason = "multiple_candidates"
                candidate.trust_confidence = "low"
                candidate.trust_reason = "multiple_candidates"
                self.harness.ledger.update_candidate(candidate)
            return None, None
        candidate = candidates[0]
        valid, _reason = validate_candidate_shape(candidate, candidate.answer_type)
        candidate.structural_validity = "valid" if valid else "invalid"
        complete, complete_reason = assess_answer_completeness(
            candidate,
            answer_shape=self._current_route_contract.answer_shape,
            parsed=parsed,
        )
        candidate.answer_complete = complete
        candidate.answer_complete_reason = complete_reason
        self.harness.ledger.update_candidate(candidate)
        decision = self.trust_policy.evaluate(
            contract=self._current_route_contract,
            candidate=candidate,
            parsed=parsed,
            call_result=call_result,
        )
        candidate.trust_confidence = decision.confidence
        candidate.trust_reason = decision.reason
        self.harness.ledger.update_candidate(candidate)
        return candidate, decision

    @staticmethod
    def _parse_resolver(response: str | None) -> str:
        """Accept only A, B, or UNKNOWN from the bounded resolver."""
        text = (response or "").strip().splitlines()
        first = text[0].strip().upper() if text else ""
        if first in {"A", "B", "UNKNOWN"}:
            return first
        return "UNKNOWN"

    def _resolve_solver_mode(self, route: Any) -> tuple[str, str]:
        """Resolve adaptive mode from the existing route-risk contract."""
        if self.solver_mode_policy != "adaptive":
            return self.solver_mode_policy, "fixed_profile_mode"
        contract = getattr(route, "contract", None)
        risk = str(getattr(contract, "reasoning_risk", ""))
        lane = str(getattr(route, "lane", ""))
        if lane == "deep" or risk in {"deep", "structured"}:
            return "on", "route_risk_requires_deeper_primary"
        return "off", "route_risk_allows_fast_primary"


def policy_name(mode: str) -> str:
    """Name the v2 compute lane without exposing a new host route."""
    return f"v2_{mode}"

__all__ = ["AdaptiveReliabilityHarness", "ARM_COMPACT_SALVAGE_PROMPT", "ARM_V2_RESOLVER_PROMPT"]

