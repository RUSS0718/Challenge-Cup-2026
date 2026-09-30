"""ARM-Harness v2: selective candidate verification under bounded compute."""

from __future__ import annotations

from typing import Any, Sequence

from reasoning_agent.answer_completeness import assess_answer_completeness
from reasoning_agent.arm_v21_diagnostics import pair_relation, second_sample_outcome
from reasoning_agent.arm_v21_verification import DeterministicVerifier
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
    _unique_candidates,
    value_equivalence,
)
from reasoning_agent.inference_policy import ComputePolicy
from reasoning_agent.math_harness import BudgetLedger
from reasoning_agent.runtime_policy import (
    RuntimeRecoveryPolicy,
    classify_runtime_failure,
)
from reasoning_agent.arm_v21_support import ARMV21StateSupport, ARM_V21_PRIMARY_PROMPT
from reasoning_agent.safe_candidate import SafeCandidateState
from reasoning_agent.skill_audit import SkillAuditor
from reasoning_agent.skill_guidance import SkillRouter


ARM_COMPACT_SALVAGE_PROMPT = """请直接重新求解并尽快形成最终答案。

不要展开长证明，只保留必要计算。

最后一行：Final answer: <answer>"""

ARM_V2_RESOLVER_PROMPT = """你是数学候选验证器。给定原题与两个冲突候选 A/B。

不要凭措辞或先后顺序偏好候选。请只检查能区分 A/B 的关键约束、代入、边界或算术；
允许做最短的局部重算，但不要生成第三个候选答案。

必须输出两行：
CHECK: <一句话说明实际检查了什么；无法形成判据时写 insufficient>
DECISION: A、B 或 UNKNOWN

只有 CHECK 给出具体判据时才允许选择 A/B；证据不足则输出 UNKNOWN。"""


