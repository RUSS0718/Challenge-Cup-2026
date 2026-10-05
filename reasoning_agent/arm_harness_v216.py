"""Recover a missing ARM candidate with one independent bounded solve.

This opt-in variant fixes a control-plane mismatch in v2.1.4: when the
primary response contains no candidate, the second request must form an
answer instead of pretending to review an empty candidate. Existing
candidate, conflict, trust, and replacement rules remain unchanged.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.arm_v214_support import ARM_V21_SECOND_PROMPT
from reasoning_agent.harness_contracts import Candidate


ARM_V216_MISSING_CANDIDATE_PROMPT = """你是一个受限的数学答案形成器。

原题已经在上下文中。上一次求解没有形成可解析候选；请独立完成必要的最短计算，
不要复述长篇推理，不要假设或评价不存在的先前答案，也不要输出多个候选。
最后单独一行且必须使用：Final answer: <完整答案>"""


class AdaptiveReliabilityHarnessV216(AdaptiveReliabilityHarnessV214):
    """Use independent answer formation only when the primary is missing."""

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Select independent recovery for a missing candidate, else v2.1.4."""
        if primary is not None:
            return super()._second_call_plan(problem, route, primary, trace, summary)

        summary["candidate_generation_b"] = {
            "backend": "independent_missing_candidate_recovery",
            "reasoning_mode": self.solver_mode,
            "max_tokens": self.harness.config.tokens_for("attempt_b"),
        }
        trace.append(
            {
                "method": "arm_harness_v216",
                "stage": "missing_candidate_recovery",
                "status": "triggered",
                "reason": "primary_missing",
            }
        )
        return (
            "arm_v216_missing_candidate_recovery",
            ARM_V216_MISSING_CANDIDATE_PROMPT,
            self.solver_mode,
            self.harness.config.tokens_for("attempt_b"),
        )


__all__ = [
    "ARM_V216_MISSING_CANDIDATE_PROMPT",
    "AdaptiveReliabilityHarnessV216",
]
