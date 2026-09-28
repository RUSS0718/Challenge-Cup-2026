"""ARM-Harness v2: selective candidate verification under bounded compute."""

from __future__ import annotations

from typing import Any, Sequence

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
    value_equivalence,
)
from reasoning_agent.inference_policy import ComputePolicy, ReasoningMode
from reasoning_agent.math_harness import ATTEMPT_A_PROMPT, ATTEMPT_B_PROMPT, BudgetLedger
from reasoning_agent.runtime_policy import (
    RuntimeRecoveryPolicy,
    classify_runtime_failure,
)


ARM_COMPACT_SALVAGE_PROMPT = """请直接重新求解并尽快形成最终答案。

不要展开长证明，只保留必要计算。

最后一行：Final answer: <answer>"""

ARM_V2_RESOLVER_PROMPT = """给定同一道数学题的两个候选答案。

只能输出一行：A、B 或 UNKNOWN。
只能选择已有候选，不能生成第三个答案，也不要重新求解。"""


class AdaptiveReliabilityHarness(AdaptiveReasoningHarness):
    """Run ARM v2 trust gating, selective resampling, and bounded resolution."""

    def __init__(self, harness: Any) -> None:
        """Bind v2 policies to the existing parser, ledger, and scheduler seams."""
        super().__init__(harness)
        config = harness.config
        self.compute_policy = self._build_compute_policy(config)
        self.trust_policy = CandidateTrustPolicy()
        self.runtime_policy = RuntimeRecoveryPolicy(
            config.arm_timeout_recovery_mode,
            salvage_max_tokens=config.arm_salvage_max_tokens,
            salvage_timeout_seconds=config.arm_salvage_timeout_seconds,
        )

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
        """Allocate extra calls only after the primary candidate fails the trust gate."""
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
        for event in trace:
            if event.get("stage") == "route":
                event.update(target="harness", lane=route_data["lane"], arm_lane="v2")

        summary: dict[str, Any] = {
            "method": "arm_harness_v2",
            "stage": "arm_v2_summary",
            "profile": self.harness.config.arm_v2_mode,
            "early_stop": False,
            "second_sample_triggered": False,
            "agreement": False,
            "conflict": False,
            "resolver_triggered": False,
            "runtime_recovery_action": None,
            "final_source": None,
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
            }
        )
        self.harness.ledger.transition("arm_v2_policy", reason=self.harness.config.arm_v2_mode)

        primary_timeout = self.harness.config.arm_primary_timeout_seconds
        if self.harness.config.arm_v2_mode == "long_timeout" and primary_timeout is None:
            primary_timeout = 60
        self.harness.ledger.transition(STATE_ATTEMPT_A)
        parsed_a, candidates_a = self._call(
            "arm_v2_primary",
            ATTEMPT_A_PROMPT,
            problem,
            self.harness.config.tokens_for("attempt_a"),
            "off",
            route,
            source="arm_primary",
            timeout_seconds=primary_timeout,
        )
        call_a = self._last_call_result
        self._record(STATE_CANDIDATE_A, parsed_a, candidates_a)

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
            )
            if classify_runtime_failure(call_a) is not None:
                trace.append(summary)
                return self.harness._abstain(trace, route_data, "runtime_recovery_failed")

        primary, primary_decision = self._evaluate_one(candidates_a, parsed_a, call_a)
        summary["candidate_a"] = self._candidate_summary(primary)
        if primary_decision is not None and primary_decision.trusted:
            summary["early_stop"] = True
            summary["final_source"] = "candidate_a"
            trace.append(summary)
            return self.harness._select(
                trace,
                route_data,
                primary,
                candidates_a,
                "arm_v2_trusted_primary",
                problem=problem,
            )

        if not policy.allow_second_sample:
            summary["final_source"] = "abstain_untrusted"
            trace.append(summary)
            return self.harness._abstain(trace, route_data, "candidate_untrusted")

        summary["second_sample_triggered"] = True
        self.harness.ledger.transition(STATE_ATTEMPT_B, reason="candidate_trust_gate")
        parsed_b, candidates_b = self._call(
            "arm_v2_second_sample",
            ATTEMPT_B_PROMPT,
            problem,
            self.harness.config.tokens_for("attempt_b"),
            "off",
            route,
            source="arm_second",
            timeout_seconds=primary_timeout,
        )
        call_b = self._last_call_result
        self._record(STATE_CANDIDATE_B, parsed_b, candidates_b)
        if classify_runtime_failure(call_b) is not None:
            summary["final_source"] = "runtime_failure"
            trace.append(summary)
            return self.harness._abstain(trace, route_data, "second_sample_runtime_failure")

        secondary, secondary_decision = self._evaluate_one(candidates_b, parsed_b, call_b)
        summary["candidate_b"] = self._candidate_summary(secondary)
        primary_valid = primary if primary is not None and primary.structural_validity == "valid" else None
        secondary_valid = secondary if secondary is not None and secondary.structural_validity == "valid" else None
        if primary_valid is None and secondary_decision is not None and secondary_decision.trusted:
            summary["final_source"] = "candidate_b"
            trace.append(summary)
            return self.harness._select(
                trace,
                route_data,
                secondary_valid,
                candidates_b,
                "arm_v2_trusted_second_sample",
                problem=problem,
            )
        if primary_valid is None or secondary_valid is None:
            summary["final_source"] = "abstain_no_two_candidates"
            trace.append(summary)
            return self.harness._abstain(trace, route_data, "second_sample_incomplete")

        relation = value_equivalence(primary_valid.value, secondary_valid.value)
        if relation == "EQUIVALENT":
            for candidate in (primary_valid, secondary_valid):
                candidate.verification_status = "consensus_supported"
                candidate.extraction_status = "verified"
                candidate.trust_confidence = "high"
                candidate.trust_reason = "independent_agreement"
                self.harness.ledger.update_candidate(candidate)
            summary["agreement"] = True
            summary["final_source"] = "candidate_b"
            trace.append(summary)
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
            summary["final_source"] = "abstain_conflict"
            trace.append(summary)
            return self.harness._abstain(trace, route_data, "arm_v2_conflict_unresolved")

        self.harness.ledger.transition(STATE_CONFLICT, reason="arm_v2_candidate_conflict")
        self.harness.ledger.add_conflict([primary_valid, secondary_valid])
        self.harness.ledger.transition(STATE_CRITIC, reason="arm_v2_conflict")
        summary["resolver_triggered"] = True
        resolver_tokens = min(1_024, self.harness.budget.total_tokens - self.harness.budget.requested_tokens)
        resolver = self.harness.scheduler.call(
            "arm_v2_resolver",
            ARM_V2_RESOLVER_PROMPT,
            self.harness._critic_prompt(problem, [primary_valid, secondary_valid]),
            resolver_tokens,
            reasoning_mode="off",
        )
        decision = self._parse_resolver(resolver.content)
        summary["resolver_decision"] = decision
        if decision == "A":
            selected = primary_valid
        elif decision == "B":
            selected = secondary_valid
        else:
            summary["final_source"] = "abstain_resolver_unknown"
            trace.append(summary)
            return self.harness._abstain(trace, route_data, "arm_v2_resolver_unknown")
        selected.verification_status = "bounded_resolver"
        selected.trust_confidence = "medium"
        selected.trust_reason = "bounded_resolver_selected"
        self.harness.ledger.update_candidate(selected)
        summary["final_source"] = f"candidate_{decision.lower()}"
        trace.append(summary)
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
            else ATTEMPT_A_PROMPT
        )
        recovered_parsed, recovered_candidates = self._call(
            "arm_v2_runtime_recovery",
            prompt,
            problem,
            decision.max_tokens,
            "off",
            route,
            source="arm_salvage" if decision.action == "compact_salvage" else "arm_runtime_retry",
            timeout_seconds=decision.timeout_seconds,
        )
        recovered_call = self._last_call_result
        self._record(STATE_CANDIDATE_A, recovered_parsed, recovered_candidates)
        return recovered_parsed, recovered_candidates, recovered_call

    def _evaluate_one(self, candidates: Sequence[Candidate], parsed: Any, call_result: Any):
        """Annotate one candidate with structural and trust metadata."""
        if len(candidates) != 1:
            for candidate in candidates:
                candidate.structural_validity = "invalid"
                candidate.trust_confidence = "low"
                candidate.trust_reason = "multiple_candidates"
                self.harness.ledger.update_candidate(candidate)
            return None, None
        candidate = candidates[0]
        valid, _reason = validate_candidate_shape(candidate, candidate.answer_type)
        candidate.structural_validity = "valid" if valid else "invalid"
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
        if first in {"SELECT: A", "SELECT: B"}:
            return first[-1]
        return "UNKNOWN"

    @staticmethod
    def _candidate_summary(candidate: Candidate | None) -> dict[str, Any] | None:
        """Return bounded candidate telemetry for the result trace."""
        if candidate is None:
            return None
        return {
            "value": str(candidate.normalized_value or candidate.value)[:256],
            "valid": candidate.structural_validity == "valid",
            "trust": candidate.trust_confidence,
            "trust_reason": candidate.trust_reason[:240],
        }


def policy_name(mode: str) -> str:
    """Name the v2 compute lane without exposing a new host route."""
    return f"v2_{mode}"


__all__ = ["AdaptiveReliabilityHarness", "ARM_COMPACT_SALVAGE_PROMPT", "ARM_V2_RESOLVER_PROMPT"]
