"""Opt-in compact finalization for incomplete or truncated ARM responses.

The v2.1.8 candidate targets the dominant official failure signal: a long
response reaches the output limit before a complete answer is emitted.  It
reuses the v2.1.4 trust and safe-candidate state machine, replacing only the
ordinary second sample when the primary response is missing, incomplete, or
truncated.  A complete primary response keeps the original v2.1.4 path.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.harness_contracts import Candidate


ARM_V218_COMPACT_FINALIZER_PROMPT = """你是数学答案收束器。

原题已经在上下文中。上一轮回答可能被截断、没有形成答案，或只留下不完整草稿。
请只做必要的最短计算，形成一个完整且唯一的结论。不要输出推理过程、计划、多个候选或解释。
如果无法可靠确定答案，只输出 UNKNOWN。
严格只输出一行：Final answer: <完整答案>"""

ARM_V218_COMPACT_FINALIZER_MAX_TOKENS = 2_048


class AdaptiveReliabilityHarnessV218(AdaptiveReliabilityHarnessV214):
    """Recover incomplete primary output with one bounded answer-only request."""

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Use compact finalization only when the primary cannot be trusted."""
        primary_parse = summary.get("primary_parse")
        primary_parse = primary_parse if isinstance(primary_parse, dict) else {}
        primary_incomplete = (
            primary is None
            or getattr(primary, "structural_validity", "") != "valid"
            or not bool(getattr(primary, "answer_complete", False))
        )
        primary_truncated = bool(primary_parse.get("truncated"))
        if not primary_incomplete and not primary_truncated:
            return super()._second_call_plan(problem, route, primary, trace, summary)

        draft = str(getattr(primary, "normalized_value", "") or "").strip()
        reason = "primary_missing" if primary is None else "primary_incomplete"
        if primary_truncated:
            reason = "primary_truncated"
        summary["candidate_generation_b"] = {
            "backend": "compact_finalizer",
            "reasoning_mode": "off",
            "max_tokens": ARM_V218_COMPACT_FINALIZER_MAX_TOKENS,
            "draft_present": bool(draft),
        }
        trace.append(
            {
                "method": "arm_harness_v218",
                "stage": "compact_finalizer",
                "status": "triggered",
                "reason": reason,
                "draft_present": bool(draft),
            }
        )
        prompt = ARM_V218_COMPACT_FINALIZER_PROMPT
        if draft:
            prompt = f"{prompt}\n\n不完整草稿（仅供修复，不要原样照抄）：{draft}"
        return (
            "arm_v218_compact_finalizer",
            prompt,
            "off",
            min(
                int(self.harness.config.tokens_for("attempt_b")),
                ARM_V218_COMPACT_FINALIZER_MAX_TOKENS,
            ),
        )


__all__ = [
    "ARM_V218_COMPACT_FINALIZER_MAX_TOKENS",
    "ARM_V218_COMPACT_FINALIZER_PROMPT",
    "AdaptiveReliabilityHarnessV218",
]
