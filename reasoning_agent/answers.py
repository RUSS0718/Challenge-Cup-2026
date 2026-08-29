"""Pure answer extraction, normalization, equivalence and safety checks."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from reasoning_agent.policy import (
    TASK_TYPE_CALCULATION,
    TASK_TYPE_CHOICE,
    TASK_TYPE_DERIVATION,
    TASK_TYPE_EXPLANATION,
    TASK_TYPE_FILL_BLANK,
    TASK_TYPE_PROOF,
    _NON_NUMERIC_TASK_TYPES,
)

_ANSWER_MARKER_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]\s*([^\n\r]+)", re.IGNORECASE)
_ANSWER_MARKER_LINE_STRICT_RE = re.compile(
    r"^\s*(?:最终答案|final\s+answer|答案)\s*[:：]\s*(.*?)\s*$",
    re.IGNORECASE,
)
_CHOICE_LINE_RE = re.compile(r"^(?:选项\s*)?([A-Da-d])(?:[.。)）]?)\s*$")
# A standalone answer line must be pure math (no CJK prose / sentence punctuation).
_MATH_ONLY_LINE_RE = re.compile(r"^[\sA-Za-z0-9+\-*/=<>≤≥.,(){}[\]^_'\\|±×÷]+$")
# Natural-language connectives that mark a truncated / prose fragment.
_CONNECTIVE_RE = re.compile(r"(因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)")
_STRICT_THINKING_RE = re.compile(
    r"\b(?:thinking(?:\s+process)?|analysis|reasoning|draft)\b|思考过程|思维链|内部推理",
    re.IGNORECASE,
)


def extract_final_answer(response: str) -> str:
    """Return a clean, explicit answer or "" (no arbitrary last-line fallback).

    Accepts only: a closed ``\\boxed{...}``, an explicit ``最终答案：`` /
    ``Final answer:`` / ``答案：`` marker with an answer-like value, or a
    standalone short answer line (option letter / number / fraction / equation /
    set).  A truncated natural-language tail line is never treated as an answer.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    boxed = _extract_boxed_answers(response)
    if boxed:
        return boxed[-1]
    markers = _ANSWER_MARKER_RE.findall(response)
    for marker in reversed(markers):
        answer = marker.strip()
        if answer and not is_placeholder_answer(answer) and _is_answer_like(answer):
            return answer
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for line in reversed(lines):
        choice = _CHOICE_LINE_RE.match(line)
        if choice:
            return choice.group(1).upper()
        standalone = _is_standalone_answer_line(line)
        if standalone is not None:
            return standalone
    return ""


def extract_answer_first(response: str) -> str:
    """Prefer the first standalone answer marker used by the answer-first arm."""
    if not isinstance(response, str) or not response.strip():
        return ""
    for line in response.splitlines():
        match = _ANSWER_MARKER_LINE_STRICT_RE.match(line)
        if not match:
            continue
        answer = match.group(1).strip()
        if answer and not is_placeholder_answer(answer) and _is_answer_like(answer):
            return answer
    return extract_final_answer(response)


