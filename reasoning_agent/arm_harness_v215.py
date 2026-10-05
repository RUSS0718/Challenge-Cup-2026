"""Opt-in bounded confirmation for explicit answers in truncated ARM tails.

This module extends v2.1.4 without changing its trust policy or official
selector. It only replaces the ordinary Challenger request when the primary
response was truncated after one structurally valid, explicitly marked answer.
All other candidates use the v2.1.4 path unchanged.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.harness_contracts import Candidate


ARM_V215_BOUNDED_TAIL_CONFIRMATION_PROMPT = """你是一个受限的答案确认器。

原题已经在上下文中。上一次求解在输出预算耗尽后留下了一个带明确 Final answer 标记的唯一候选。
把这个候选当作不可信假设，只检查它是否满足原题；不要复述推理，不要提出第二个候选。
如果候选正确，按原样返回；如果不正确或无法确认，返回 UNKNOWN。
严格只输出一行：Final answer: <完整答案>"""

ARM_V215_CONFIRMATION_MAX_TOKENS = 1_024


class AdaptiveReliabilityHarnessV215(AdaptiveReliabilityHarnessV214):
    """Run v2.1.4 with one narrow, fail-closed truncated-tail confirmation."""

    def __init__(self, harness: Any) -> None:
        """Bind the v2.1.4 state machine and clear confirmation-local state."""
        super().__init__(harness)
        self._tail_confirmation_active = False

    @staticmethod
    def _eligible_tail_candidate(primary: Candidate | None, summary: dict[str, Any]) -> bool:
        """Return whether the primary has a unique explicit answer tail."""
        if primary is None:
            return False
        if summary.get("primary_parse", {}).get("candidate_count") != 1:
            return False
        if not bool(summary.get("primary_parse", {}).get("truncated")):
            return False
        if getattr(primary, "source", "") != "arm_primary":
            return False
        if getattr(primary, "structural_validity", "") != "valid":
            return False
        if not bool(getattr(primary, "answer_complete", False)):
            return False
        if getattr(primary, "answer_complete_reason", "") != "answer_complete_truncated_tail":
            return False
        return bool(str(getattr(primary, "normalized_value", "") or "").strip())

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Confirm only an explicit truncated tail; otherwise delegate to v2.1.4."""
        if not self._eligible_tail_candidate(primary, summary):
            self._tail_confirmation_active = False
            return super()._second_call_plan(problem, route, primary, trace, summary)

        self._tail_confirmation_active = True
        value = str(getattr(primary, "normalized_value", "") or "").strip()
        summary["candidate_generation_b"] = {
            "backend": "bounded_tail_confirmation",
            "reasoning_mode": self.solver_mode,
            "max_tokens": ARM_V215_CONFIRMATION_MAX_TOKENS,
        }
        trace.append(
            {
                "method": "arm_harness_v215",
                "stage": "bounded_tail_confirmation",
                "status": "triggered",
                "candidate_shape": str(getattr(primary, "answer_type", "unknown")),
            }
        )
        prompt = (
            f"{ARM_V215_BOUNDED_TAIL_CONFIRMATION_PROMPT}\n\n"
            f"待确认候选：{value}"
        )
        return (
            "arm_v215_bounded_tail_confirmation",
            prompt,
            self.solver_mode,
            min(
                int(self.harness.config.tokens_for("attempt_b")),
                ARM_V215_CONFIRMATION_MAX_TOKENS,
            ),
        )

    def _evaluate_one(self, candidates: Any, parsed: Any, call_result: Any):
        """Reject an incomplete confirmation before pair agreement is computed."""
        candidate, decision = super()._evaluate_one(candidates, parsed, call_result)
        if (
            self._tail_confirmation_active
            and candidate is not None
            and getattr(candidate, "source", "") == "arm_second"
            and (decision is None or not bool(getattr(decision, "trusted", False)))
        ):
            candidate.answer_complete = False
            candidate.answer_complete_reason = "bounded_confirmation_untrusted"
            self.harness.ledger.update_candidate(candidate)
        return candidate, decision


__all__ = [
    "ARM_V215_BOUNDED_TAIL_CONFIRMATION_PROMPT",
    "ARM_V215_CONFIRMATION_MAX_TOKENS",
    "AdaptiveReliabilityHarnessV215",
]
