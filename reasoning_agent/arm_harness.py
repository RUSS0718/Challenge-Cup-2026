"""Run one bounded ARM solve on top of the existing math-harness seams."""

from __future__ import annotations

from typing import Any, Sequence

from reasoning_agent.harness_contracts import (
    ANSWER_SHAPE_SINGLE_NUMERIC,
    ANSWER_SHAPE_UNKNOWN,
    CANDIDATE_CONFLICT,
    HostParser,
    TypedParser,
    _unique_candidates,
    value_equivalence,
)
from reasoning_agent.inference_policy import (
    ReasoningMode,
    ReasoningModePolicy,
    candidate_is_stable,
    should_escalate,
)
from reasoning_agent.math_harness import (
    ATTEMPT_A_PROMPT,
    ATTEMPT_B_PROMPT,
    CRITIC_PROMPT,
    DEEP_PRIMARY_PROMPT,
    DEEP_REVIEW_PROMPT,
    BudgetLedger,
    STATE_ATTEMPT_A,
    STATE_ATTEMPT_B,
    STATE_CANDIDATE_A,
    STATE_CANDIDATE_B,
    STATE_CONFLICT,
    STATE_CRITIC,
)


ARM_ESCALATION_PROMPT = """你是深度数学求解器。

此前快速求解未形成可靠最终候选。请从原题重新独立求解，重点处理关键推导与约束。
不要讨论此前失败。形成唯一答案后立即结束。

最后一行：Final answer: <answer>"""


