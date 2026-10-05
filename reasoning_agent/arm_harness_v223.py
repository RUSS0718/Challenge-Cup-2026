"""Opt-in continuation of a partial Primary response for ARM v2.3.

This variant changes only the missing-candidate branch.  When the Primary
response contains a bounded text tail but the host parser found no candidate,
one continuation request receives that tail and is asked to finish the same
trajectory.  A complete incumbent still uses the unchanged v2.1.4 Challenger.
Raw Primary text is kept in process memory for the prompt only and is never
copied into trace telemetry.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.harness_contracts import Candidate


ARM_V223_PRIMARY_TAIL_CONTINUATION_PROMPT = """你是同一条 Primary 解题轨迹的受限续写器。

原题已经在宿主上下文中。Primary 的有限尾部如下；它可能在输出预算耗尽处结束，
也可能尚未写出可解析答案。请从尾部结束处继续必要的最短计算，不要重写长篇推理，
不要提出多个候选，也不要评价解析器。最后单独一行且必须使用：Final answer: <唯一答案>。
如果仍无法可靠形成唯一答案，只输出：Final answer: UNKNOWN。

Primary 输出尾部（仅供续写）："""

ARM_V223_CONTINUATION_MAX_TOKENS = 2_048
_TAIL_MAX_CHARS = 4_096
_TRUNCATION_FINISH_REASONS = frozenset(
    {"length", "max_tokens", "max_output_tokens", "truncated"}
)


class AdaptiveReliabilityHarnessV223(AdaptiveReliabilityHarnessV214):
    """Continue one partial no-candidate Primary response under a hard cap."""

    def _partial_primary_tail(
        self,
        primary: Candidate | None,
        summary: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Return a bounded raw tail and trigger reason when continuation is safe."""
        if primary is not None:
            return None
        parse = summary.get("primary_parse")
        parse = parse if isinstance(parse, dict) else {}
        if int(parse.get("candidate_count", 0) or 0) != 0:
            return None
        call_result = getattr(self, "_last_call_result", None)
        content = getattr(call_result, "content", None)
        if not isinstance(content, str):
            return None
        text = content.strip()
        if len(text) < 24 or text.casefold() in {"unknown", "无法确定", "无法完成"}:
            return None
        finish_reason = str(getattr(call_result, "finish_reason", "") or "").casefold()
        truncated = bool(parse.get("truncated")) or finish_reason in _TRUNCATION_FINISH_REASONS
        reason = "primary_truncated_partial" if truncated else "primary_text_without_candidate"
        return text[-_TAIL_MAX_CHARS:], reason

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Use one same-trajectory continuation only for a partial missing candidate."""
        partial = self._partial_primary_tail(primary, summary)
        if partial is None:
            return super()._second_call_plan(problem, route, primary, trace, summary)

        tail, reason = partial
        summary["candidate_generation_b"] = {
            "backend": "primary_tail_continuation",
            "stage": "arm_v223_primary_continuation",
            "reasoning_mode": self.solver_mode,
            "max_tokens": ARM_V223_CONTINUATION_MAX_TOKENS,
            "tail_chars": len(tail),
            "trigger_reason": reason,
        }
        trace.append(
            {
                "method": "arm_harness_v223",
                "stage": "primary_tail_continuation",
                "status": "triggered",
                "reason": reason,
                "tail_chars": len(tail),
            }
        )
        prompt = f"{ARM_V223_PRIMARY_TAIL_CONTINUATION_PROMPT}\n{tail}"
        return (
            "arm_v223_primary_continuation",
            prompt,
            self.solver_mode,
            min(
                int(self.harness.config.tokens_for("attempt_b")),
                ARM_V223_CONTINUATION_MAX_TOKENS,
            ),
        )


__all__ = [
    "ARM_V223_CONTINUATION_MAX_TOKENS",
    "ARM_V223_PRIMARY_TAIL_CONTINUATION_PROMPT",
    "AdaptiveReliabilityHarnessV223",
]
