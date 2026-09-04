"""Bounded Analyze--Fork--Select/Deepen--Finish relay.

The relay is an opt-in code-acceptance path.  It deliberately owns its fixed
five-call protocol instead of inheriting any mutable submission configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any, Callable


METHOD_ID = "fork_select_deepen_finish_v1"
STAGE_TOKEN_SEQUENCE = (2048, 2048, 2048, 8192, 4096)
L0_TOKEN_SEQUENCE = (4096,)
SOFT_DEADLINE_SECONDS = 900.0
HARD_DEADLINE_SECONDS = 1080.0

_ANALYSIS_LIMIT = 1800
_ANALYSIS_FALLBACK_LIMIT = 5000
_IDEA_LIMIT = 1600
_DEEP_CONTEXT_LIMIT = 6000
_HANDOFF_LIMIT = 5000
_FINISH_CONTEXT_LIMIT = 6500
# E 的接力上下文内先为 D handoff 预留固定份额，A 摘要与选中思路不得挤占。
_FINISH_HANDOFF_RESERVE = 2000
_FINISH_LABEL_BUDGET = 64

_ANALYSIS_FIELDS = ("GOAL", "ANSWER_TYPE", "CONSTRAINTS", "STRUCTURE", "BOTTLENECK")
_IDEA_FIELDS = ("BRANCH", "METHOD", "KEY_LEMMA", "PLAN", "EXPECTED_FORM", "RISK")
_HANDOFF_FIELDS = ("SELECTED_BRANCH", "CANDIDATE_D", "DERIVED", "OPEN", "CHECKS", "RISK")

ANALYZE_PROMPT = """你负责 Analyze 阶段。只拆解题目，不完成整题，不输出 FINAL。
严格输出五个字段：GOAL、ANSWER_TYPE、CONSTRAINTS、STRUCTURE、BOTTLENECK。
每个字段保持简洁，说明题目目标、答案形式、定义域/边界/唯一性、核心结构和唯一瓶颈。"""

BRANCH_B_PROMPT = """你负责 Fork 的 B 分支。只提出标准构造/正向推导方法，不展开完整证明，
不计算正式终值，不输出 FINAL。严格输出 BRANCH: B、METHOD、KEY_LEMMA、PLAN（不超过6步）、
EXPECTED_FORM、RISK 六个字段。"""

BRANCH_C_PROMPT = """你负责 Fork 的 C 分支。只提出区别于标准正向推导的替代方法，优先使用反推、
极值、不变量、分类讨论、几何变换或模运算；不展开完整证明，不计算正式终值，不输出 FINAL。
严格输出 BRANCH: C、METHOD、KEY_LEMMA、PLAN（不超过6步）、EXPECTED_FORM、RISK 六个字段。"""

DEEPEN_PROMPT = """你负责 Select/Deepen 阶段。先明确选择 B 或 C 中恰好一条，再只沿选中的方法深推。
不得把两条方法融合成第三条。必须先输出 SELECTED_BRANCH: B 或 C、SELECTION_REASON、
CANDIDATE_D。随后输出 handoff 字段：SELECTED_BRANCH、CANDIDATE_D、DERIVED、OPEN、CHECKS、RISK。
可以输出 FINAL_D，但不要把未选分支全文复制进 handoff。"""

FINISH_PROMPT = """你负责 Finish 阶段。只沿已选分支和 D 的 handoff 收尾，不重新进行方法选择，
只修复选定链路的局部错误。第一项输出 CANDIDATE_E，末尾另起一行输出唯一 FINAL。
不要输出未选分支、多个答案或格式示例；无法确认时输出 FINAL: UNKNOWN。"""

L0_PROMPT = """这是一个已由确定性简单算式识别器命中的 L0 题。直接计算并只输出一行 FINAL: <答案>。
不要输出推理、多个答案或占位符。"""


@dataclass
class RelayResult:
    """Small result interface returned by the relay."""

    final_response: str
    trace: list[dict[str, Any]]
    extracted_answer: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_response": self.final_response,
            "extracted_answer": self.extracted_answer,
            "trace": self.trace,
        }


@dataclass
class _SolveState:
    started_at: float
    logical_calls: int = 0
    stage_status: dict[str, str] = field(default_factory=dict)
    analysis_packet_a: str = ""
    idea_packet_b: str = ""
    idea_packet_c: str = ""
    selected_branch: str = ""
    deep_handoff_d: str = ""
    finish_packet_e: str = ""
    candidate_history: list[str] = field(default_factory=list)
    sanitized_errors: list[str] = field(default_factory=list)


def _clip(text: str | None, limit: int) -> str:
    """Return a deterministic head/tail crop whose total length is bounded."""
    value = text if isinstance(text, str) else ""
    limit = max(0, int(limit))
    if len(value) <= limit:
        return value
    marker = "\n...[省略]...\n"
    if limit <= len(marker):
        return value[:limit]
    available = limit - len(marker)
    head = (available + 1) // 2
    tail = available - head
    return value[:head] + marker + (value[-tail:] if tail else "")


def _marker_value(text: str | None, marker: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(
        rf"(?im)^\s*{re.escape(marker)}\s*[:：]\s*(.*?)\s*$",
        text,
    )
    return match.group(1).strip() if match else ""


def _canonical_packet(text: str | None, fields: tuple[str, ...], limit: int, fallback_limit: int) -> str:
    values = [_marker_value(text, field) for field in fields]
    if all(values):
        return _clip("\n".join(f"{field}: {value}" for field, value in zip(fields, values)), limit)
    return _clip(text, fallback_limit)


def _is_placeholder(value: str | None) -> bool:
    if not isinstance(value, str):
        return True
    text = value.strip().strip("`\"'“”‘’")
    if not text:
        return True
    folded = text.casefold()
    if folded.strip("。.;,，；:：") in {
        "unknown",
        "<answer>",
        "<result>",
        "[answer]",
        "[result]",
        "答案",
        "answer",
        "result",
    }:
        return True
    if re.fullmatch(r"<\s*(?:answer|result|答案|答案内容|具体答案)\s*>", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"\[\s*(?:answer|result|答案|答案内容|具体答案)\s*\]", text, re.IGNORECASE):
        return True
    if "格式示例" in text or "format example" in folded:
        return True
    if "..." in text or "．．．" in text or "待定" == text:
        return True
    return False


def _boxed_value(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    for match in re.finditer(r"\\boxed\s*\{", text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth == 0:
            value = text[match.end(): index - 1].strip()
            if value and not _is_placeholder(value):
                return value
    return ""


_PURE_MATH_RE = re.compile(r"^[\s0-9A-Za-z_+*/^=(){}\[\].,<>≤≥±×÷\\|%!$\-]+$")
_MATH_STOP_WORDS = re.compile(
    r"(?:answer|result|final|candidate|unknown|therefore|because|step|proof|method|"
    r"最终答案|答案|因此|所以|证明|步骤|结论|候选|未知)",
    re.IGNORECASE,
)
_IDEA_PACKET_MARKER_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?`?(?:BRANCH|METHOD|KEY_LEMMA|PLAN|EXPECTED_FORM)`?\s*[:：]"
)


def _independent_math_line(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    candidates: list[str] = []
    for line in text.splitlines():
        value = line.strip().strip("`$")
        if not value or ":" in value or "：" in value:
            continue
        if "\\boxed" in value.casefold():
            continue
        if _MATH_STOP_WORDS.search(value) or not _PURE_MATH_RE.fullmatch(value):
            continue
        if not re.search(r"\d|[=+*/^{}()\[\]\\<>≤≥±×÷|%]", value):
            continue
        candidates.append(value)
    return candidates[0] if len(candidates) == 1 else ""


def _strip_idea_packet_text(text: str | None) -> str:
    """Ignore echoed B/C packet text before extracting D handoff fields."""
    if not isinstance(text, str):
        return ""
    marker = _IDEA_PACKET_MARKER_RE.search(text)
    return text[:marker.start()] if marker else text


def match_simple_arithmetic_expression(problem: str) -> str | None:
    """Single source of the deterministic simple-arithmetic (L0) recognizer.

    ``user_agent`` routes its baseline L0 decision through this function as
    well, so the relay path and the baseline recognizer cannot drift apart.
    """
    match = re.fullmatch(
        r"\s*(?:计算|求值|calculate|evaluate)?\s*([0-9+\-*/().\s]+)\s*[?？]?\s*",
        problem,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _error_category(exc: BaseException) -> str:
    category = getattr(exc, "category", "")
    if isinstance(category, str):
        folded = category.casefold()
        if "timeout" in folded:
            return "timeout"
        if "rate" in folded or "429" in folded:
            return "rate_limit"
        if "http" in folded or folded.isdigit() or "503" in folded:
            return "http_status"
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            return "rate_limit" if int(status_code) == 429 else "http_status"
        except (TypeError, ValueError):
            return "http_status"
    if "timeout" in type(exc).__name__.casefold():
        return "timeout"
    return "model_error"


class ForkSelectDeepenFinishRelay:
    """Deep FSDF module with one small public interface."""

    def __init__(self, client: Any, clock: Callable[[], float] = time.monotonic) -> None:
        self.client = client
        self.clock = clock

    def solve(self, problem: str, problem_type: str) -> RelayResult:
        problem_text = problem if isinstance(problem, str) else str(problem)
        state = _SolveState(started_at=self.clock())
        trace: list[dict[str, Any]] = []

        if problem_type == "calculation" and match_simple_arithmetic_expression(problem_text) is not None:
            if not self._stage_allowed(state, trace, "l0", L0_TOKEN_SEQUENCE[0]):
                return self._result(state, trace, "UNKNOWN", "unknown")
            response = self._call(
                state,
                trace,
                "l0",
                L0_PROMPT,
                problem_text,
                0.6,
                L0_TOKEN_SEQUENCE[0],
            )
            final_response, source = self._select_l0_answer(response)
            return self._result(state, trace, final_response, source)

        response_a = ""
        if self._stage_allowed(state, trace, "analyze", 2048):
            response_a = self._call(state, trace, "analyze", ANALYZE_PROMPT, problem_text, 0.2, 2048) or ""
        if response_a:
            state.analysis_packet_a = _canonical_packet(
                response_a, _ANALYSIS_FIELDS, _ANALYSIS_LIMIT, _ANALYSIS_FALLBACK_LIMIT
            )
            state.stage_status["analyze"] = "ok"
        else:
            state.stage_status["analyze"] = "failed"

        response_b = ""
        if self._stage_allowed(state, trace, "fork_b", 2048):
            response_b = self._call(
                state,
                trace,
                "fork_b",
                BRANCH_B_PROMPT,
                self._fork_user_prompt(problem_text, state.analysis_packet_a, "B"),
                0.6,
                2048,
            ) or ""
        if response_b:
            state.idea_packet_b = _canonical_packet(response_b, _IDEA_FIELDS, _IDEA_LIMIT, _IDEA_LIMIT)
            state.stage_status["fork_b"] = "ok"
            state.candidate_history.append("B")
        else:
            state.stage_status["fork_b"] = "failed"

        response_c = ""
        if self._stage_allowed(state, trace, "fork_c", 2048):
            response_c = self._call(
                state,
                trace,
                "fork_c",
                BRANCH_C_PROMPT,
                self._fork_user_prompt(problem_text, state.analysis_packet_a, "C"),
                0.6,
                2048,
            ) or ""
        if response_c:
            state.idea_packet_c = _canonical_packet(response_c, _IDEA_FIELDS, _IDEA_LIMIT, _IDEA_LIMIT)
            state.stage_status["fork_c"] = "ok"
            state.candidate_history.append("C")
        else:
            state.stage_status["fork_c"] = "failed"

        methods_equal = bool(
            state.idea_packet_b
            and state.idea_packet_c
            and (
                _marker_value(state.idea_packet_b, "METHOD").casefold()
                == _marker_value(state.idea_packet_c, "METHOD").casefold()
                or state.idea_packet_b == state.idea_packet_c
            )
        )
        if state.idea_packet_b and state.idea_packet_c:
            self._event(trace, state, "fork", "ok", 0, ideas_not_diverse=methods_equal)

        response_d = ""
        if self._stage_allowed(state, trace, "deepen", 8192):
            response_d = self._call(
                state,
                trace,
                "deepen",
                DEEPEN_PROMPT,
                self._deepen_user_prompt(problem_text, state),
                0.2,
                8192,
            ) or ""
        if response_d:
            branch = self._selected_branch(
                response_d, bool(state.idea_packet_b), bool(state.idea_packet_c)
            )
            if branch:
                state.stage_status["deepen"] = "ok"
                state.selected_branch = branch
                state.deep_handoff_d = self._handoff(response_d, state)
                state.candidate_history.append("D:" + branch)
            else:
                # D 协议失败：响应存在但没有可解析的 SELECTED_BRANCH。按 D 失败处置
                # （确定性分支回退，B 优先）。D 的 FINAL_D/CANDIDATE_D 仍保留在
                # §9 答案链，但不把不可信的 D 原文交给 E。
                state.stage_status["deepen"] = "protocol_failed"
                state.sanitized_errors.append("invalid_response")
                state.selected_branch = self._available_branch(state)
                state.deep_handoff_d = self._incomplete_handoff(state.selected_branch)
                self._mark_protocol_failure(trace, state, "deepen", state.selected_branch)
        else:
            state.stage_status["deepen"] = "failed"
            state.selected_branch = self._available_branch(state)
            state.deep_handoff_d = self._incomplete_handoff(state.selected_branch)

        response_e = ""
        if self._stage_allowed(state, trace, "finish", 4096):
            response_e = self._call(
                state,
                trace,
                "finish",
                FINISH_PROMPT,
                self._finish_user_prompt(problem_text, state),
                0.0,
                4096,
            ) or ""
        if response_e:
            state.stage_status["finish"] = "ok"
            state.finish_packet_e = _clip(response_e, _FINISH_CONTEXT_LIMIT)
        else:
            state.stage_status["finish"] = "failed"

        final_response, source = self._select_answer(response_e, response_d)
        return self._result(state, trace, final_response, source)

    @staticmethod
    def _fork_user_prompt(problem: str, analysis_packet: str, branch: str) -> str:
        analysis = analysis_packet or "A 状态不可用；只依据原题提出本分支思路。"
        return f"原题：\n{problem}\n\nA 状态：\n{analysis}\n\n当前分支：{branch}"

    @staticmethod
    def _deepen_user_prompt(problem: str, state: _SolveState) -> str:
        b = state.idea_packet_b or "B 思路不可用。"
        c = state.idea_packet_c or "C 思路不可用。"
        if not state.idea_packet_b and not state.idea_packet_c:
            direct = "两条分支均不可用：使用固定 direct fallback 深推，不产生新分支。"
        else:
            direct = ""
        context = _clip(
            f"A 状态：\n{state.analysis_packet_a or '不可用'}\n\nB 思路包：\n{b}\n\nC 思路包：\n{c}\n{direct}",
            _DEEP_CONTEXT_LIMIT,
        )
        return f"原题：\n{problem}\n\n{context}"

    @staticmethod
    def _finish_user_prompt(problem: str, state: _SolveState) -> str:
        branch = state.selected_branch or ForkSelectDeepenFinishRelay._available_branch(state) or "UNKNOWN"
        if branch == "B":
            selected_idea = state.idea_packet_b
        elif branch == "C":
            selected_idea = state.idea_packet_c
        else:
            selected_idea = "没有可用分支；沿 D handoff 做固定 direct fallback。"
        handoff = _clip(state.deep_handoff_d or "不可用", _FINISH_HANDOFF_RESERVE)
        budget = _FINISH_CONTEXT_LIMIT - _FINISH_LABEL_BUDGET - len(handoff)
        selected = _clip(selected_idea or "不可用", min(_IDEA_LIMIT, max(0, budget)))
        analysis = _clip(
            state.analysis_packet_a or "不可用", max(0, budget - len(selected))
        )
        context = _clip(
            f"A 约束摘要：\n{analysis}\n\nSELECTED_BRANCH: {branch}\n选中思路：\n{selected}\n\nD handoff：\n{handoff}",
            _FINISH_CONTEXT_LIMIT,
        )
        return f"原题：\n{problem}\n\n{context}"

    @staticmethod
    def _available_branch(state: _SolveState) -> str:
        # D 失败且两支都可用时，固定选择标准路径 B，保证降级可复现。
        if state.idea_packet_b:
            return "B"
        if state.idea_packet_c:
            return "C"
        return ""

    @staticmethod
    def _selected_branch(response: str, has_b: bool, has_c: bool) -> str:
        selected = _marker_value(response, "SELECTED_BRANCH").upper()
        if selected not in {"B", "C"}:
            return ""
        # A syntactically valid choice is still a protocol failure when that
        # branch is unavailable. Never relabel D's work as the other branch.
        if selected == "B" and not has_b:
            return ""
        if selected == "C" and not has_c:
            return ""
        return selected

    @staticmethod
    def _handoff(response: str, state: _SolveState) -> str:
        branch = state.selected_branch or "UNKNOWN"
        # Only parse the D handoff prefix.  A model may echo an idea packet
        # later in its response; idea markers are not D handoff evidence.
        safe_response = _strip_idea_packet_text(response)
        substantive = {
            field: _marker_value(safe_response, field)
            for field in _HANDOFF_FIELDS[1:]
        }
        parts = [f"SELECTED_BRANCH: {branch}"]
        parts.extend(
            f"{field}: {value}" for field, value in substantive.items() if value
        )
        if any(not value for value in substantive.values()):
            # 缺字段只标记不完整；E 不接收 D 的任意自由文本，避免未选分支泄露。
            parts.append("HANDOFF_INCOMPLETE: true")
        return _clip("\n".join(parts), _HANDOFF_LIMIT)

    @staticmethod
    def _incomplete_handoff(branch: str) -> str:
        return _clip(
            f"SELECTED_BRANCH: {branch or 'UNKNOWN'}\nHANDOFF_INCOMPLETE: true",
            _HANDOFF_LIMIT,
        )

    def _mark_protocol_failure(
        self,
        trace: list[dict[str, Any]],
        state: _SolveState,
        stage: str,
        selected_branch: str,
    ) -> None:
        for event in reversed(trace):
            if event.get("stage") == stage:
                event["status"] = "protocol_failed"
                event["error_category"] = "invalid_response"
                event["packet_present"] = False
                event["selected_branch"] = selected_branch or "UNKNOWN"
                return
        self._event(
            trace,
            state,
            stage,
            "protocol_failed",
            8192,
            error_category="invalid_response",
            packet_present=False,
            selected_branch=selected_branch or "UNKNOWN",
        )

    def _call(
        self,
        state: _SolveState,
        trace: list[dict[str, Any]],
        stage: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        if state.logical_calls >= 5:
            return None
        if self._deadline(state) == "hard":
            self._event(trace, state, stage, "skipped", max_tokens, error_category="hard_deadline")
            return None
        state.logical_calls += 1
        try:
            response = self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # the public client contract permits arbitrary exceptions
            category = _error_category(exc)
            state.sanitized_errors.append(category)
            state.stage_status[stage] = "failed"
            self._event(trace, state, stage, "failed", max_tokens, error_category=category)
            return None
        if not isinstance(response, str) or not response.strip():
            state.sanitized_errors.append("invalid_response")
            state.stage_status[stage] = "failed"
            self._event(trace, state, stage, "failed", max_tokens, error_category="invalid_response")
            return None
        state.stage_status[stage] = "ok"
        self._event(trace, state, stage, "ok", max_tokens, packet_present=True)
        return response.strip()

    def _stage_allowed(
        self, state: _SolveState, trace: list[dict[str, Any]], stage: str, max_tokens: int
    ) -> bool:
        deadline = self._deadline(state)
        if deadline:
            self._event(
                trace,
                state,
                stage,
                "skipped",
                max_tokens,
                error_category=f"{deadline}_deadline",
            )
            return False
        return True

    def _deadline(self, state: _SolveState) -> str:
        elapsed = self.clock() - state.started_at
        if elapsed >= HARD_DEADLINE_SECONDS:
            return "hard"
        if elapsed >= SOFT_DEADLINE_SECONDS:
            return "soft"
        return ""

    def _event(
        self,
        trace: list[dict[str, Any]],
        state: _SolveState,
        stage: str,
        status: str,
        max_tokens: int,
        **extra: Any,
    ) -> None:
        event: dict[str, Any] = {
            "method": METHOD_ID,
            "stage": stage,
            "status": status,
            "model_calls": state.logical_calls,
            "max_tokens": max_tokens,
            "elapsed_bucket": self._elapsed_bucket(state),
        }
        event.update({key: value for key, value in extra.items() if key in {
            "packet_present",
            "selected_branch",
            "candidate_present",
            "final_present",
            "fallback_source",
            "error_category",
            "ideas_not_diverse",
        }})
        trace.append(event)

    def _elapsed_bucket(self, state: _SolveState) -> str:
        elapsed = self.clock() - state.started_at
        if elapsed >= HARD_DEADLINE_SECONDS:
            return "hard"
        if elapsed >= SOFT_DEADLINE_SECONDS:
            return "soft"
        return "normal"

    @staticmethod
    def _select_l0_answer(response: str | None) -> tuple[str, str]:
        final = _marker_value(response, "FINAL") or _marker_value(response, "最终答案")
        if final and not _is_placeholder(final):
            return final, "finish_final"
        boxed = _boxed_value(response)
        if boxed:
            return boxed, "boxed"
        math_line = _independent_math_line(response)
        if math_line:
            return math_line, "math_line"
        return "UNKNOWN", "unknown"

    @staticmethod
    def _select_answer(response_e: str | None, response_d: str | None) -> tuple[str, str]:
        choices = (
            ("finish_final", _marker_value(response_e, "FINAL") or _marker_value(response_e, "最终答案")),
            ("finish_candidate", _marker_value(response_e, "CANDIDATE_E")),
            ("deep_final", _marker_value(response_d, "FINAL_D")),
            ("deep_candidate", _marker_value(response_d, "CANDIDATE_D")),
        )
        for source, value in choices:
            if value and not _is_placeholder(value):
                return value, source
        boxed = _boxed_value(response_d)
        if boxed:
            return boxed, "boxed"
        math_line = _independent_math_line(response_e)
        if math_line:
            return math_line, "math_line"
        math_line = _independent_math_line(response_d)
        if math_line:
            return math_line, "math_line"
        return "UNKNOWN", "unknown"

    def _result(
        self,
        state: _SolveState,
        trace: list[dict[str, Any]],
        final_response: str,
        fallback_source: str,
    ) -> RelayResult:
        final = final_response.strip() if isinstance(final_response, str) else "UNKNOWN"
        if not final or _is_placeholder(final):
            final, fallback_source = "UNKNOWN", "unknown"
        self._event(
            trace,
            state,
            "finalize",
            "ok" if final != "UNKNOWN" else "unknown",
            0,
            final_present=final != "UNKNOWN",
            fallback_source=fallback_source,
            selected_branch=state.selected_branch or "UNKNOWN",
        )
        return RelayResult(final_response=final, extracted_answer=final if final != "UNKNOWN" else "", trace=trace)


__all__ = [
    "ForkSelectDeepenFinishRelay",
    "RelayResult",
    "METHOD_ID",
    "STAGE_TOKEN_SEQUENCE",
    "L0_TOKEN_SEQUENCE",
    "SOFT_DEADLINE_SECONDS",
    "HARD_DEADLINE_SECONDS",
    "match_simple_arithmetic_expression",
]
