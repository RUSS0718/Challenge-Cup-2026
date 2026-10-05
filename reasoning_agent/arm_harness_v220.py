"""Opt-in answer-commit-first ARM v2.2 harness.

The official 2026-10-04 report recorded many length-terminated requests.  This
variant changes the first-call contract: the model must commit one parseable
answer before any optional checking text.  The second call remains the v2.1.4
CFR Challenger, so the experiment measures answer formation order without
adding a new post-hoc solver or changing the formal selector.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214


ARM_V220_ANSWER_COMMIT_PROMPT = """你是数学推理求解器。请独立解决原题并形成唯一、可判定的结论。

严格遵守以下输出顺序：
1. 第一行且只能第一行写：Final answer: <唯一最终答案>
2. 第一行之后最多写四行必要的极短核对；不得输出计划、Thinking Process、多个候选或第二个答案标记。
3. 如果无法可靠确定答案，第一行写：Final answer: UNKNOWN；不要猜测。

答案必须先提交，后续核对不得改写成另一个答案。"""


class AdaptiveReliabilityHarnessV220(AdaptiveReliabilityHarnessV214):
    """Commit a parseable answer before optional reasoning text."""

    def _primary_prompt(
        self,
        problem: str,
        route: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Use the answer-commit contract and expose its variant in telemetry."""
        summary["primary_prompt_variant"] = "answer_commit_first_v1"
        return super()._primary_prompt(problem, route, trace, summary)

    def _primary_base_prompt(self) -> str:
        """Return the answer-commit prompt instead of the final-line prompt."""
        return ARM_V220_ANSWER_COMMIT_PROMPT


__all__ = [
    "ARM_V220_ANSWER_COMMIT_PROMPT",
    "AdaptiveReliabilityHarnessV220",
]