class AdaptiveReliabilityHarness(ARMV21StateSupport, AdaptiveReasoningHarness):
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
        return ComputePolicy(3, config.arm_adaptive_token_budget, config.max_wall_seconds, True, True, bool(config.arm_allow_thinking_on))

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
        primary_checkpointed = self._checkpoint(primary, parsed_a, safe_state, "candidate_a")
        weak_checkpointed = False
        if not primary_checkpointed:
            weak_checkpointed = self._checkpoint_weak(primary, parsed_a, safe_state, "candidate_a")
        if primary_checkpointed or weak_checkpointed:
            summary["safe_candidate_source"] = safe_state.source
            trace.append(
                {
                    "method": "arm_harness_v2",
                    "stage": "safe_candidate_checkpoint",
                    "source": safe_state.source,
                    "checkpoint_stage": safe_state.checkpoint_stage,
                    "policy": "weak_incumbent" if weak_checkpointed else "complete_incumbent",
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
        second_timeout_cap = int(
            getattr(
                self.harness.config,
                "arm_second_timeout_with_incumbent_seconds"
                if safe_state.get() is not None
                else "arm_second_timeout_without_incumbent_seconds",
                180 if safe_state.get() is not None else 300,
            )
        )
        second_timeout = second_timeout_cap
        if primary_timeout is not None:
            second_timeout = min(int(primary_timeout), second_timeout_cap)
        summary["second_sample_timeout_seconds"] = second_timeout
        parsed_b, candidates_b = self._call(
            second_stage,
            second_prompt,
            problem,
            second_tokens,
            second_mode,
            route,
            source="arm_second",
            timeout_seconds=second_timeout,
        )
        call_b = self._last_call_result
        self._record(STATE_CANDIDATE_B, parsed_b, candidates_b)
        self._record_parse(summary, "second_parse", parsed_b, candidates_b)
        second_failure = classify_runtime_failure(call_b)
        if second_failure is not None:
            # If an incumbent already exists, the challenger is optional: fail
            # closed on replacement and immediately return the incumbent.
            if safe_state.get() is not None:
                return self._return_safe_or_abstain(
                    trace,
                    route_data,
                    summary,
                    safe_state,
                    [*candidates_a, *candidates_b],
                    "second_sample_runtime_failure",
                )

            # With no incumbent, spend the remaining third call on a compact
            # final-answer salvage instead of waiting on another long sample.
            remaining_calls = self.harness.budget.max_calls - self.harness.budget.calls_used
            remaining_tokens = self.harness.budget.total_tokens - self.harness.budget.requested_tokens
            salvage_tokens = min(
                int(getattr(self.harness.config, "arm_second_salvage_max_tokens", 2048)),
                max(0, remaining_tokens),
            )
            if (
                second_failure == "timeout"
                and remaining_calls > 0
                and salvage_tokens > 0
                and not self.should_finalize_now()
            ):
                summary["runtime_recovery_action"] = "second_timeout_compact_salvage"
                salvage_timeout = int(
                    getattr(self.harness.config, "arm_second_salvage_timeout_seconds", 90)
                )
                parsed_salvage, candidates_salvage = self._call(
                    "arm_v2_second_timeout_salvage",
                    ARM_COMPACT_SALVAGE_PROMPT,
                    problem,
                    salvage_tokens,
                    "off",
                    route,
                    source="arm_salvage",
                    timeout_seconds=salvage_timeout,
                )
                salvage_call = self._last_call_result
                self._record(STATE_CANDIDATE_B, parsed_salvage, candidates_salvage)
                self._record_parse(summary, "second_salvage_parse", parsed_salvage, candidates_salvage)
                if classify_runtime_failure(salvage_call) is None:
                    salvage_candidate, _salvage_decision = self._evaluate_one(
                        candidates_salvage, parsed_salvage, salvage_call
                    )
                    summary["candidate_b"] = self._candidate_summary(salvage_candidate)
                    summary["second_candidate"] = self._candidate_summary(salvage_candidate)
                    if self._checkpoint(salvage_candidate, parsed_salvage, safe_state, "candidate_b"):
                        summary["safe_candidate_source"] = safe_state.source
                        trace.append(
                            {
                                "method": "arm_harness_v2",
                                "stage": "safe_candidate_checkpoint",
                                "source": safe_state.source,
                                "checkpoint_stage": safe_state.checkpoint_stage,
                                "policy": "timeout_salvage",
                            }
                        )
                        return self._return_safe_or_abstain(
                            trace,
                            route_data,
                            summary,
                            safe_state,
                            [*candidates_a, *candidates_b, *candidates_salvage],
                            "second_timeout_salvage",
                        )
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
        best = self._best_candidate(primary_valid, secondary_valid)
        incumbent = safe_state.get()
        if incumbent is None:
            safe_state.update(
                best,
                source="candidate_a" if best is primary_valid else "candidate_b",
                confidence=best.trust_confidence,
                checkpoint_stage="pre_resolver",
            )
            incumbent = safe_state.get()
        else:
            incumbent.incumbent = True
            challenger = secondary_valid if incumbent is primary_valid else primary_valid
            challenger.candidate_role = "challenger"
            challenger.challenge_status = "pending"
            challenger.challenge_id = incumbent.candidate_id
            self.harness.ledger.update_candidate(incumbent)
            self.harness.ledger.update_candidate(challenger)
        trace.append(
            {
                "method": "arm_harness_v2",
                "stage": "safe_candidate_checkpoint",
                "source": safe_state.source,
                "checkpoint_stage": safe_state.checkpoint_stage,
                "policy": "incumbent_preserved",
            }
        )
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
        resolver_tokens = min(2_048, self.harness.budget.total_tokens - self.harness.budget.requested_tokens)
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
        decision, resolver_evidence = self._parse_resolver(resolver.content)
        summary["resolver_decision"] = decision
        summary["resolver"].update(
            {
                "candidate_a_value": primary_valid.normalized_value,
                "candidate_b_value": secondary_valid.normalized_value,
                "candidate_a_trust": primary_valid.trust_confidence,
                "candidate_b_trust": secondary_valid.trust_confidence,
                "resolver_decision": decision,
                "selected_source": f"candidate_{decision.lower()}" if decision in {"A", "B"} else None,
                "resolver_verdict": resolver_evidence,
            }
        )
        if decision == "A":
            selected = primary_valid
        elif decision == "B":
            selected = secondary_valid
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

    def _evaluate_one(self, candidates: Sequence[Candidate], parsed: Any, call_result: Any):
        """Annotate one candidate, collapsing only representation-equivalent duplicates."""
        values = list(candidates)
        if not values:
            return None, None
        unique = _unique_candidates(values)
        if len(unique) == 1:
            candidate = unique[0]
            if len(values) > 1:
                candidate.checks.append(
                    {"type": "same_response_consolidation", "candidate_count": len(values)}
                )
                candidate.reason_summary = "equivalent_candidates_collapsed"
        else:
            # Multiple genuinely distinct candidates are unresolved evidence,
            # not structurally invalid mathematics.  Preserve diagnostics but
            # do not let same-response alternatives masquerade as consensus.
            for candidate in values:
                valid, _reason = validate_candidate_shape(candidate, candidate.answer_type)
                candidate.structural_validity = "valid" if valid else "invalid"
                complete, complete_reason = assess_answer_completeness(
                    candidate,
                    answer_shape=self._current_route_contract.answer_shape,
                    parsed=parsed,
                )
                candidate.answer_complete = complete
                candidate.answer_complete_reason = complete_reason
                candidate.trust_confidence = "low"
                candidate.trust_reason = "same_response_conflict"
                self.harness.ledger.update_candidate(candidate)
            return None, None
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
    def _parse_resolver(response: str | None) -> tuple[str, str]:
        """Require a concrete targeted check before allowing candidate replacement."""
        lines = [line.strip() for line in (response or "").strip().splitlines() if line.strip()]
        check = next(
            (
                line.split(":", 1)[1].strip()
                for line in lines
                if line.upper().startswith("CHECK:") and ":" in line
            ),
            "",
        )
        decision = "UNKNOWN"
        for line in reversed(lines):
            match = __import__("re").fullmatch(
                r"(?:DECISION\s*[:：]\s*)?(A|B|UNKNOWN)",
                line,
                __import__("re").IGNORECASE,
            )
            if match:
                decision = match.group(1).upper()
                break
        concrete_check = bool(check) and check.casefold() not in {
            "insufficient",
            "unknown",
            "none",
            "n/a",
            "无法判断",
            "证据不足",
        }
        if decision in {"A", "B"} and not concrete_check:
            return "UNKNOWN", "missing_targeted_check"
        return decision, "targeted_check_present" if concrete_check else "insufficient_check"

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