def extract_numeric_answer(response: str) -> str:
    """Extract a conservative answer for numeric/choice/fill-blank tasks.

    This salvage arm only accepts an independent answer-marker line, a closed
    ``\\boxed{...}``, a standalone option letter, or a short pure-math line.
    It deliberately does not accept an arbitrary last line or prose sentence.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for line in reversed(lines):
        marker = _ANSWER_MARKER_LINE_STRICT_RE.match(line)
        if not marker:
            continue
        answer = marker.group(1).strip()
        if r"\boxed{" in answer:
            boxed_answer = _extract_standalone_boxed_answer(answer)
            if boxed_answer and _is_strict_numeric_value(boxed_answer):
                return boxed_answer
            continue
        if answer and _is_strict_numeric_value(answer):
            return answer
    for line_index in range(len(lines) - 1, -1, -1):
        line = lines[line_index]
        answer = _extract_standalone_boxed_answer(line)
        if answer and _STRICT_THINKING_RE.search("\n".join(lines[:line_index])):
            continue
        if answer and _is_strict_numeric_value(answer):
            return answer
    last_line = lines[-1] if lines else ""
    choice = _CHOICE_LINE_RE.match(last_line)
    if choice:
        return choice.group(1).upper()
    if r"\boxed{" in last_line:
        return ""
    standalone = _is_standalone_answer_line(last_line)
    if standalone is not None:
        return standalone
    return ""


def _extract_standalone_boxed_answer(line: str) -> str:
    """Extract one boxed value only when the whole line is a boxed answer."""
    text = line.strip()
    answers = _extract_boxed_answers(text)
    if len(answers) != 1 or text.count(r"\boxed{") != 1:
        return ""
    start = text.find(r"\boxed{")
    end = text.rfind("}")
    prefix = text[:start].strip().strip("$*")
    suffix = text[end + 1:].strip().strip("$*")
    if prefix or suffix:
        return ""
    return answers[0].strip()


def _is_strict_numeric_value(answer: str) -> bool:
    """Accept only a choice token or an independent pure-math answer."""
    if not answer or is_placeholder_answer(answer):
        return False
    if _CHOICE_LINE_RE.fullmatch(answer.strip()):
        return True
    return _is_standalone_answer_line(answer) is not None


# ── 13.2 实验 C/D：非数值题型答案段抽取（answer-first 协议）──────────────────
# 答案前置后，非数值题型（derivation/proof/explanation）的响应以「最终答案：<结论>」
# 开头，正文在后。这里抽取首个「真正」的答案段，跳过 thinking 复述的占位符。
_ANSWER_MARKER_POS_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]", re.IGNORECASE)
# 段边界：下一个结构标题（中英文正文标题 + 答案标记）。
_ANSWER_SEGMENT_STOP_RE = re.compile(
    r"\n\s*(?:推导|证明|解释|Derivation|Proof|Explanation|最终答案|final\s+answer|答案)\s*[:：]",
    re.IGNORECASE,
)
# 正文标题（用于 final_response 重建时定位正文起点）。
_BODY_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:推导|证明|解释|Derivation|Proof|Explanation)\s*[:：]\s*",
    re.IGNORECASE,
)
_ANSWER_ECHO_RE = re.compile(
    r"only\s+write|complete\s+chain|followed\s+by|final\s+expression|只写|简洁|独立判定|最终表达式|核心回答",
    re.IGNORECASE,
)
# thinking 元文本（假标记常出现在这类句子里）。
_THINKING_CONTEXT_RE = re.compile(
    r"system\s+prompt|asks?\s+for|format\s+instruction|following\s+structure|meta-?analysis",
    re.IGNORECASE,
)


def extract_answer_segment(response: str) -> str:
    """Return the genuine answer segment from an answer-first response, or "".

    Extracts the first "最终答案：" segment that is a real structural answer
    block, not a thinking-process echo: it skips placeholder echoes ("<…>"),
    prompt boilerplate, markers quoted inside thinking text, and markers
    sitting in meta-instruction sentences ("the system prompt asks for…").
    The segment is returned verbatim — no global numeric normalization, so
    proofs, explanations, inequalities, sets and tuples keep their semantics.
    """
    if not isinstance(response, str) or not response.strip():
        return ""
    for m in _ANSWER_MARKER_POS_RE.finditer(response):
        seg = _take_answer_segment(response, m.end())
        if not seg or _is_answer_echo(seg):
            continue
        if _is_marker_in_thinking_quote(response, m.start()):
            continue
        return seg
    return ""


def _is_marker_in_thinking_quote(text: str, pos: int) -> bool:
    """True when a marker sits inside a thinking quote / meta sentence, not a
    standalone structural line."""
    # 只看标记所在行内、标记前的内容（不跨行，避免误伤下一行的真标记）。
    line_start = text.rfind("\n", 0, pos) + 1
    ctx = text[line_start:pos]
    # Unbalanced double quote (marker inside a quoted echo).
    if ctx.count('"') % 2 == 1:
        return True
    # Unbalanced Chinese quote pair.
    if ctx.count("“") != ctx.count("”") or ctx.count("‘") != ctx.count("’"):
        return True
    # Marker right after a Markdown list bullet ("- Final Answer: …").
    if re.fullmatch(r"[-*]\s*", ctx.strip()):
        return True
    # Meta-instruction sentence on the same line.
    if _THINKING_CONTEXT_RE.search(ctx):
        return True
    return False


def _take_answer_segment(text: str, start: int) -> str:
    """Slice the segment right after a marker, up to the next structure header
    (推导/证明/解释/最终答案, 中英文) or a blank line."""
    rest = text[start:]
    stop = _ANSWER_SEGMENT_STOP_RE.search(rest)
    blank = re.search(r"\n\s*\n", rest)
    end = len(rest)
    if stop:
        end = min(end, stop.start())
    if blank:
        end = min(end, blank.start())
    return rest[:end].strip()


def _is_answer_echo(seg: str) -> bool:
    """True when a marker segment is a placeholder/prompt echo, not a real answer."""
    s = seg.strip()
    if not s:
        return True
    if re.match(r"^<[^>]*>", s):
        return True  # "<只写…>" placeholder copied verbatim
    if _ANSWER_ECHO_RE.search(s):
        return True  # prompt boilerplate echoed inside thinking
    return False


_BODY_HEADER_NAME = {
    TASK_TYPE_DERIVATION: "推导",
    TASK_TYPE_PROOF: "证明",
    TASK_TYPE_EXPLANATION: "解释",
}


def reconstruct_final_response(response: str, problem_type: str) -> str:
    """Rebuild a clean answer-first final_response, or return the original.

    Drops the thinking / prompt echo that precedes the real answer block, keeps
    the answer conclusion and the body after the structure header, and re-emits
    them as「最终答案：<结论>」+「<正文标题>：<正文>」.  Never collapses a proof
    into a bare number.  When the structure cannot be reliably identified, the
    original response is returned unchanged (no aggressive trimming).
    """
    if not isinstance(response, str) or not response.strip():
        return response or ""
    answer_pos = -1
    answer_seg = ""
    for m in _ANSWER_MARKER_POS_RE.finditer(response):
        seg = _take_answer_segment(response, m.end())
        if seg and not _is_answer_echo(seg) and not _is_marker_in_thinking_quote(response, m.start()):
            answer_pos = m.start()
            answer_seg = seg
            break
    if answer_pos < 0 or not answer_seg:
        return response  # 无真实答案块 → 不裁剪
    body_m = _BODY_HEADER_RE.search(response, answer_pos + 1)
    if not body_m:
        return response  # 无正文标题 → 不裁剪
    body = response[body_m.end():].strip()
    if not body:
        return response  # 正文为空 → 不裁剪
    header = _BODY_HEADER_NAME.get(problem_type, "证明")
    return f"最终答案：{answer_seg}\n\n{header}：\n{body}"


# ── 13.2 实验 F：行级结构语法收紧（三状态解析 PREAMBLE→ANSWER→BODY）─────────
# 实验 E 证明 Prompt 压制语已到天花板。F 从解析层收紧：答案标记/正文标题必须
# 是独立结构行（行首，允许有限 Markdown 包装），嵌在 thinking 句子、约束说明、
# 引号、列表里的「最终答案」一律不识别；占位符（<…>/[Core Answer]/[Option
# Letter]/…）一律拒绝。不做全局数值规范化，不按 thinking/analysis 词删正文句。
_ANSWER_MARKER_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:最终答案|final\s+answer|答案)\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_BODY_HEADER_LINE_RE = re.compile(
    r"^(?:\*\*|\*)?\s*(?:推导|证明|解释|Derivation|Proof|Explanation)"
    r"(?:\s*(?:块|Block))?\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?$",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"^(?:<[^>]*>|\[[^\]]*\]|\.{3,}|…{1,})$")


def _is_placeholder_segment(seg: str) -> bool:
    """F：占位符答案段（尖括号/方括号占位符、纯省略号、prompt 复述词）。"""
    s = seg.strip()
    if not s:
        return True
    if _PLACEHOLDER_RE.match(s):
        return True
    if _ANSWER_ECHO_RE.search(s):
        return True
    return False


def parse_structure_f(response: str, problem_type: str) -> dict:
    """F 三状态行解析，返回 {status, answer, body}。

    status: "structured"（答案+正文齐全）/ "no_answer_block"（无独立答案标记行）
            / "no_body"（有答案但无独立正文标题行）。
    仅接受「独立结构行」：答案标记/正文标题必须是行首（允许 **…** 粗体包装）。
    不识别特定题号、学科或具体答案。
    """
    if not isinstance(response, str) or not response.strip():
        return {"status": "no_answer_block", "answer": "", "body": ""}

    lines = response.splitlines()
    answer = ""
    answer_idx = -1
    for i, line in enumerate(lines):
        m = _ANSWER_MARKER_LINE_RE.match(line)
        if m and not _is_placeholder_segment(m.group(1)):
            answer = m.group(1).strip()
            answer_idx = i
            break
    if answer_idx < 0:
        return {"status": "no_answer_block", "answer": "", "body": ""}

    for j in range(answer_idx + 1, len(lines)):
        m = _BODY_HEADER_LINE_RE.match(lines[j])
        if m:
            head_rest = m.group(1).strip()
            tail = lines[j + 1:]
            body_lines = ([head_rest] if head_rest else []) + tail
            body = "\n".join(body_lines).strip()
            if body:
                return {"status": "structured", "answer": answer, "body": body}
            return {"status": "no_body", "answer": answer, "body": ""}
    return {"status": "no_body", "answer": answer, "body": ""}


def reconstruct_final_response_f(response: str, problem_type: str) -> str:
    """F 版 final_response 重建：仅在结构可靠时裁剪 thinking 前缀。

    无独立答案块或正文标题时返回原始响应（不具备重建条件，不激进裁剪）。
    """
    parsed = parse_structure_f(response, problem_type)
    if parsed["status"] != "structured":
        return response or ""
    header = _BODY_HEADER_NAME.get(problem_type, "证明")
    return f"最终答案：{parsed['answer']}\n\n{header}：\n{parsed['body']}"


def _is_answer_like(answer: str) -> bool:
    """A marker value must look like a short mathematical result, not trailing prose."""
    s = answer.strip().strip("。；;.,\"'“”’ ")
    if not s or len(s) > 60:
        return False
    if re.search(r"[，,、;；:：=<>]\s*$", s):
        return False  # ends mid-sentence → truncated
    if re.search(r"(?:因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)$", s):
        return False  # ends with a reasoning connective → truncated
    return True


def _is_standalone_answer_line(line: str) -> str | None:
    """Return a standalone short math answer line, or None if not answer-like."""
    s = line.strip()
    if not s or len(s) > 60 or is_placeholder_answer(s):
        return None
    if re.search(r"[，。；;、？！\n]", s):
        return None  # sentence punctuation → prose, not a bare answer
    if _CONNECTIVE_RE.search(s):
        return None  # contains a reasoning connective → prose
    if not _MATH_ONLY_LINE_RE.fullmatch(s):
        return None  # contains CJK / non-math characters
    if not (re.search(r"\d", s) or re.search(r"[=<>≤≥]", s)):
        return None  # no numeric or relational content
    return s


def _has_placeholder_answer(response: str) -> bool:
    """True if an answer marker in the response resolves to a placeholder token."""
    for marker in _ANSWER_MARKER_RE.findall(response or ""):
        if is_placeholder_answer(marker):
            return True
    for boxed in _extract_boxed_answers(response or ""):
        if is_placeholder_answer(boxed):
            return True
    return False


def is_placeholder_answer(answer: str) -> bool:
    """Reject output-format placeholders and prompt echoes that are not answers."""
    compact = answer.strip().lower().strip("。；;.,\"'”’ ")
    return compact in {
        "[answer]", "<answer>", "答案", "answer",
        "明确写出答案", "写出答案", "请写出答案", "最终答案",
    }


# ── P1: failure-path salvage (invalid → judgeable best-effort answer) ────
_SALVAGE_BOXED_RE = re.compile(r"\\boxed\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_SALVAGE_MARKER_RE = re.compile(r"(?:最终答案|答案|Final answer|Answer)\s*[:：为]?\s*(.+)")
_SALVAGE_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:/\d+)?")
_SALVAGE_MAX_CHARS = 100


def _salvage_answer(texts: list[str], problem_type: str) -> str:
    """Best-effort answer from rejected responses, or "".

    Priority per response: \\boxed content > explicit answer marker > the
    last bare numeric/ratio token. Placeholder-like extractions are refused.
    Numeric-family problems only: proof/derivation/explanation dumps of a
    stray number would be meaningless.
    """
    if problem_type not in (TASK_TYPE_CALCULATION, TASK_TYPE_FILL_BLANK, TASK_TYPE_CHOICE):
        return ""
    for text in reversed(texts):
        raw = text or ""
        if not raw.strip():
            continue
        for pattern in (_SALVAGE_BOXED_RE, _SALVAGE_MARKER_RE, _SALVAGE_NUMBER_RE):
            matches = list(pattern.finditer(raw))
            for match in reversed(matches):
                candidate = (match.group(1) if match.lastindex else match.group(0)).strip()
                if pattern is _SALVAGE_MARKER_RE:
                    # marker capture runs to end of text; keep only the first
                    # segment up to a sentence break.
                    candidate = re.split(r"[。\n;,;]", candidate)[0].strip()
                candidate = candidate.strip("。；;,， ]）)")
                if not candidate or len(candidate) > _SALVAGE_MAX_CHARS:
                    continue
                if is_placeholder_answer(candidate) or _is_placeholder_segment(candidate):
                    continue
                if not re.search(r"[\w\\]", candidate):
                    # must contain at least one letter/digit/backslash:
                    # pure punctuation tokens (e.g. ">") are not answers.
                    continue
                if pattern is _SALVAGE_NUMBER_RE and not re.fullmatch(
                        r"-?\d+(?:\.\d+)?(?:/\d+)?", candidate):
                    # bare-number tier only accepts whole numeric tokens;
                    # marker/boxed tiers accept what they matched.
                    continue
                return candidate
    return ""


def _truncation_signals(response: str, answer: str) -> list[str]:
    """Proxy signals for finish_reason=length truncation (client returns str only).

    These are observability-only hints; the solver's only hard decision is
    ``no clear answer → at most one recovery call``.
    """
    signals: list[str] = []
    text = (response or "").rstrip()
    if not answer:
        signals.append("no_extractable_answer")
    if re.search(r"[，,、;；:：=<>]\s*$", text):
        signals.append("ends_with_connective_punctuation")
    if re.search(r"(?:因此|所以|故|综上|代入|根据|由此|从而|于是|接下来|那么|则|即|得到|可得|解得|我们|考虑|推导)$", text):
        signals.append("ends_with_connective_word")
    if "\\boxed{" in text and text.rfind("}") < text.rfind("\\boxed{"):
        signals.append("unclosed_boxed")
    if text.endswith("\\"):
        signals.append("ends_with_backslash")
    return signals

def _extract_boxed_answers(text: str) -> list[str]:
    answers, cursor = [], 0
    while True:
        start = text.find(r"\boxed{", cursor)
        if start < 0: return answers
        depth, index = 1, start + len(r"\boxed{")
        content_start = index
        while index < len(text) and depth:
            depth += (text[index] == "{") - (text[index] == "}")
            index += 1
        if depth == 0 and (answer := text[content_start:index - 1].strip()): answers.append(answer)
        cursor = index if index > start else start + 1

def _format_rational(number: Fraction) -> str:
    return str(number.numerator) if number.denominator == 1 else f"{number.numerator}/{number.denominator}"

def _parse_rational_token(token: str) -> Fraction | None:
    compact = re.sub(r"\s+", "", token or "")
    if not compact:
        return None
    compact = compact.replace("\\left", "").replace("\\right", "").replace("−", "-")
    match = re.fullmatch(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", compact)
    if match:
        compact = f"{match.group(1)}/{match.group(2)}"
    try:
        return Fraction(Decimal(compact))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        try:
            return Fraction(compact)
        except (ValueError, ZeroDivisionError):
            return None

def _canonicalize_multi_numeric_set(answer: str) -> str | None:
    """Unordered multi-root numeric sets only; ordered tuples/vectors stay untouched.

    Universal surface forms such as ``x=1, x=-1``, ``-1 or 1``, ``{1,-1}``.
    No problem-id or subject branching.
    """
    if not isinstance(answer, str) or not answer.strip():
        return None
    text = answer.strip().rstrip("。；;.")
    # Keep ordered coordinates / inequalities / single expressions alone.
    if re.fullmatch(r"\([^()]+(?:,[^()]+)+\)", re.sub(r"\s+", "", text)):
        return None
    if re.search(r"[<>≤≥]", text):
        return None
    # Drop optional set braces after rejecting ordered tuples.
    bare = text
    if bare.startswith("{") and bare.endswith("}"):
        bare = bare[1:-1].strip()
    # Require an explicit multi-value separator before treating as a set.
    if not re.search(r",|，|、|\bor\b|或", bare, flags=re.IGNORECASE):
        return None
    pieces = [p.strip() for p in re.split(r"(?:,|，|、|\bor\b|或)", bare, flags=re.IGNORECASE) if p.strip()]
    if len(pieces) < 2:
        return None
    values: list[Fraction] = []
    for piece in pieces:
        # Strip repeated ``var =`` / ``var:`` labels common in multi-root dumps.
        piece = re.sub(r"^(?:[A-Za-z\u4e00-\u9fff]+)\s*[=:：]\s*", "", piece.strip())
        number = _parse_rational_token(piece)
        if number is None:
            return None
        values.append(number)
    # Unordered set: sort and dedupe exact rationals.
    ordered = sorted(set(values))
    return ",".join(_format_rational(v) for v in ordered)

def normalize_answer(answer: str) -> str:
    if not isinstance(answer, str): return ""
    multi = _canonicalize_multi_numeric_set(answer)
    if multi is not None:
        return multi
    compact = re.sub(r"\s+", "", answer).rstrip("。；;.,\"")
    if not compact: return ""
    # Strip display-math / markdown wrappers so LaTeX answers normalize cleanly.
    compact = compact.replace("$", "").replace("\\(", "").replace("\\)", "").replace("**", "")
    compact = compact.replace("\\left", "").replace("\\right", "")
    match = re.fullmatch(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", compact)
    if match: compact = f"{match.group(1)}/{match.group(2)}"
    compact = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", compact).replace("−", "-").replace("×", "*")
    number = _parse_rational_token(compact)
    if number is None:
        return compact
    return _format_rational(number)

def answer_equivalence(left: str, right: str) -> str:
    """Return only proven answer identity; ambiguous expressions stay separate."""
    normalized_left, normalized_right = normalize_answer(left), normalize_answer(right)
    if not normalized_left or not normalized_right:
        return "UNKNOWN"
    if normalized_left == normalized_right:
        return "EQUIVALENT"
    numeric = r"-?\d+(?:/\d+)?"
    multi_numeric = rf"{numeric}(?:,{numeric})+"
    if re.fullmatch(numeric, normalized_left) and re.fullmatch(numeric, normalized_right):
        return "NOT_EQUIVALENT"
    if re.fullmatch(multi_numeric, normalized_left) and re.fullmatch(multi_numeric, normalized_right):
        return "NOT_EQUIVALENT"
    if re.fullmatch(r"[A-D]", normalized_left, re.IGNORECASE) and re.fullmatch(r"[A-D]", normalized_right, re.IGNORECASE):
        return "NOT_EQUIVALENT"
    return "UNKNOWN"


def has_conflicting_explicit_answers(response: str) -> bool:
    """True only for two explicit, provably different terminal answers."""
    answers = [answer.strip() for answer in _ANSWER_MARKER_RE.findall(response) if answer.strip()]
    return any(
        answer_equivalence(left, right) == "NOT_EQUIVALENT"
        for index, left in enumerate(answers)
        for right in answers[index + 1:]
    )


# ── B1: deterministic verification-gated retry checks ────────────────────


def _conflicting_answer_pair(response: str) -> tuple[str, str] | None:
    """Return the first pair of explicit, provably different answers."""
    answers = [answer.strip() for answer in _ANSWER_MARKER_RE.findall(response) if answer.strip()]
    for index, left in enumerate(answers):
        for right in answers[index + 1:]:
            if answer_equivalence(left, right) == "NOT_EQUIVALENT":
                return left, right
    return None


def _single_scalar_value(answer: str) -> Fraction | None:
    """Return an exact scalar value, or None for structured/non-scalar text."""
    if not isinstance(answer, str):
        return None
    value = re.sub(r"\s+", "", answer)
    value = re.sub(r"^[A-Za-z\u4e00-\u9fff]{1,6}\s*[＝=:：]", "", value)
    percent = value.endswith(("%", "％"))
    if percent:
        value = value[:-1]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\d+/\d+)", value) and not re.fullmatch(r"\\[df]?rac\{[\d.]+\}\{[\d.]+\}", value):
        return None
    parsed = _parse_rational_token(value)
    if parsed is None:
        return None
    return parsed / 100 if percent else parsed


_GATE_INTERROGATIVE_RE = re.compile(r"求|多少|几|是否|哪")
_GATE_PROBABILITY_RE = re.compile(r"概率|可能性")
_GATE_EXPECTATION_RE = re.compile(r"期望|均值|方差|标准差")
_GATE_COUNT_RE = re.compile(r"个数|数量|有多少|共有多少|多少个|几种|多少种|种数|条数|人数|件数|方案")
_GATE_AVERAGE_RE = re.compile(r"平均|比例|百分")


def _interrogative_sentences(problem: str) -> list[str]:
    sentences = re.split(r"[。；;！!？?\n]+", problem or "")
    return [sentence for sentence in sentences if _GATE_INTERROGATIVE_RE.search(sentence)]


def _sanity_violation(problem: str, answer: str) -> str | None:
    """Return a violated probability/count constraint when it is explicit."""
    value = _single_scalar_value(answer)
    if value is None:
        return None
    for sentence in _interrogative_sentences(problem):
        if _GATE_PROBABILITY_RE.search(sentence) and not _GATE_EXPECTATION_RE.search(sentence):
            if not 0 <= value <= 1:
                return f"题面所求为概率，取值必须在区间 [0,1] 内（当前 {answer}）"
        if _GATE_COUNT_RE.search(sentence) and not _GATE_AVERAGE_RE.search(sentence):
            if value < 0 or value.denominator != 1:
                return f"题面所求为计数，必须是非负整数（当前 {answer}）"
    return None


_GATE_MODE_PRIORITY = ("truncation", "conflict", "sanity", "unstructured", "placeholder", "no_answer")


def run_answer_checks(
    problem: str,
    problem_type: str,
    response: str,
    answer: str,
    structured: bool | None,
) -> dict[str, Any]:
    """Run B1's six deterministic checks without making a model call."""
    numeric_type = problem_type not in _NON_NUMERIC_TASK_TYPES
    signals = _truncation_signals(response, answer)
    structural = [signal for signal in signals if signal != "no_extractable_answer"]
    if structural:
        return {"status": "fail", "mode": "truncation", "detail": {"signals": structural}}

    pair = _conflicting_answer_pair(response or "")
    if pair:
        return {"status": "fail", "mode": "conflict", "detail": {"first": pair[0], "second": pair[1]}}

    if not numeric_type:
        if structured is False:
            return {"status": "fail", "mode": "unstructured", "detail": None}
        return {"status": "pass", "mode": None, "detail": None}

    if not answer:
        mode = "placeholder" if _has_placeholder_answer(response or "") else "no_answer"
        return {"status": "fail", "mode": mode, "detail": {"signals": signals}}
    violation = _sanity_violation(problem, answer)
    if violation:
        return {"status": "fail", "mode": "sanity", "detail": {"constraint": violation, "answer": answer}}
    return {"status": "pass", "mode": None, "detail": None}
