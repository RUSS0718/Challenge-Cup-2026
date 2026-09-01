"""Bounded Typed Consensus Solver (BTCS; Frame v2 is the current candidate).

The module owns the protocol state machine so the legacy runtime does not
grow another collection of protocol-specific branches.  Model output is
parsed into typed packets, consensus is decided locally, and the arbiter can
only point at an existing packet.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from user_agent import (
    _is_placeholder_segment,
    _truncation_signals,
    answer_equivalence,
    is_placeholder_answer,
    normalize_answer,
    reconstruct_final_response_f,
    TASK_TYPE_CALCULATION,
    TASK_TYPE_CHOICE,
    TASK_TYPE_FILL_BLANK,
    _NON_NUMERIC_TASK_TYPES,
)


BTCS_CONTINUATION_PROMPT = """你是 BTCS 答案帧恢复器。只能根据已有解答前缀确认答案，禁止从截断文本捞裸数字或猜测。
严格输出一行：FINAL: <明确答案>；无法确认时严格输出：FINAL: UNKNOWN。
不要输出其它内容。"""

BTCS_FRAME_V2_DIRECT_PROMPT = """你是 BTCS Frame v2 结构化数学求解器。独立解决题目，并把答案放在推理之前。
数值、选择、填空题严格只输出一行：FINAL: <唯一最终答案>
证明、推导、解释题严格输出：
FINAL: <唯一最终结论>
EVIDENCE: <一句关键依据>
BODY:
<完整而紧凑的正文>
不要输出 Thinking Process、计划、格式示例或其它内容；无法确定时输出 FINAL: UNKNOWN。"""

BTCS_FRAME_V2_INDEPENDENT_PROMPT = """你是 BTCS Frame v2 独立求解器。不要参考其它候选，独立计算或反向核对题目。
数值、选择、填空题只输出一行 FINAL: <唯一最终答案>。
证明、推导、解释题输出 FINAL、EVIDENCE 和 BODY 三个字段，答案必须先出现。
禁止裸数字兜底、猜测、Thinking Process 和其它格式；无法确定时输出 FINAL: UNKNOWN。"""

BTCS_FRAME_V2_ARBITER_PROMPT = """你是 BTCS Frame v2 受限裁决器。只能在候选 A、B、C 中选择，不能创造、改写或补全答案。
数值候选只含 FINAL；证明、推导、解释候选含 FINAL 与 EVIDENCE。
严格输出一行：SELECT: A、SELECT: B、SELECT: C 或 SELECT: UNKNOWN。
无法判断时输出 SELECT: UNKNOWN；不要输出其它内容。"""


_NUMERIC_TASK_TYPES = frozenset(
    {TASK_TYPE_CALCULATION, TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK}
)
_PROOF_HEADERS = {
    "proof": "证明",
    "derivation": "推导",
    "explanation": "解释",
}
_FINAL_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:FINAL|最终答案|Final\s+answer|答案)"
    r"\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_LEGACY_INLINE_FINAL_RE = re.compile(
    r"(?:最终答案|Final\s+answer)\s*[:：]\s*(.+)$", re.IGNORECASE
)
_EVIDENCE_LINE_RE = re.compile(
    r"^\s*EVIDENCE\s*[:：]\s*(.*?)\s*$", re.IGNORECASE
)
_BODY_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:BODY|证明|推导|解释|Derivation|Proof|Explanation)"
    r"(?:\s*(?:块|Block))?\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_SELECT_LINE_RE = re.compile(r"^\s*SELECT\s*:\s*(A|B|C|UNKNOWN)\s*$", re.IGNORECASE)
_RETRYABLE_CATEGORIES = frozenset(
    {"rate_limit", "timeout", "service_unavailable", "temporarily_unavailable"}
)
_PACKET_DIAGNOSTIC_KEYS = (
    "accepted",
    "no_final",
    "unknown_final",
    "placeholder_final",
    "conflicting_final",
    "missing_body",
)


@dataclass
class SolveBudget:
    """Per-solve BTCS accounting; no field is shared between solves."""

    max_logical_calls: int = 4
    max_http_attempts: int = 5
    solver_max_tokens: int = 4096
    arbiter_max_tokens: int = 256
    continuation_max_tokens: int = 256
    retry_limit: int = 1
    retry_base_delay_seconds: float = 0.25
    temperature: float = 0.6
    frame_version: str = "v2"
    logical_calls: int = 0
    http_attempts: int = 0
    retries: int = 0
    halted: bool = False
    solver_requests: int = 0
    parsed_solver_packets: int = 0
    packet_diagnostics: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in _PACKET_DIAGNOSTIC_KEYS}
    )

    def __post_init__(self) -> None:
        # The protocol's hard ceilings cannot be raised by a caller config.
        self.max_logical_calls = min(4, max(0, int(self.max_logical_calls)))
        self.max_http_attempts = min(5, max(0, int(self.max_http_attempts)))
        self.solver_max_tokens = max(1, int(self.solver_max_tokens))
        self.arbiter_max_tokens = max(1, int(self.arbiter_max_tokens))
        self.continuation_max_tokens = max(1, int(self.continuation_max_tokens))
        self.retry_limit = min(1, max(0, int(self.retry_limit)))
        self.retry_base_delay_seconds = max(0.0, float(self.retry_base_delay_seconds))
        if self.frame_version != "v2":
            raise ValueError("BTCS main backport only supports frame v2")

    @classmethod
    def from_config(cls, config: Any) -> "SolveBudget":
        return cls(
            max_logical_calls=getattr(config, "btcs_max_model_calls", 4),
            max_http_attempts=5,
            solver_max_tokens=getattr(config, "btcs_solver_max_tokens", 4096),
            arbiter_max_tokens=getattr(config, "btcs_arbiter_max_tokens", 256),
            continuation_max_tokens=getattr(config, "btcs_continuation_max_tokens", 256),
            retry_limit=getattr(config, "btcs_retry_limit", 1),
            retry_base_delay_seconds=getattr(
                config, "btcs_retry_base_delay_seconds", 0.25
            ),
            temperature=getattr(config, "policy_temperature", 0.6),
            frame_version="v2",
        )


@dataclass
class CandidatePacket:
    """A parsed candidate; ``raw_response`` never enters trace output."""

    candidate_id: str
    source: str
    answer: str
    normalized_answer: str
    evidence: str = ""
    body: str = ""
    raw_response: str = ""
    body_complete: bool = False
    truncation_signals: tuple[str, ...] = ()


@dataclass
class ProtocolResult:
    final_response: str
    extracted_answer: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    logical_calls: int = 0
    http_attempts: int = 0
    packet_diagnostics: dict[str, int] = field(default_factory=dict)
    per_solve_final_success: bool = False
    raw_packet_parse_rate: float = 0.0
    selection_source: str = "none"


class PacketParser:
    """Parse only explicit answer frames and required proof bodies."""

    def parse(
        self,
        response: str | None,
        problem_type: str,
        candidate_id: str = "A",
        source: str = "direct",
        frame_version: str = "v2",
    ) -> CandidatePacket | None:
        packet, _ = self.parse_with_reason(
            response,
            problem_type,
            candidate_id=candidate_id,
            source=source,
            frame_version=frame_version,
        )
        return packet

    def parse_with_reason(
        self,
        response: str | None,
        problem_type: str,
        *,
        candidate_id: str,
        source: str,
        frame_version: str = "v2",
    ) -> tuple[CandidatePacket | None, str]:
        if not isinstance(response, str) or not response.strip():
            return None, "empty_response"

        lines = self._frame_lines(response, frame_version)
        if lines is None:
            return None, "no_final"
        final_matches = [
            (index, match)
            for index, line in enumerate(lines)
            if (match := _FINAL_LINE_RE.match(line)) is not None
        ]
        if not final_matches and frame_version != "v2":
            # Legacy responses sometimes put the explicit marker after a
            # short preamble.  This still requires an answer marker; it never
            # falls back to a bare number or the last line.
            final_matches = [
                (index, match)
                for index, line in enumerate(lines)
                if (match := _LEGACY_INLINE_FINAL_RE.search(line)) is not None
            ]
        if not final_matches:
            return None, "no_final"
        if frame_version == "v2" and len(final_matches) != 1:
            return None, "conflicting_final"

        values: list[str] = []
        for _, match in final_matches:
            value = match.group(1).strip()
            if not value or value.upper() == "UNKNOWN":
                return None, "unknown_final"
            if is_placeholder_answer(value) or _is_placeholder_segment(value):
                return None, "placeholder_final"
            values.append(value)

        answer = values[0]
        if any(
            answer_equivalence(answer, other) != "EQUIVALENT"
            for other in values[1:]
        ):
            return None, "conflicting_final"

        final_index = final_matches[0][0]
        if frame_version == "v2" and any(
            line.strip() for line in lines[:final_index]
        ):
            return None, "no_final"
        evidence = ""
        body = ""
        body_header_found = False
        body_start = len(lines)
        body_index = len(lines)
        for index in range(final_index + 1, len(lines)):
            evidence_match = _EVIDENCE_LINE_RE.match(lines[index])
            if evidence_match and not evidence:
                evidence = evidence_match.group(1).strip()
                if _is_placeholder_segment(evidence):
                    return None, "placeholder_evidence"
                continue
            body_match = _BODY_LINE_RE.match(lines[index])
            if body_match:
                body_header_found = True
                body_index = index
                head_rest = body_match.group(1).strip()
                body_start = index + 1
                body_lines = ([head_rest] if head_rest else []) + lines[body_start:]
                body = "\n".join(body_lines).strip()
                break

        signals = tuple(
            signal
            for signal in _truncation_signals(response, answer)
            if signal != "no_extractable_answer"
        )
        if problem_type in _NON_NUMERIC_TASK_TYPES:
            if not body_header_found or not body:
                return None, "missing_body"
            if _is_placeholder_segment(body):
                return None, "placeholder_body"
            if frame_version == "v2":
                if any(
                    line.strip()
                    and not _EVIDENCE_LINE_RE.match(line)
                    for line in lines[final_index + 1:body_index]
                ):
                    return None, "no_final"
            if frame_version == "v2" and (
                not evidence or evidence.upper() == "UNKNOWN"
            ):
                return None, "missing_evidence"
            body_complete = not signals
        else:
            if frame_version == "v2":
                nonempty_lines = [line for line in lines if line.strip()]
                if (
                    len(nonempty_lines) != 1
                    or _FINAL_LINE_RE.match(nonempty_lines[0]) is None
                ):
                    return None, "no_final"
            body_complete = True

        return (
            CandidatePacket(
                candidate_id=candidate_id,
                source=source,
                answer=answer,
                normalized_answer=normalize_answer(answer),
                evidence=evidence,
                body=body,
                raw_response=response,
                body_complete=body_complete,
                truncation_signals=signals,
            ),
            "accepted",
        )

    @staticmethod
    def _frame_lines(response: str, frame_version: str) -> list[str] | None:
        if frame_version != "v2":
            return response.splitlines()
        lines = response.strip().splitlines()
        if lines and lines[0].strip().startswith("```"):
            if len(lines) < 2 or lines[-1].strip() != "```":
                return None
            lines = lines[1:-1]
        normalized: list[str] = []
        for line in lines:
            candidate = re.sub(
                r"^\s*(?:[-+*]\s+|\d+[.)]\s+)", "", line, count=1
            )
            if (
                _FINAL_LINE_RE.match(candidate)
                or _EVIDENCE_LINE_RE.match(candidate)
                or _BODY_LINE_RE.match(candidate)
            ):
                normalized.append(candidate)
            else:
                normalized.append(line)
        return normalized

    @staticmethod
    def diagnostic_key(reason: str) -> str:
        if reason == "accepted":
            return "accepted"
        if reason in {"unknown_final"}:
            return "unknown_final"
        if reason in {"placeholder_final", "placeholder_evidence", "placeholder_body"}:
            return "placeholder_final"
        if reason == "conflicting_final":
            return "conflicting_final"
        if reason in {"missing_body", "missing_evidence", "truncated_body"}:
            return "missing_body"
        return "no_final"


@dataclass
class _Selection:
    candidate: CandidatePacket | None
    consensus: bool
    basis: str


class ConsensusSelector:
    """Use the existing conservative answer-equivalence relation locally."""

    @staticmethod
    def _groups(candidates: Iterable[CandidatePacket]) -> list[list[CandidatePacket]]:
        groups: list[list[CandidatePacket]] = []
        for candidate in candidates:
            for group in groups:
                if answer_equivalence(candidate.answer, group[0].answer) == "EQUIVALENT":
                    group.append(candidate)
                    break
            else:
                groups.append([candidate])
        return groups

    @staticmethod
    def _cleanest(candidates: Iterable[CandidatePacket]) -> CandidatePacket | None:
        items = list(candidates)
        if not items:
            return None

        def score(candidate: CandidatePacket) -> tuple[int, int, int, int]:
            body = candidate.body
            noisy = bool(
                re.search(r"thinking\s+process|题目\s*[:：]|格式说明", body, re.IGNORECASE)
            )
            nonempty_lines = sum(bool(line.strip()) for line in body.splitlines())
            return (
                int(candidate.body_complete),
                int(not noisy),
                nonempty_lines,
                min(len(body), 4000),
            )

        return max(items, key=score)

    def select(self, candidates: list[CandidatePacket], problem_type: str) -> _Selection:
        if not candidates:
            return _Selection(None, False, "no_candidate")
        groups = self._groups(candidates)
        winning_group = max(groups, key=len)
        if len(winning_group) >= 2:
            if problem_type in _NUMERIC_TASK_TYPES:
                return _Selection(winning_group[0], True, "equivalent_answers")
            complete = [candidate for candidate in winning_group if candidate.body_complete]
            if not complete:
                return _Selection(
                    self._cleanest(candidates),
                    False,
                    "equivalent_without_complete_body",
                )
            return _Selection(
                self._cleanest(complete), True, "equivalent_conclusions"
            )
        if problem_type in _NUMERIC_TASK_TYPES:
            return _Selection(candidates[0], False, "deterministic_first")
        return _Selection(self._cleanest(candidates), False, "deterministic_cleanest")


class RequestGate:
    """Public-client request wrapper with one solve-local transient retry."""

    def __init__(
        self,
        request: Callable[..., str],
        budget: SolveBudget,
        trace: list[dict[str, Any]] | None = None,
    ) -> None:
        self.request = request
        self.budget = budget
        self.trace = trace if trace is not None else []

    @staticmethod
    def classify_error(exc: BaseException) -> str:
        status = getattr(exc, "status_code", getattr(exc, "status", None))
        code = str(getattr(exc, "code", "")).lower()
        category = str(getattr(exc, "category", "")).lower()
        class_name = type(exc).__name__.lower()
        message = str(exc)[:256].lower()
        haystack = " ".join((code, category, class_name, message))
        if (
            str(status) == "429"
            or "429" in message
            or "rate_limit" in haystack
            or "rate limit" in haystack
            or "ratelimit" in haystack
        ):
            return "rate_limit"
        if (
            str(status) == "503"
            or "503" in message
            or "serviceunavailable" in haystack
        ):
            return "service_unavailable"
        if isinstance(exc, TimeoutError) or "timeout" in haystack:
            return "timeout"
        if (
            "temporarily_unavailable" in haystack
            or "temporarily unavailable" in haystack
            or "temporarilyunavailable" in haystack
        ):
            return "temporarily_unavailable"
        return "model_error"

    def _record(self, label: str, status: str, max_tokens: int, **extra: Any) -> None:
        self.trace.append(
            {
                "step": "btcs_request",
                "label": label,
                "status": status,
                "max_tokens": max_tokens,
                "logical_calls": self.budget.logical_calls,
                "http_attempts": self.budget.http_attempts,
                "retry_count": self.budget.retries,
                **extra,
            }
        )

    def _retry_delay(self, retry_index: int) -> float:
        base = min(0.25, self.budget.retry_base_delay_seconds)
        return min(0.75, base * (3**retry_index))

    def call(
        self,
        label: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str | None:
        if self.budget.halted:
            self._record(label, "skipped", max_tokens, reason="gate_halted")
            return None
        if self.budget.logical_calls >= self.budget.max_logical_calls:
            self.budget.halted = True
            self._record(label, "skipped", max_tokens, reason="logical_budget_exhausted")
            return None

        self.budget.logical_calls += 1
        retry_index = 0
        while True:
            if self.budget.http_attempts >= self.budget.max_http_attempts:
                self.budget.halted = True
                self._record(label, "failed", max_tokens, error_category="http_budget_exhausted")
                return None
            self.budget.http_attempts += 1
            try:
                response = self.request(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.budget.temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                category = self.classify_error(exc)
                if (
                    category in _RETRYABLE_CATEGORIES
                    and retry_index < self.budget.retry_limit
                    and self.budget.retries < self.budget.retry_limit
                    and self.budget.http_attempts < self.budget.max_http_attempts
                ):
                    delay = self._retry_delay(retry_index)
                    self.budget.retries += 1
                    retry_index += 1
                    if delay:
                        time.sleep(delay)
                    continue
                self.budget.halted = True
                self._record(
                    label,
                    "failed",
                    max_tokens,
                    error_category=category,
                )
                return None

            if response is None:
                self._record(label, "empty", max_tokens)
                return ""
            if not isinstance(response, str):
                self.budget.halted = True
                self._record(
                    label,
                    "failed",
                    max_tokens,
                    error_category="invalid_response",
                )
                return None
            response = response.strip()
            self._record(label, "ok" if response else "empty", max_tokens)
            return response


class ContinuationFrame:
    def recover(
        self,
        problem: str,
        problem_type: str,
        prefixes: list[str],
        gate: RequestGate,
        budget: SolveBudget,
        parser: PacketParser,
    ) -> tuple[CandidatePacket | None, str]:
        prefix = max((item for item in prefixes if item), key=len, default="")[:4000]
        user_prompt = (
            f"题型：{problem_type}\n题目：\n{problem}\n\n"
            "已有解答前缀（只能据此判断，不得猜测）：\n"
            f"{prefix or '无可用前缀'}"
        )
        response = gate.call(
            "continuation",
            BTCS_CONTINUATION_PROMPT,
            user_prompt,
            budget.continuation_max_tokens,
        )
        return parser.parse_with_reason(
            response,
            problem_type,
            candidate_id="D",
            source="continuation",
            frame_version=budget.frame_version,
        )


class BoundedArbiter:
    def select(
        self,
        problem: str,
        problem_type: str,
        candidates: list[CandidatePacket],
        gate: RequestGate,
        budget: SolveBudget,
    ) -> tuple[CandidatePacket | None, str]:
        if not candidates:
            return None, "no_candidate"
        snippets = []
        for candidate in candidates:
            final = candidate.answer[:240]
            if budget.frame_version == "v2" and problem_type in _NUMERIC_TASK_TYPES:
                snippets.append(f"{candidate.candidate_id}: FINAL: {final}")
            else:
                evidence = candidate.evidence[:240] if candidate.evidence else "UNKNOWN"
                snippets.append(
                    f"{candidate.candidate_id}: FINAL: {final}\n"
                    f"EVIDENCE: {evidence}"
                )
        user_prompt = (
            f"题型：{problem_type}\n题目：\n{problem}\n\n"
            "候选摘要（不得补写答案）：\n" + "\n".join(snippets)
        )
        response = gate.call(
            "arbiter",
            BTCS_FRAME_V2_ARBITER_PROMPT,
            user_prompt,
            budget.arbiter_max_tokens,
        )
        if response is None:
            return None, "request_failed"
        match = _SELECT_LINE_RE.fullmatch(response)
        if not match:
            return None, "invalid_format"
        label = match.group(1).upper()
        if label == "UNKNOWN":
            return None, "unknown"
        selected = next(
            (candidate for candidate in candidates if candidate.candidate_id == label),
            None,
        )
        return (selected, "selected_existing") if selected else (None, "unknown_candidate")


class BoundedTypedConsensus:
    """Coordinate the bounded BTCS protocol and its frame-version policy."""

    def run(
        self,
        problem: str,
        problem_type: str,
        request: Callable[..., str],
        budget: SolveBudget,
    ) -> ProtocolResult:
        protocol = "btcs_frame_v2"
        direct_prompt = BTCS_FRAME_V2_DIRECT_PROMPT
        independent_prompt = BTCS_FRAME_V2_INDEPENDENT_PROMPT
        trace: list[dict[str, Any]] = [
            {
                "step": "route_budget",
                "protocol": protocol,
                "max_model_calls": budget.max_logical_calls,
                "max_http_attempts": budget.max_http_attempts,
            },
            {
                "step": "btcs_start",
                "protocol": protocol,
                "frame_version": budget.frame_version,
                "problem_type": problem_type,
                "max_logical_calls": budget.max_logical_calls,
                "max_http_attempts": budget.max_http_attempts,
                "retry_limit": budget.retry_limit,
            }
        ]
        parser = PacketParser()
        selector = ConsensusSelector()
        gate = RequestGate(request, budget, trace)
        candidates: list[CandidatePacket] = []
        prefixes: list[str] = []

        self._collect(
            "A",
            "direct",
            direct_prompt,
            problem,
            problem_type,
            budget,
            gate,
            parser,
            candidates,
            prefixes,
            trace,
        )
        self._collect(
            "B",
            "independent_checker",
            independent_prompt,
            problem,
            problem_type,
            budget,
            gate,
            parser,
            candidates,
            prefixes,
            trace,
        )

        selection = selector.select(candidates, problem_type)
        self._record_selection(trace, "after_two", selection, len(candidates))
        if selection.consensus:
            return self._finish(selection.candidate, problem_type, selection.basis, trace, budget)

        self._collect(
            "C",
            "independent_solver",
            independent_prompt,
            problem,
            problem_type,
            budget,
            gate,
            parser,
            candidates,
            prefixes,
            trace,
        )
        selection = selector.select(candidates, problem_type)
        self._record_selection(trace, "after_three", selection, len(candidates))
        if selection.consensus:
            return self._finish(selection.candidate, problem_type, selection.basis, trace, budget)

        if not candidates and problem_type in _NUMERIC_TASK_TYPES and not budget.halted:
            continuation, reason = ContinuationFrame().recover(
                problem, problem_type, prefixes, gate, budget, parser
            )
            trace.append(
                {
                    "step": "btcs_continuation",
                    "status": "accepted" if continuation else "rejected",
                    "reason": reason,
                }
            )
            if continuation:
                return self._finish(continuation, problem_type, "continuation", trace, budget)
            return self._finish(None, problem_type, "continuation_failed", trace, budget)

        if not candidates:
            return self._finish(None, problem_type, "no_candidate", trace, budget)

        arbiter_status = "not_called"
        selected = selection.candidate
        basis = selection.basis
        if not budget.halted:
            arbiter_candidates = candidates
            if problem_type in _NON_NUMERIC_TASK_TYPES:
                arbiter_candidates = [
                    candidate for candidate in candidates if candidate.body_complete
                ]
            if arbiter_candidates:
                selected, arbiter_status = BoundedArbiter().select(
                    problem, problem_type, arbiter_candidates, gate, budget
                )
                if selected is None:
                    selected = selection.candidate
                    basis = f"local_fallback_after_{arbiter_status}"
                else:
                    basis = "arbiter_existing_candidate"
            else:
                arbiter_status = "no_complete_body"
                selected = None
                basis = "local_fallback_after_no_complete_body"
        trace.append(
            {
                "step": "btcs_arbiter",
                "status": arbiter_status,
                "selected_existing": arbiter_status == "selected_existing",
                "candidate_count": len(candidates),
            }
        )
        return self._finish(selected, problem_type, basis, trace, budget)

    @staticmethod
    def _collect(
        candidate_id: str,
        source: str,
        system_prompt: str,
        problem: str,
        problem_type: str,
        budget: SolveBudget,
        gate: RequestGate,
        parser: PacketParser,
        candidates: list[CandidatePacket],
        prefixes: list[str],
        trace: list[dict[str, Any]],
    ) -> None:
        if budget.halted:
            return
        calls_before = budget.logical_calls
        response = gate.call(
            source,
            system_prompt,
            f"题型：{problem_type}\n题目：\n{problem}",
            budget.solver_max_tokens,
        )
        if budget.logical_calls > calls_before:
            budget.solver_requests += 1
        if response:
            prefixes.append(response)
        packet, reason = parser.parse_with_reason(
            response,
            problem_type,
            candidate_id=candidate_id,
            source=source,
            frame_version=budget.frame_version,
        )
        diagnostic_key = parser.diagnostic_key(reason)
        budget.packet_diagnostics[diagnostic_key] += 1
        if packet:
            candidates.append(packet)
            budget.parsed_solver_packets += 1
        trace.append(
            {
                "step": "btcs_packet",
                "candidate_id": candidate_id,
                "source": source,
                "status": "accepted" if packet else "rejected",
                "reason": reason,
                "has_body": bool(packet and packet.body),
                "truncation_signals": list(packet.truncation_signals) if packet else [],
            }
        )

    @staticmethod
    def _record_selection(
        trace: list[dict[str, Any]],
        phase: str,
        selection: _Selection,
        candidate_count: int,
    ) -> None:
        trace.append(
            {
                "step": "btcs_consensus",
                "phase": phase,
                "candidate_count": candidate_count,
                "consensus": selection.consensus,
                "basis": selection.basis,
                "selected_candidate_id": (
                    selection.candidate.candidate_id if selection.candidate else None
                ),
            }
        )

    @staticmethod
    def _finish(
        candidate: CandidatePacket | None,
        problem_type: str,
        basis: str,
        trace: list[dict[str, Any]],
        budget: SolveBudget,
    ) -> ProtocolResult:
        if candidate is None:
            final_response = "未能生成有效数学答案。"
            extracted_answer = ""
            status = "fallback"
            candidate_id = None
        elif problem_type in _NUMERIC_TASK_TYPES:
            final_response = candidate.normalized_answer or candidate.answer
            extracted_answer = final_response
            status = "selected"
            candidate_id = candidate.candidate_id
        elif candidate.body_complete:
            header = _PROOF_HEADERS.get(problem_type, "证明")
            # The body and conclusion are copied from the selected packet; the
            # old formatter only supplies the established public wrapper.
            raw = f"最终答案：{candidate.answer}\n\n{header}：\n{candidate.body}"
            final_response = reconstruct_final_response_f(raw, problem_type)
            extracted_answer = candidate.normalized_answer or candidate.answer
            status = "selected"
            candidate_id = candidate.candidate_id
        else:
            final_response = "未能生成有效数学答案。"
            extracted_answer = ""
            status = "fallback"
            candidate_id = None

        raw_packet_parse_rate = (
            budget.parsed_solver_packets / budget.solver_requests
            if budget.solver_requests
            else 0.0
        )
        trace.append(
            {
                "step": "btcs_packet_diagnostics",
                "counts": dict(budget.packet_diagnostics),
                "solver_requests": budget.solver_requests,
                "parsed_solver_packets": budget.parsed_solver_packets,
                "raw_packet_parse_rate": round(raw_packet_parse_rate, 6),
            }
        )
        trace.append(
            {
                "step": "finalize",
                "protocol": "btcs_frame_v2",
                "status": status,
                "selection_basis": basis,
                "selection_source": BoundedTypedConsensus._selection_source(basis),
                "candidate_id": candidate_id,
                "logical_calls": budget.logical_calls,
                "http_attempts": budget.http_attempts,
                "retry_count": budget.retries,
                "solver_requests": budget.solver_requests,
                "parsed_solver_packets": budget.parsed_solver_packets,
                "packet_diagnostics": dict(budget.packet_diagnostics),
                "raw_packet_parse_rate": round(raw_packet_parse_rate, 6),
                "per_solve_final_success": status == "selected",
            }
        )
        return ProtocolResult(
            final_response=final_response,
            extracted_answer=extracted_answer,
            trace=trace,
            logical_calls=budget.logical_calls,
            http_attempts=budget.http_attempts,
            packet_diagnostics=dict(budget.packet_diagnostics),
            per_solve_final_success=status == "selected",
            raw_packet_parse_rate=raw_packet_parse_rate,
            selection_source=BoundedTypedConsensus._selection_source(basis),
        )

    @staticmethod
    def _selection_source(basis: str) -> str:
        if basis == "continuation":
            return "continuation_candidate"
        if basis == "arbiter_existing_candidate":
            return "arbiter_existing_candidate"
        if basis == "no_candidate" or basis.endswith("failed"):
            return "none"
        if basis.startswith("local_fallback"):
            return "local_candidate"
        return "parsed_candidate"