class AdaptiveReasoningHarness:
    """Apply lane policy while reusing the host ledger, parser, and call budget."""

    def __init__(self, harness: Any) -> None:
        """Bind the existing orchestrator and freeze its ARM settings."""
        self.harness = harness
        config = harness.config
        self.policy = ReasoningModePolicy(
            allow_thinking_on=config.arm_allow_thinking_on,
            default_lane=config.arm_default_lane,
            fast_max_calls=config.arm_fast_max_calls,
            adaptive_max_calls=config.arm_adaptive_max_calls,
            deep_max_calls=config.arm_deep_max_calls,
            fast_token_budget=config.arm_fast_token_budget,
            adaptive_token_budget=config.arm_adaptive_token_budget,
            deep_token_budget=config.arm_deep_token_budget,
        )

    def solve(self, problem: str, route: Any, prefix_trace: list[dict[str, Any]]) -> dict[str, Any]:
        """Solve through OFF-first calls, escalating only on unresolved evidence."""
        policy = self.policy.plan(route.contract, route.answer_type)
        self.harness.budget = BudgetLedger(
            max_calls=policy.max_calls,
            total_tokens=policy.token_budget,
            clock=self.harness.clock,
        )
        trace = list(prefix_trace)
        route_data = route.as_dict()
        route_data.update(target="harness", lane=policy.lane, arm_lane=policy.lane)
        for event in trace:
            if event.get("stage") == "route":
                event.update(target="harness", lane=policy.lane, arm_lane=policy.lane)
        trace.append(
            {
                "method": "arm_harness_v1",
                "stage": "arm_policy",
                "host_lane": route.lane,
                "lane": policy.lane,
                "initial_mode": policy.initial_mode,
                "escalation_mode": policy.escalation_mode,
                "max_calls": policy.max_calls,
                "token_budget": policy.token_budget,
                "reason": policy.reason,
            }
        )
        self.harness.ledger.transition("arm_policy", reason=policy.reason)

        first_mode = policy.initial_mode
        first_stage = "arm_primary" if policy.lane != "deep_on" else "arm_deep_primary"
        first_prompt = DEEP_PRIMARY_PROMPT if policy.lane == "deep_on" else ATTEMPT_A_PROMPT
        first_tokens = self.harness.config.tokens_for(
            "deep_primary" if policy.lane == "deep_on" else "attempt_a"
        )
        self.harness.ledger.transition(STATE_ATTEMPT_A)
        first = self._call(
            first_stage,
            first_prompt,
            problem,
            first_tokens,
            first_mode,
            route,
            source="arm_primary",
        )
        first_parsed, first_candidates = first
        self._record(STATE_CANDIDATE_A, first_parsed, first_candidates)

        if candidate_is_stable(first_parsed, first_candidates):
            trace.append(self._not_needed_trace())
            return self.harness._select(
                trace,
                route_data,
                first_candidates[0],
                first_candidates,
                "arm_candidate_first",
                problem=problem,
            )

        if policy.lane == "deep_on":
            # The Always-ON arm is one solver call followed, if needed, by an
            # OFF review; it never chains multiple ON solve calls.
            if not first_candidates:
                trace.append({"method": "arm_harness_v1", "stage": "arm_escalation", "status": "not_needed"})
                return self.harness._abstain(trace, route_data, "no_extractable_candidate")
            second_mode: ReasoningMode = "off"
            second_stage = "arm_off_review"
            second_prompt = DEEP_REVIEW_PROMPT
            second_tokens = self.harness.config.tokens_for("deep_review")
            escalation_reason = "candidate_unresolved"
        else:
            should_run, escalation_reason = should_escalate(
                parsed=first_parsed,
                candidates=first_candidates,
                call_result=self._last_call_result,
                budget=self.harness.budget,
            )
            if not should_run:
                trace.append(self._not_needed_trace(escalation_reason))
                if first_candidates:
                    return self.harness._select(
                        trace,
                        route_data,
                        first_candidates[0],
                        first_candidates,
                        "arm_budget_limited_candidate",
                        problem=problem,
                    )
                return self.harness._abstain(trace, route_data, escalation_reason)
            second_mode = policy.escalation_mode or "off"
            second_stage = "arm_escalation" if second_mode == "on" else "arm_recovery"
            second_prompt = ARM_ESCALATION_PROMPT if second_mode == "on" else ATTEMPT_B_PROMPT
            second_tokens = self.harness.config.tokens_for(
                "deep_primary" if second_mode == "on" else "attempt_b"
            )

        trace.append(
            {
                "method": "arm_harness_v1",
                "stage": "arm_escalation",
                "status": "triggered",
                "from": first_mode,
                "to": second_mode,
                "reason": escalation_reason,
            }
        )
        self.harness.ledger.transition(STATE_ATTEMPT_B, reason=escalation_reason)
        second_parsed, second_candidates = self._call(
            second_stage,
            second_prompt,
            problem,
            second_tokens,
            second_mode,
            route,
            source="arm_second",
        )
        self._record(STATE_CANDIDATE_B, second_parsed, second_candidates)
        all_candidates = [*first_candidates, *second_candidates]
        unique = _unique_candidates(all_candidates)

        if len(unique) == 1:
            matching = [
                candidate
                for candidate in all_candidates
                if value_equivalence(candidate.value, unique[0].value) == "EQUIVALENT"
            ]
            if len(matching) > 1:
                for candidate in matching:
                    candidate.verification_status = "verified"
                    candidate.extraction_status = "verified"
                    self.harness.ledger.update_candidate(candidate)
            return self.harness._select(
                trace,
                route_data,
                unique[0],
                all_candidates,
                "arm_independent_agreement" if len(matching) > 1 else "arm_single_candidate",
                problem=problem,
            )

        if len(unique) > 1 and self.harness.budget.calls_used < self.harness.budget.max_calls:
            self.harness.ledger.transition(STATE_CONFLICT, reason="arm_candidate_conflict")
            self.harness.ledger.add_conflict(unique)
            trace.append(
                {
                    "method": "arm_harness_v1",
                    "stage": "arm_conflict_check",
                    "status": "deterministic_unresolved",
                    "candidate_ids": [item.candidate_id for item in unique],
                }
            )
            self.harness.ledger.transition(STATE_CRITIC, reason="arm_conflict")
            critic = self.harness.scheduler.call(
                "arm_critic",
                CRITIC_PROMPT,
                self.harness._critic_prompt(problem, unique),
                self.harness.config.tokens_for("critic"),
                reasoning_mode="off",
            )
            decision, selected, _reason = self.harness._parse_critic(critic.content, unique)
            if decision == "select" and selected is not None:
                selected.verification_status = "selected_by_bounded_critic"
                self.harness.ledger.update_candidate(selected)
                return self.harness._select(
                    trace,
                    route_data,
                    selected,
                    all_candidates,
                    "arm_bounded_critic",
                    problem=problem,
                )
            return self.harness._abstain(trace, route_data, "arm_conflict_unresolved")

        reason = "arm_conflict_unresolved" if unique else "no_extractable_candidate"
        return self.harness._abstain(trace, route_data, reason)

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
    ) -> tuple[Any, list[Any]]:
        """Run and parse one call while attaching its selected mode to candidates."""
        contract = route.contract.as_dict()
        call_result = self.harness.scheduler.call(
            stage,
            prompt,
            "题目：\n"
            f"{problem}\n\n答案形状：{contract['answer_shape']}；"
            f"推理风险：{contract['reasoning_risk']}；路由置信度：{contract['route_confidence']}。\n"
            "请形成唯一答案。",
            max_tokens,
            reasoning_mode=reasoning_mode,
            timeout_seconds=timeout_seconds,
        )
        self._last_call_result = call_result
        if route.contract.answer_shape in {ANSWER_SHAPE_SINGLE_NUMERIC, ANSWER_SHAPE_UNKNOWN}:
            parsed = HostParser().parse(
                call_result.content,
                problem=problem,
                source=source,
                finish_reason=call_result.finish_reason,
            )
            candidates = self.harness._new_candidates(parsed, source)
        else:
            parsed = TypedParser().parse(
                call_result.content,
                route.contract,
                finish_reason=call_result.finish_reason,
            )
            candidates = [parsed.candidate] if parsed.candidate is not None else []
            for candidate in candidates:
                candidate.candidate_id = f"{source}_{self.harness._next_candidate_number}"
                candidate.source = source
                self.harness._next_candidate_number += 1
        for candidate in candidates:
            candidate.reasoning_mode = reasoning_mode
        return parsed, candidates

    def _record(self, state: str, parsed: Any, candidates: Sequence[Any]) -> None:
        """Append compact parser and candidate evidence to the solve ledger."""
        self.harness.ledger.transition(state, reason=getattr(parsed, "reason_summary", getattr(parsed, "reason", "")))
        self.harness.ledger.add_candidates(candidates)
        if len(candidates) > 1 or getattr(parsed, "status", None) == CANDIDATE_CONFLICT:
            self.harness.ledger.add_conflict(candidates)

    @staticmethod
    def _not_needed_trace(reason: str = "candidate_stable") -> dict[str, Any]:
        """Describe the early-stop decision without a model call."""
        return {
            "method": "arm_harness_v1",
            "stage": "arm_escalation",
            "status": "not_needed",
            "reason": reason,
        }
