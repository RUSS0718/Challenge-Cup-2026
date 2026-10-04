"""Opt-in structured confirmation for an existing ARM incumbent.

The v2.1.7 experiment changes only the second request: it asks a Challenger
to return a bounded JSON confirmation for the incumbent value.  A PASS is
accepted only when the reported value is equivalent to that incumbent;
FAIL, UNKNOWN, malformed JSON, and any new value remain fail-closed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.harness_contracts import (
    CANDIDATE_MISSING,
    CANDIDATE_PARSED,
    CANDIDATE_REJECTED,
    Candidate,
    ParsedResponse,
    value_equivalence,
)


ARM_V217_STRUCTURED_CONFIRMATION_PROMPT = """你是 Primary 候选的结构化 Challenger。

只检查原题是否支持给定的已有候选值。不要重新求解、不要提出替代答案、不要输出 Final answer
标记，也不要改变候选的表示形式。严格只输出一个 JSON 对象：
{"status":"PASS|FAIL|UNKNOWN","confirmed_value":"<原候选值>","checked_issue":"...","check_result":"..."}

只有在确实检查了原题并确认候选值时才使用 PASS；FAIL 表示发现具体错误；无法确认时使用
UNKNOWN。PASS 时 confirmed_value 必须逐字复述给定候选的值。"""

_STRUCTURED_CONFIRMATION_MAX_TOKENS = 1_024
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


class AdaptiveReliabilityHarnessV217(AdaptiveReliabilityHarnessV214):
    """Confirm an incumbent without allowing the Challenger to invent a value."""

    def __init__(self, harness: Any) -> None:
        """Bind the v2.1.4 state machine and clear confirmation state."""
        super().__init__(harness)
        self._confirmation_incumbent: Candidate | None = None

    @staticmethod
    def _parse_confirmation_payload(content: Any) -> dict[str, Any] | None:
        """Parse one bounded JSON object and reject answer-marker responses."""
        text = content if isinstance(content, str) else ""
        if not text or "final answer" in text.casefold() or "最终答案" in text:
            return None
        match = _JSON_OBJECT_RE.search(text[:4096])
        if match is None:
            return None
        try:
            payload = json.loads(match.group(0))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Use structured confirmation only when an incumbent already exists."""
        if primary is None:
            self._confirmation_incumbent = None
            return super()._second_call_plan(problem, route, primary, trace, summary)
        self._confirmation_incumbent = primary
        summary["candidate_generation_b"] = {
            "backend": "structured_challenger_confirmation",
            "reasoning_mode": self.solver_mode,
            "max_tokens": _STRUCTURED_CONFIRMATION_MAX_TOKENS,
            "incumbent_only": True,
        }
        trace.append(
            {
                "method": "arm_harness_v217",
                "stage": "structured_challenger_confirmation",
                "status": "triggered",
                "incumbent_only": True,
            }
        )
        value = str(getattr(primary, "normalized_value", "") or "").strip()
        prompt = (
            f"{ARM_V217_STRUCTURED_CONFIRMATION_PROMPT}\n\n"
            f"已有候选值：{value}"
        )
        return (
            "arm_v217_structured_confirmation",
            prompt,
            self.solver_mode,
            min(int(self.harness.config.tokens_for("attempt_b")), _STRUCTURED_CONFIRMATION_MAX_TOKENS),
        )

    def _call(
        self,
        stage: str,
        prompt: str,
        problem: str,
        max_tokens: int,
        reasoning_mode: Any,
        route: Any,
        *,
        source: str,
        timeout_seconds: int | None = None,
    ) -> tuple[Any, list[Candidate]]:
        """Parse a PASS as the incumbent value and all other statuses as no candidate."""
        parsed, candidates = super()._call(
            stage,
            prompt,
            problem,
            max_tokens,
            reasoning_mode,
            route,
            source=source,
            timeout_seconds=timeout_seconds,
        )
        if stage != "arm_v217_structured_confirmation":
            return parsed, candidates

        call_result = self._last_call_result
        payload = self._parse_confirmation_payload(getattr(call_result, "content", None))
        incumbent = self._confirmation_incumbent
        status = str((payload or {}).get("status", "UNKNOWN")).upper()
        confirmed_value = str((payload or {}).get("confirmed_value", "")).strip()
        is_pass = (
            status == "PASS"
            and incumbent is not None
            and bool(confirmed_value)
            and value_equivalence(confirmed_value, incumbent.value) == "EQUIVALENT"
        )
        if not is_pass:
            reason = (
                "structured_confirmation_unknown"
                if status == "UNKNOWN"
                else "structured_confirmation_rejected"
            )
            status_code = CANDIDATE_MISSING if status == "UNKNOWN" else CANDIDATE_REJECTED
            return (
                ParsedResponse(
                    [],
                    status_code,
                    getattr(parsed, "answer_type", getattr(incumbent, "answer_type", "unknown")),
                    bool(getattr(parsed, "truncated", False)),
                    reason,
                    getattr(call_result, "finish_reason", None),
                ),
                [],
            )

        candidate = Candidate(
            candidate_id="arm_second_pending",
            value=incumbent.value,
            normalized_value=incumbent.normalized_value,
            answer_type=incumbent.answer_type,
            source="arm_confirmation",
            extraction_status=CANDIDATE_PARSED,
            checks=[{"type": "structured_confirmation", "status": "PASS"}],
            reason_summary="structured_confirmation_pass",
            response=str(getattr(call_result, "content", "") or "")[:4096],
            reasoning_mode=reasoning_mode,
        )
        confirmed = ParsedResponse(
            [candidate],
            CANDIDATE_PARSED,
            incumbent.answer_type,
            bool(getattr(parsed, "truncated", False)),
            "structured_confirmation_pass",
            getattr(call_result, "finish_reason", None),
        )
        return confirmed, self.harness._new_candidates(confirmed, "arm_confirmation")


__all__ = [
    "ARM_V217_STRUCTURED_CONFIRMATION_PROMPT",
    "AdaptiveReliabilityHarnessV217",
]
