"""Minimal thinking-on candidate-first relay.

The relay keeps candidate formation separate from proof completion.  It uses
only the public ``client.chat(messages, temperature, max_tokens)`` contract,
has a three-call ceiling, and never treats missing proof as a protocol failure
when a single bounded candidate is already available.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
import unicodedata
from typing import Any, Callable


METHOD_ID = "adaptive_candidate_first_v1"
CANDIDATE_MAX_TOKENS = 2048
FOLLOWUP_MAX_TOKENS = 2048
ADJUDICATION_MAX_TOKENS = 4096
SOFT_DEADLINE_SECONDS = 600.0
HARD_DEADLINE_SECONDS = 900.0
MAX_PROBLEM_CHARS = 12_000
MAX_FRAGMENT_CHARS = 2_000
MAX_HINT_CHARS = 1_200
MAX_CANDIDATE_CHARS = 256

SHORT_CANDIDATE_PROMPT = """你是数学求解器。只求一个当前最可能的答案，不展开完整证明。
尽早输出且只输出一个标记：CANDIDATE: <答案>
随后最多写三行关键理由。没有可靠候选时写 CANDIDATE: UNKNOWN。
不要输出多个候选、长篇协议字段或 Thinking Process。"""

SECOND_CANDIDATE_PROMPT = """你是独立的数学复核求解器。使用与前一次不同的简短思路，
只给一个当前最可能的答案。尽早输出且只输出一个标记：CANDIDATE: <答案>
随后最多写三行关键理由。没有可靠候选时写 CANDIDATE: UNKNOWN。
不要复述前一次答案，不要输出多个候选或长篇证明。"""

RECOVERY_PROMPT = """你负责从一个可能被截断的解答片段中恢复答案。重新核对原题，
只输出一个标记：CANDIDATE: <答案>，随后最多写一句理由。
若无法可靠恢复，输出 CANDIDATE: UNKNOWN；不要继续长篇推导。"""

ADJUDICATION_PROMPT = """你是数学候选裁决器。比较给出的候选，回到原题核对，
只输出一行 FINAL: <唯一答案>，随后最多写三行依据。
若无法判定或候选都不可靠，输出 FINAL: UNKNOWN；不要输出多个 FINAL。"""

_MARKER_RE = re.compile(r"(?im)^\s*{marker}\s*[:：]\s*(.*?)\s*$")
_UNKNOWN_RE = re.compile(r"^(?:unknown|无法确定|不确定|未知|无答案)$", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]*>|\[[^\]]*(?:answer|答案|result|结果|option|选项)[^\]]*\])$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Parsed:
    values: tuple[str, ...]
    marker_count: int
    malformed: bool


def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value or "")
    if len(text) <= limit:
        return text
    marker = "\n...[片段省略]...\n"
    if limit <= len(marker):
        return text[:limit]
    head = (limit - len(marker) + 1) // 2
    tail = limit - len(marker) - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def _normalize(value: str) -> str:
    return "".join(unicodedata.normalize("NFC", value).split()).casefold()


def _valid_value(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > MAX_CANDIDATE_CHARS or _UNKNOWN_RE.fullmatch(value):
        return False
    if _PLACEHOLDER_RE.fullmatch(value):
        return False
    if value.rstrip().endswith(("\\", "=", "+", "-", "*", "/", "^", "(")):
        return False
    depth = 0
    for char in value:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _parse(response: str | None, marker: str) -> _Parsed:
    if not isinstance(response, str) or not response.strip():
        return _Parsed((), 0, True)
    pattern = _MARKER_RE.pattern.format(marker=re.escape(marker))
    matches = list(re.finditer(pattern, response))
    values: list[str] = []
    malformed = False
    for match in matches:
        value = match.group(1).strip()
        if _valid_value(value):
            values.append(value)
        else:
            malformed = True
    return _Parsed(tuple(values), len(matches), malformed or not matches)


def _distinct(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _normalize(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _error_category(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    if "rate" in name or "rate" in text or "429" in text:
        return "rate_limit"
    return "client_error"


@dataclass
class RelayResult:
    final_response: str
    extracted_answer: str
    trace: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_response": self.final_response,
            "extracted_answer": self.extracted_answer,
            "trace": self.trace,
        }


class AdaptiveCandidateFirstRelay:
    """Bounded candidate-first relay for an opt-in experiment."""

    def __init__(
        self,
        client: Any,
        *,
        temperature: float = 0.6,
        candidate_max_tokens: int = CANDIDATE_MAX_TOKENS,
        followup_max_tokens: int = FOLLOWUP_MAX_TOKENS,
        adjudication_max_tokens: int = ADJUDICATION_MAX_TOKENS,
        max_model_calls: int = 3,
        soft_deadline_seconds: float = SOFT_DEADLINE_SECONDS,
        hard_deadline_seconds: float = HARD_DEADLINE_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.candidate_max_tokens = int(candidate_max_tokens)
        self.followup_max_tokens = int(followup_max_tokens)
        self.adjudication_max_tokens = int(adjudication_max_tokens)
        self.max_model_calls = min(3, max(1, int(max_model_calls)))
        self.soft_deadline_seconds = float(soft_deadline_seconds)
        self.hard_deadline_seconds = float(hard_deadline_seconds)
        self.clock = clock or time.monotonic

    def solve(
        self,
        problem: str,
        problem_type: str = "",
        *,
        skill_hint: str = "",
        notebook_hint: str = "",
    ) -> dict[str, Any]:
        started = self.clock()
        calls = 0
        trace: list[dict[str, Any]] = []
        responses: list[str] = []
        candidates: list[str] = []
        prompt_context = self._context(problem, problem_type, skill_hint, notebook_hint)
        if skill_hint:
            trace.append({
                "method": METHOD_ID,
                "stage": "skill_hint",
                "status": "provided",
                "mode": "soft",
                "model_calls": 0,
                "hint_chars": min(len(skill_hint), MAX_HINT_CHARS),
            })

        first, calls = self._call(
            "candidate_1", SHORT_CANDIDATE_PROMPT, prompt_context,
            self.candidate_max_tokens, calls, started, trace,
        )
        if first:
            responses.append(first)
        parsed_first = _parse(first, "CANDIDATE")
        candidates.extend(parsed_first.values)
        first_distinct = _distinct(candidates)
        if first_distinct and len(first_distinct) == 1 and not parsed_first.malformed:
            source = "deterministic_agreement" if parsed_first.marker_count > 1 else "candidate_unproven"
            return self._result(first_distinct[0], source, trace, calls, first_distinct)

        parsed_second = _Parsed((), 0, True)
        if calls < self.max_model_calls:
            follow_prompt = SECOND_CANDIDATE_PROMPT
            if not candidates:
                follow_prompt = RECOVERY_PROMPT
            second, calls = self._call(
                "candidate_2", follow_prompt, prompt_context,
                self.followup_max_tokens, calls, started, trace,
                fragment=responses[-1] if responses else "",
            )
            if second:
                responses.append(second)
            parsed_second = _parse(second, "CANDIDATE")
            candidates.extend(parsed_second.values)

        distinct = _distinct(candidates)
        if len(distinct) == 1 and not parsed_second.malformed:
            source = "recovered_candidate" if not first_distinct else "deterministic_agreement"
            return self._result(distinct[0], source, trace, calls, distinct)

        if calls >= self.max_model_calls:
            return self._result("UNKNOWN", "unknown", trace, calls, distinct)

        if len(distinct) >= 2:
            prompt = self._adjudication_user_prompt(problem, distinct)
            adjudicated, calls = self._call(
                "adjudication", ADJUDICATION_PROMPT, prompt,
                self.adjudication_max_tokens, calls, started, trace,
            )
            parsed_final = _parse(adjudicated, "FINAL")
            final_values = _distinct(list(parsed_final.values))
            if len(final_values) == 1 and not parsed_final.malformed:
                return self._result(final_values[0], "adjudicated", trace, calls, distinct)
            return self._result("UNKNOWN", "adjudication_unknown", trace, calls, distinct)

        # No usable candidate after two attempts: spend the final bounded slot
        # on recovery with the latest response fragment, never on long resume.
        prompt = self._recovery_user_prompt(problem, responses[-1] if responses else "")
        recovered, calls = self._call(
            "recovery", RECOVERY_PROMPT, prompt,
            self.adjudication_max_tokens, calls, started, trace,
        )
        parsed_recovered = _parse(recovered, "CANDIDATE")
        recovered_values = _distinct(list(parsed_recovered.values))
        if len(recovered_values) == 1 and not parsed_recovered.malformed:
            return self._result(recovered_values[0], "recovered_candidate", trace, calls, recovered_values)
        return self._result("UNKNOWN", "unknown", trace, calls, recovered_values)

    def _context(self, problem: str, problem_type: str, skill_hint: str, notebook_hint: str) -> str:
        parts = [f"题目：\n{_clip(problem, MAX_PROBLEM_CHARS)}"]
        if problem_type:
            parts.append(f"题型：{_clip(problem_type, 64)}")
        if skill_hint:
            parts.append(f"建议路线（可采纳也可拒绝）：\n{_clip(skill_hint, MAX_HINT_CHARS)}")
        if notebook_hint:
            parts.append(f"冻结经验（仅供参考）：\n{_clip(notebook_hint, MAX_HINT_CHARS)}")
        return "\n\n".join(parts)

    @staticmethod
    def _recovery_user_prompt(problem: str, fragment: str) -> str:
        return (
            f"题目：\n{_clip(problem, MAX_PROBLEM_CHARS)}\n\n"
            f"截断片段（仅供参考）：\n{_clip(fragment, MAX_FRAGMENT_CHARS)}\n\n"
            "请只恢复一个候选答案。"
        )

    @staticmethod
    def _adjudication_user_prompt(problem: str, candidates: list[str]) -> str:
        values = "\n".join(f"候选{i}: {_clip(value, MAX_CANDIDATE_CHARS)}" for i, value in enumerate(candidates, 1))
        return f"题目：\n{_clip(problem, MAX_PROBLEM_CHARS)}\n\n候选账本：\n{values}"

    def _call(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        calls: int,
        started: float,
        trace: list[dict[str, Any]],
        *,
        fragment: str = "",
    ) -> tuple[str | None, int]:
        elapsed = self.clock() - started
        if elapsed >= self.hard_deadline_seconds or calls >= self.max_model_calls:
            trace.append({"method": METHOD_ID, "stage": stage, "status": "skipped", "reason": "hard_deadline_or_call_cap", "model_calls": calls, "max_tokens": max_tokens})
            return None, calls
        # The first call is always allowed to establish a candidate.  Once it
        # has consumed the soft budget, optional follow-ups stop; this keeps
        # the ladder bounded without treating the first slow response as an
        # infrastructure failure.
        if calls > 0 and elapsed >= self.soft_deadline_seconds:
            trace.append({"method": METHOD_ID, "stage": stage, "status": "skipped", "reason": "soft_deadline", "model_calls": calls, "max_tokens": max_tokens})
            return None, calls
        calls += 1
        if fragment and system_prompt == RECOVERY_PROMPT:
            user_prompt = (
                f"{user_prompt}\n\n截断片段（有界）：\n{_clip(fragment, MAX_FRAGMENT_CHARS)}"
            )
        try:
            response = self.client.chat(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # public client contract permits arbitrary exceptions
            trace.append({"method": METHOD_ID, "stage": stage, "status": "failed", "error_category": _error_category(exc), "model_calls": calls, "max_tokens": max_tokens})
            return None, calls
        if not isinstance(response, str) or not response.strip():
            trace.append({"method": METHOD_ID, "stage": stage, "status": "failed", "error_category": "invalid_response", "model_calls": calls, "max_tokens": max_tokens})
            return None, calls
        trace.append({"method": METHOD_ID, "stage": stage, "status": "ok", "model_calls": calls, "max_tokens": max_tokens, "finish_reason": "unavailable", "elapsed_bucket": "soft" if self.clock() - started >= self.soft_deadline_seconds else "normal"})
        return response.strip(), calls

    @staticmethod
    def _result(answer: str, source: str, trace: list[dict[str, Any]], calls: int, candidates: list[str]) -> dict[str, Any]:
        final = answer if answer and answer != "UNKNOWN" else "UNKNOWN"
        event = {
            "method": METHOD_ID,
            "stage": "finalize",
            "status": "ok" if final != "UNKNOWN" else "unknown",
            "source": source,
            "model_calls": calls,
            "candidate_values": [_clip(value, MAX_CANDIDATE_CHARS) for value in candidates[:5]],
            "candidate_unproven": source in {"candidate_unproven", "recovered_candidate", "deterministic_agreement"},
        }
        trace.append(event)
        return RelayResult(final, final if final != "UNKNOWN" else "", trace).as_dict()


__all__ = [
    "AdaptiveCandidateFirstRelay",
    "RelayResult",
    "METHOD_ID",
    "CANDIDATE_MAX_TOKENS",
    "FOLLOWUP_MAX_TOKENS",
    "ADJUDICATION_MAX_TOKENS",
    "SOFT_DEADLINE_SECONDS",
    "HARD_DEADLINE_SECONDS",
]
