"""Pure contracts, candidate types, and response parsers for the math harness.

The orchestration module re-exports these names through its existing seam so
callers and tests do not depend on the internal file layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
import unicodedata
from typing import Any, Callable, Iterable, Mapping

MAX_PROBLEM_CHARS = 12_000
MAX_RESPONSE_CHARS = 24_000
MAX_CANDIDATE_CHARS = 256
MAX_REASON_CHARS = 240


def _prompt_problem(problem: str, reference_context: str) -> str:
    if not reference_context or reference_context in problem:
        return problem
    return f"{problem}\n\n{reference_context}"

STATE_START = "start"
STATE_ATTEMPT_A = "attempt_a"
STATE_CANDIDATE_A = "candidate_a"
STATE_ATTEMPT_B = "attempt_b"
STATE_CANDIDATE_B = "candidate_b"
STATE_CONFLICT = "conflict"
STATE_CRITIC = "critic"
STATE_REPAIR = "repair"
STATE_CONTINUATION = "continuation"
STATE_DEEP_PRIMARY = "deep_primary"
STATE_DEEP_REVIEW = "deep_review"
STATE_DEEP_CONTINUATION = "deep_continuation"
STATE_DEEP_CRITIC = "deep_critic"
STATE_SELECTED = "selected"
STATE_ABSTAINED = "abstained"
STATE_FINALIZED = "finalized"

CANDIDATE_MISSING = "missing"
CANDIDATE_PARSED = "parsed"
CANDIDATE_TRUNCATED = "truncated_with_candidate"
CANDIDATE_CONFLICT = "conflict"
CANDIDATE_REJECTED = "rejected"
CANDIDATE_VERIFIED = "verified"

ANSWER_INTEGER = "integer"
ANSWER_RATIONAL = "rational"
ANSWER_EXACT_EXPRESSION = "exact_expression"
ANSWER_SET = "set"
ANSWER_CHOICE = "choice"
ANSWER_SCALAR = "scalar"
ANSWER_PROOF = "proof"
ANSWER_DERIVATION = "derivation"
ANSWER_EXPLANATION = "explanation"
ANSWER_UNKNOWN = "unknown"

ANSWER_SHAPE_SINGLE_NUMERIC = "single_numeric"
ANSWER_SHAPE_PARAMETERIZED_EXPRESSION = "parameterized_expression"
ANSWER_SHAPE_FINITE_SET = "finite_set"
ANSWER_SHAPE_INTERVAL_OR_RANGE = "interval_or_range"
ANSWER_SHAPE_FUNCTION_FAMILY = "function_family"
ANSWER_SHAPE_PROOF_TEXT = "proof_text"
ANSWER_SHAPE_UNKNOWN = "unknown"

REASONING_RISK_DIRECT = "direct"
REASONING_RISK_STRUCTURED = "structured"
REASONING_RISK_DEEP = "deep"

ROUTE_CONFIDENCE_HIGH = "high"
ROUTE_CONFIDENCE_MEDIUM = "medium"
ROUTE_CONFIDENCE_LOW = "low"


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _error_category(exc: BaseException) -> str:
    """Return a stable, non-sensitive failure category."""
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    if "timeout" in name or "timeout" in detail or "deadline" in detail:
        return "timeout"
    if "rate" in name or "rate" in detail or "429" in detail:
        return "rate_limit"
    if "configuration" in name or "configuration" in detail:
        return "configuration"
    return "client_error"


def _as_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        result = int(value.strip())
    else:
        raise ValueError("invalid_integer")
    if minimum is not None and result < minimum:
        raise ValueError("integer_out_of_bounds")
    if maximum is not None and result > maximum:
        raise ValueError("integer_out_of_bounds")
    return result


def _parse_numeric(value: str) -> Fraction | None:
    compact = re.sub(r"\s+", "", value or "")
    compact = compact.replace("−", "-").replace(r"\left", "").replace(r"\right", "")
    frac = re.fullmatch(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", compact)
    if frac:
        compact = f"{frac.group(1)}/{frac.group(2)}"
    if not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:/[+-]?(?:\d+(?:\.\d*)?|\.\d+))?",
        compact,
    ):
        return None
    try:
        if "/" in compact:
            left, right = compact.split("/", 1)
            return Fraction(Decimal(left)) / Fraction(Decimal(right))
        return Fraction(Decimal(compact))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def _format_numeric(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _strip_math_wrappers(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "").strip()
    text = text.strip("。；;，, \t\r\n")
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$$"):
        text = text[1:-2].strip()
    elif text.startswith(r"\[") and text.endswith(r"\]"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    if text.startswith(r"\(") and text.endswith(r"\)"):
        text = text[2:-2].strip()
    if text.endswith("$$"):
        text = text[:-2].strip()
    elif text.endswith(r"\]"):
        text = text[:-2].strip()
    if text.count("$") == 1 and (text.startswith("$") or text.endswith("$")):
        text = text.strip("$").strip()
    return text


def _scalar_rhs(value: str) -> str:
    """Extract a final scalar RHS from a bounded equality chain."""
    clean = _strip_math_wrappers(value)
    parts = re.split(r"(?<![!<>≤≥])=(?!=)", clean)
    if len(parts) > 1 and parts[-1].strip():
        return _strip_math_wrappers(parts[-1].strip())
    return clean


def _is_placeholder(value: str) -> bool:
    compact = _strip_math_wrappers(value).lower()
    if not compact:
        return True
    if compact in {
        "unknown",
        "未知",
        "不确定",
        "无法确定",
        "[answer]",
        "<answer>",
        "答案",
        "最终答案",
        "<答案>",
        "<result>",
        "[core answer]",
        "不知道",
        "i don't know",
        "i do not know",
        "not sure",
        "cannot determine",
        "can't determine",
        "n/a",
        "null",
        "none",
    }:
        return True
    return bool(re.fullmatch(r"(?:<[^>]*>|\[[^\]]*\]|\.{3,}|…+)", compact))


def _balanced(value: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in value:
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def _extract_boxed(text: str) -> list[str]:
    values: list[str] = []
    cursor = 0
    marker = r"\boxed{"
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            return values
        depth = 1
        index = start + len(marker)
        content_start = index
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth == 0:
            value = text[content_start : index - 1].strip()
            if value:
                values.append(value)
        cursor = max(index, start + 1)


def _answer_type_from_problem(problem: str) -> str:
    text = (problem or "").strip()
    if re.search(r"(?:选择|选项|单选|多选|\bchoose\b|\bselect\b)", text, re.I):
        return ANSWER_CHOICE
    if re.search(r"(?:证明|求证|\bprove\b|\bshow\s+that\b)", text, re.I):
        return ANSWER_PROOF
    if re.search(r"(?:推导|导出|推演|\bderive\b|\bdeduce\b)", text, re.I):
        return ANSWER_DERIVATION
    if re.search(r"(?:解释|说明理由|阐述|为什么|\bexplain\b|\bdescribe\b)", text, re.I):
        return ANSWER_EXPLANATION
    return ANSWER_SCALAR


def _answer_shape_from_problem(problem: str) -> tuple[str, int]:
    """Infer a bounded answer shape and the number of competing shape signals."""
    text = (problem or "").strip()
    range_is_answer_shape = bool(re.search(
        r"(?:取值范围|值域|取值区间|范围|\brange\b|\binterval\b|\bdomain\b|\bset\s+of\s+values\b)",
        text,
        re.I,
    ))
    # A bounded output domain such as "give the value in the range [0, N)"
    # constrains a scalar remainder; it does not ask the solver to return an
    # interval. Keep that wording on the numeric answer lane.
    if re.search(
        r"\b(?:provide|give)\s+(?:the\s+)?(?:value|answer)\s+in\s+the\s+range\b",
        text,
        re.I,
    ) or re.search(r"\bremainder\b[\s\S]{0,80}\brange\b", text, re.I):
        range_is_answer_shape = False
    signals: list[tuple[str, bool]] = [
        (
            ANSWER_SHAPE_FUNCTION_FAMILY,
            bool(re.search(
                r"(?:所有|全部|求出所有|找出所有|find\s+all|determine\s+all|all\s+functions?)"
                r"[\s\S]{0,40}(?:函数|functions?|mappings?|polynomials?)",
                text,
                re.I,
            )),
        ),
        (
            ANSWER_SHAPE_INTERVAL_OR_RANGE,
            range_is_answer_shape,
        ),
        (
            ANSWER_SHAPE_FINITE_SET,
            bool(re.search(
                r"(?:所有可能(?:的)?(?:值|解)|所有解|解集|根的集合|求出集合|all\s+possible\s+values?"
                r"|all\s+solutions?|solution\s+set|set\s+of\s+(?:solutions?|roots?)|all\s+pairs)",
                text,
                re.I,
            )),
        ),
        (
            ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
            bool(re.search(
                r"(?:用[^。；;\n]{0,20}表示|关于[^。；;\n]{0,20}的表达式|in\s+terms\s+of|as\s+a\s+function\s+of"
                r"|\b[A-Za-z]\s*=\s*[A-Za-z]\s*\([^)]{1,32}\)|\bT\s*=\s*T\s*\([^)]{1,32}\))",
                text,
                re.I,
            )),
        ),
        (
            ANSWER_SHAPE_PROOF_TEXT,
            bool(re.search(
                r"(?:证明|求证|证明题|with\s+proof|prove|show\s+that|give\s+a\s+proof)",
                text,
                re.I,
            )),
        ),
    ]
    matched = [shape for shape, present in signals if present]
    if len(matched) == 1:
        return matched[0], 1
    if len(matched) > 1:
        # Proof is the safest shape when it competes with another request.
        return (ANSWER_SHAPE_PROOF_TEXT if ANSWER_SHAPE_PROOF_TEXT in matched else matched[0]), len(matched)
    if re.search(r"(?:选择|选项|单选|多选|\bchoose\b|\bselect\b)", text, re.I):
        # The contract has no separate choice shape; a short choice is still
        # a single-answer direct lane, while the answer_type retains choice.
        return ANSWER_SHAPE_SINGLE_NUMERIC, 1
    if re.search(
        r"(?:计算|求|求出|求值|最小值|最大值|多少|概率|余数|compute|calculate|evaluate|remainder|find\s+the\s+(?:number|value|minimum|maximum|probability|remainder))",
        text,
        re.I,
    ):
        return ANSWER_SHAPE_SINGLE_NUMERIC, 1
    return ANSWER_SHAPE_UNKNOWN, 0


def _reasoning_risk_from_problem(problem: str, answer_shape: str) -> str:
    """Estimate reasoning risk independently from the requested answer shape."""
    text = (problem or "").strip()
    deep_signal = bool(re.search(
        r"(?:所有|全部|任意|对于任意|存在|序列|排列|组合|函数|多项式|图|三角形|概率|无限|不同|满足条件|边界|最小值|最大值"
        r"|all|any|exists|sequence|permutation|polynomial|function|graph|triangle|probability|infinite|distinct|such that|boundary|minimum|maximum)",
        text,
        re.I,
    ))
    structured_signal = bool(re.search(
        r"(?:推导|解释|说明|证明|求证|条件|分情况|derive|explain|prove|show|condition|case)",
        text,
        re.I,
    ))
    simple_arithmetic = bool(re.fullmatch(r"\s*(?:计算|求|compute|calculate)?\s*[0-9\s()+*/^×÷.=-]{1,48}\s*[?。！？]?", text, re.I))
    if simple_arithmetic and not deep_signal:
        return REASONING_RISK_DIRECT
    if deep_signal or len(text) > 220 or answer_shape in {
        ANSWER_SHAPE_FUNCTION_FAMILY,
        ANSWER_SHAPE_FINITE_SET,
        ANSWER_SHAPE_INTERVAL_OR_RANGE,
        ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
        ANSWER_SHAPE_PROOF_TEXT,
    }:
        return REASONING_RISK_DEEP
    if structured_signal or len(text) > 90:
        return REASONING_RISK_STRUCTURED
    return REASONING_RISK_DIRECT


def _task_signal_count(problem: str) -> int:
    text = (problem or "").strip()
    patterns = (
        r"(?:选择|选项|单选|多选|\bchoose\b|\bselect\b)",
        r"(?:证明|求证|\bprove\b|\bshow\s+that\b)",
        r"(?:推导|导出|推演|\bderive\b|\bdeduce\b)",
        r"(?:解释|说明理由|阐述|为什么|\bexplain\b|\bdescribe\b)",
    )
    return sum(bool(re.search(pattern, text, re.I)) for pattern in patterns)


@dataclass(frozen=True)
class ProblemContract:
    """Small host contract separating answer shape from reasoning risk."""

    answer_shape: str
    reasoning_risk: str
    route_confidence: str

    def __post_init__(self) -> None:
        if self.answer_shape not in {
            ANSWER_SHAPE_SINGLE_NUMERIC,
            ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
            ANSWER_SHAPE_FINITE_SET,
            ANSWER_SHAPE_INTERVAL_OR_RANGE,
            ANSWER_SHAPE_FUNCTION_FAMILY,
            ANSWER_SHAPE_PROOF_TEXT,
            ANSWER_SHAPE_UNKNOWN,
        }:
            raise ValueError("invalid_answer_shape")
        if self.reasoning_risk not in {
            REASONING_RISK_DIRECT,
            REASONING_RISK_STRUCTURED,
            REASONING_RISK_DEEP,
        }:
            raise ValueError("invalid_reasoning_risk")
        if self.route_confidence not in {
            ROUTE_CONFIDENCE_HIGH,
            ROUTE_CONFIDENCE_MEDIUM,
            ROUTE_CONFIDENCE_LOW,
        }:
            raise ValueError("invalid_route_confidence")

    def as_dict(self) -> dict[str, str]:
        return {
            "answer_shape": self.answer_shape,
            "reasoning_risk": self.reasoning_risk,
            "route_confidence": self.route_confidence,
        }


def _infer_value_type(value: str, expected: str) -> str:
    clean = _strip_math_wrappers(value)
    if expected == ANSWER_CHOICE:
        return ANSWER_CHOICE if re.fullmatch(r"[A-Da-d](?:[.)）])?", clean) else ANSWER_UNKNOWN
    if expected in {ANSWER_PROOF, ANSWER_DERIVATION, ANSWER_EXPLANATION}:
        return expected
    if re.fullmatch(r"[+-]?\d+", clean):
        return ANSWER_INTEGER
    if _parse_numeric(clean) is not None:
        return ANSWER_RATIONAL
    if clean.startswith("{") and clean.endswith("}"):
        return ANSWER_SET
    if re.search(r"[A-Za-z\\]|[=<>≤≥^]|\b(?:sqrt|sin|cos|tan|log|ln)\b", clean, re.I):
        return ANSWER_EXACT_EXPRESSION
    return ANSWER_SCALAR if len(clean) <= 48 else ANSWER_UNKNOWN


def _canonical_set(value: str) -> str | None:
    text = _strip_math_wrappers(value)
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1].strip()
    pieces = [part.strip() for part in re.split(r"[,，、]", body) if part.strip()]
    if len(pieces) < 2:
        return None
    numbers = [_parse_numeric(part) for part in pieces]
    if any(number is None for number in numbers):
        return None
    return "{" + ",".join(_format_numeric(number) for number in sorted(set(numbers))) + "}"


def normalize_value(value: str) -> str:
    """Apply only bounded, representation-level normalization."""
    clean = _strip_math_wrappers(value).replace("−", "-")
    clean = clean.replace(r"\left", "").replace(r"\right", "")
    clean = clean.replace(r"\cdot", "*").replace("×", "*")
    clean = re.sub(r"\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", clean)
    canonical_set = _canonical_set(clean)
    if canonical_set is not None:
        return canonical_set
    numeric = _parse_numeric(clean)
    if numeric is not None:
        return _format_numeric(numeric)
    choice = re.fullmatch(r"([A-Da-d])(?:[.)）])?", clean)
    if choice:
        return choice.group(1).upper()
    return re.sub(r"\s+", "", clean)


def value_equivalence(left: str, right: str) -> str:
    left_normalized = normalize_value(left)
    right_normalized = normalize_value(right)
    if not left_normalized or not right_normalized:
        return "UNKNOWN"
    if left_normalized == right_normalized:
        return "EQUIVALENT"
    left_numeric = _parse_numeric(left_normalized)
    right_numeric = _parse_numeric(right_normalized)
    if left_numeric is not None and right_numeric is not None:
        return "NOT_EQUIVALENT"
    if re.fullmatch(r"[A-D]", left_normalized) and re.fullmatch(r"[A-D]", right_normalized):
        return "NOT_EQUIVALENT"
    if left_normalized.startswith("{") and right_normalized.startswith("{"):
        return "NOT_EQUIVALENT"
    return "UNKNOWN"


def _has_conflict(candidates: Iterable["Candidate"]) -> bool:
    values = list(candidates)
    return any(
        value_equivalence(left.value, right.value) == "NOT_EQUIVALENT"
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    )


def _unique_candidates(candidates: Iterable["Candidate"]) -> list["Candidate"]:
    unique: list[Candidate] = []
    for candidate in candidates:
        if any(value_equivalence(candidate.value, existing.value) == "EQUIVALENT" for existing in unique):
            continue
        unique.append(candidate)
    return unique


@dataclass

class Candidate:
    """A bounded answer candidate and the inference mode that produced it."""

    candidate_id: str
    value: str
    normalized_value: str
    answer_type: str
    source: str
    extraction_status: str
    proof_status: str = "not_evaluated"
    verification_status: str = "unverified"
    checks: list[dict[str, Any]] = field(default_factory=list)
    reason_summary: str = "candidate_extracted"
    response: str = field(default="", repr=False)
    reasoning_mode: str = "inherit"
    structural_validity: str = "unassessed"
    answer_complete: bool = True
    answer_complete_reason: str = ""
    trust_confidence: str = "unknown"
    trust_reason: str = ""

    def ledger_dict(self) -> dict[str, Any]:
        """Return safe candidate metadata, including a mode only when explicit."""
        entry = {
            "candidate_id": self.candidate_id,
            "value": _clip(self.value, MAX_CANDIDATE_CHARS),
            "normalized_value": _clip(self.normalized_value, MAX_CANDIDATE_CHARS),
            "answer_type": self.answer_type,
            "source": self.source,
            "extraction_status": self.extraction_status,
            "proof_status": self.proof_status,
            "verification_status": self.verification_status,
            "structural_validity": self.structural_validity,
            "answer_complete": bool(self.answer_complete),
            "answer_complete_reason": _clip(self.answer_complete_reason, MAX_REASON_CHARS),
            "trust_confidence": self.trust_confidence,
            "trust_reason": _clip(self.trust_reason, MAX_REASON_CHARS),
            "checks": [dict(check) for check in self.checks[:4]],
            "reason_summary": _clip(self.reason_summary, MAX_REASON_CHARS),
        }
        if self.reasoning_mode != "inherit":
            entry["reasoning_mode"] = self.reasoning_mode
        return entry


@dataclass
class ParsedResponse:
    candidates: list[Candidate]
    status: str
    answer_type: str
    truncated: bool
    reason_summary: str
    finish_reason: str | None = None


def _candidate_value_valid(value: str, expected_type: str) -> tuple[bool, str, str]:
    clean = _strip_math_wrappers(value)
    if not clean or len(clean) > MAX_CANDIDATE_CHARS or _is_placeholder(clean):
        return False, ANSWER_UNKNOWN, "placeholder_or_empty"
    if not _balanced(clean) or re.search(r"(?:[=+\-*/^,(\[{]|\\)\s*$", clean):
        return False, ANSWER_UNKNOWN, "incomplete_expression"
    actual_type = _infer_value_type(clean, expected_type)
    if actual_type == ANSWER_UNKNOWN:
        return False, actual_type, "type_mismatch"
    if expected_type == ANSWER_CHOICE and actual_type != ANSWER_CHOICE:
        return False, actual_type, "type_mismatch"
    if expected_type in {ANSWER_PROOF, ANSWER_DERIVATION, ANSWER_EXPLANATION}:
        return True, actual_type, "structured_conclusion"
    if re.search(r"[，。；;？！]", clean) or (
        re.search(r"[\u4e00-\u9fff]", clean) and actual_type != ANSWER_SCALAR
    ):
        return False, actual_type, "prose_in_scalar_answer"
    return True, actual_type, "candidate_extracted"


_MARKER_RE = re.compile(
    r"^\s*(?:\*\*|\*)?\s*(?:最终答案|答案|final\s+answer|answer|final)\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?\s*$",
    re.IGNORECASE,
)


def _response_is_truncated(response: str, finish_reason: str | None, candidates: list[Candidate]) -> bool:
    reason = (finish_reason or "").strip().lower()
    if reason in {"length", "max_tokens", "max_output_tokens", "truncated"}:
        return True
    text = (response or "").rstrip()
    heuristic = bool(
        re.search(r"(?:[=+\-*/^,(\[{]|\\)\s*$", text)
        or text.endswith(("因此", "所以", "故", "从而", "得到", "可得", "解得"))
        or (r"\boxed{" in text and not _balanced(text[text.rfind(r"\boxed{") :]))
    )
    return heuristic and not (len(candidates) == 1 and text.endswith(candidates[0].value))


class HostParser:
    """Answer-type-aware parser for ordinary free-format responses."""

    def parse(
        self,
        response: str | None,
        *,
        problem: str,
        source: str,
        finish_reason: str | None = None,
    ) -> ParsedResponse:
        expected = _answer_type_from_problem(problem)
        text = response if isinstance(response, str) else ""
        text = text[:MAX_RESPONSE_CHARS]
        values: list[tuple[str, str]] = []

        for line in text.splitlines():
            match = _MARKER_RE.match(line)
            if match:
                values.append((match.group(1), "explicit_marker"))

        if not values:
            for boxed in _extract_boxed(text):
                values.append((boxed, "boxed"))

        if not values and expected not in {ANSWER_PROOF, ANSWER_DERIVATION, ANSWER_EXPLANATION}:
            terminal_patterns = (
                r"(?i)(?:答案是|结果是|answer\s+is|therefore|thus|所以|因此|最终得到|得到|可得|解得)\s*[:：]?\s*([^\n。；;]{1,128})",
            )
            for pattern in terminal_patterns:
                matches = list(re.finditer(pattern, text))
                if matches:
                    values.append((matches[-1].group(1), "terminal_phrase"))
                    break

        if not values and expected not in {ANSWER_PROOF, ANSWER_DERIVATION, ANSWER_EXPLANATION}:
            for line in reversed(text.splitlines()):
                clean_line = line.strip()
                if (
                    clean_line
                    and len(clean_line) <= MAX_CANDIDATE_CHARS
                    and not re.search(r"[\u4e00-\u9fff，。；;？！]", clean_line)
                    and (re.search(r"\d", clean_line) or re.search(r"[=<>≤≥]", clean_line))
                ):
                    # A scalar conclusion is often written as a short chain,
                    # e.g. ``2^7 = 128``. Keep the final RHS so the host
                    # compares the answer rather than the derivation line.
                    parts = re.split(r"(?<![!<>≤≥])=(?!=)", clean_line)
                    if len(parts) > 1 and parts[-1].strip():
                        values.append((parts[-1].strip(), "terminal_math_rhs"))
                    else:
                        values.append((clean_line, "terminal_math_line"))
                    break

        provisional: list[Candidate] = []
        rejected = False
        for raw_value, extraction_source in values:
            value = _scalar_rhs(raw_value) if expected == ANSWER_SCALAR else _strip_math_wrappers(raw_value)
            if expected == ANSWER_CHOICE:
                choice = re.fullmatch(r"([A-Da-d])(?:[.)）])?", value)
                if choice:
                    value = choice.group(1).upper()
            valid, actual_type, reason = _candidate_value_valid(value, expected)
            if not valid:
                rejected = True
                continue
            if any(value_equivalence(value, existing.value) == "EQUIVALENT" for existing in provisional):
                continue
            provisional.append(
                Candidate(
                    candidate_id=f"{source}_{len(provisional) + 1}",
                    value=value,
                    normalized_value=normalize_value(value),
                    answer_type=actual_type,
                    source=source,
                    extraction_status=CANDIDATE_PARSED,
                    reason_summary=reason,
                    response=text,
                )
            )

        truncated = _response_is_truncated(text, finish_reason, provisional)
        if len(provisional) == 1 and expected == ANSWER_SCALAR:
            from reasoning_agent.answer_completeness import assess_answer_completeness

            complete, complete_reason = assess_answer_completeness(
                provisional[0],
                answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
                parsed=type("ParsedProbe", (), {"truncated": truncated})(),
            )
            provisional[0].answer_complete = complete
            provisional[0].answer_complete_reason = complete_reason
        if provisional and truncated:
            for candidate in provisional:
                candidate.extraction_status = CANDIDATE_TRUNCATED
            status = CANDIDATE_TRUNCATED
            reason = "truncated_with_unique_candidate" if len(provisional) == 1 else "truncated_with_candidates"
        elif len(provisional) > 1 and _has_conflict(provisional):
            for candidate in provisional:
                candidate.extraction_status = CANDIDATE_CONFLICT
            status = CANDIDATE_CONFLICT
            reason = "conflicting_candidates_retained"
        elif provisional:
            status = CANDIDATE_PARSED
            reason = "candidate_extracted"
        elif truncated:
            status = "truncated_without_candidate"
            reason = "truncated_without_candidate"
        elif rejected or text.strip():
            status = CANDIDATE_REJECTED
            reason = "candidate_rejected"
        else:
            status = CANDIDATE_MISSING
            reason = "no_response"
        return ParsedResponse(provisional, status, expected, truncated, reason, finish_reason)


@dataclass
class TypedParseResult:
    """A typed answer formation result without retaining raw response text."""

    answer_shape: str
    status: str
    typed_complete: bool
    candidate: Candidate | None
    truncated: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_shape": self.answer_shape,
            "status": self.status,
            "typed_complete": self.typed_complete,
            "candidate": self.candidate.ledger_dict() if self.candidate else None,
            "truncated": self.truncated,
            "reason": _clip(self.reason, MAX_REASON_CHARS),
        }


class TypedParser:
    """Shape-aware parser used by the revised Deep lane."""

    _MARKER = re.compile(
        r"^\s*(?:\*\*|\*)?\s*(?:最终答案|答案|final\s+answer|answer|final)\s*[:：]\s*(.*?)\s*(?:\*\*|\*)?\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def _raw_values(text: str, contract: ProblemContract) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        for line in text.splitlines():
            match = TypedParser._MARKER.match(line)
            if match:
                values.append((match.group(1).strip(), "explicit_marker"))
        if values:
            return values
        for boxed in _extract_boxed(text):
            values.append((boxed, "boxed"))
        if values:
            return values
        if contract.answer_shape == ANSWER_SHAPE_PROOF_TEXT:
            return values
        terminal = re.findall(
            r"(?i)(?:答案是|结果是|answer\s+is|therefore|thus|所以|因此|最终得到|得到|可得|解得)\s*[:：]?\s*([^\n。；;]{1,128})",
            text,
        )
        if terminal:
            return [(terminal[-1].strip(), "terminal_phrase")]
        if contract.reasoning_risk == REASONING_RISK_DIRECT and contract.answer_shape == ANSWER_SHAPE_SINGLE_NUMERIC:
            for line in reversed(text.splitlines()):
                clean = line.strip()
                if clean and len(clean) <= MAX_CANDIDATE_CHARS and re.search(r"\d", clean):
                    return [(clean, "terminal_math_line")]
        return values

    @staticmethod
    def _shape_value(value: str, shape: str) -> tuple[bool, str, str]:
        clean = _strip_math_wrappers(value).strip()
        interval_notation = bool(re.fullmatch(r"(?:\[[^\[\]]+\]|\([^()]+\))", clean))
        if not clean or (_is_placeholder(clean) and not (shape == ANSWER_SHAPE_INTERVAL_OR_RANGE and interval_notation)):
            return False, ANSWER_UNKNOWN, "placeholder_or_empty"
        if not _balanced(clean) or clean.endswith(("=", "+", "-", "*", "/", "^", "\\")):
            return False, ANSWER_UNKNOWN, "incomplete_expression"
        if shape == ANSWER_SHAPE_SINGLE_NUMERIC:
            clean = _scalar_rhs(clean)
            if _parse_numeric(clean) is None and not re.fullmatch(r"(?:\\sqrt\{[^{}]+\}|[+-]?[0-9][0-9A-Za-z^*/().\\{}]*)", clean):
                return False, ANSWER_UNKNOWN, "not_single_numeric"
            return True, _infer_value_type(clean, ANSWER_SCALAR), "typed_complete"
        if shape == ANSWER_SHAPE_PARAMETERIZED_EXPRESSION:
            if not re.search(r"[A-Za-z]", clean) or not re.search(r"[=+*/^()-]", clean) or re.search(r"[.!?]$", clean):
                return False, ANSWER_UNKNOWN, "parameterized_expression_incomplete"
            return True, ANSWER_EXACT_EXPRESSION, "typed_complete"
        if shape == ANSWER_SHAPE_FINITE_SET:
            canonical = _canonical_set(clean)
            if canonical is not None:
                return True, ANSWER_SET, "typed_complete"
            if not (clean.startswith(("{", "\\{")) and clean.endswith(("}", "\\}"))):
                return False, ANSWER_UNKNOWN, "finite_set_not_closed"
            return True, ANSWER_SET, "typed_complete"
        if shape == ANSWER_SHAPE_INTERVAL_OR_RANGE:
            if not (
                re.fullmatch(r"(?:\[[^\[\]]+\]|\([^()]+\))", clean)
                or re.search(r"(?:[A-Za-z]+\s*[<>≤≥]=?\s*[^,;]+(?:[,;]\s*)?){1,2}", clean)
                or re.search(r"(?:x|y|z|t)\s*∈\s*", clean, re.I)
            ):
                return False, ANSWER_UNKNOWN, "interval_or_range_incomplete"
            return True, ANSWER_EXACT_EXPRESSION, "typed_complete"
        if shape == ANSWER_SHAPE_FUNCTION_FAMILY:
            if not re.search(r"\b[A-Za-z]\s*\([^)]*\)\s*=", clean):
                return False, ANSWER_UNKNOWN, "function_family_incomplete"
            return True, ANSWER_EXACT_EXPRESSION, "typed_complete"
        return False, ANSWER_UNKNOWN, "unsupported_typed_shape"

    def parse(
        self,
        response: str | None,
        contract: ProblemContract,
        *,
        finish_reason: str | None = None,
    ) -> TypedParseResult:
        text = response if isinstance(response, str) else ""
        text = text[:MAX_RESPONSE_CHARS]
        finish = (finish_reason or "").strip().lower()
        truncated = finish in {"length", "max_tokens", "max_output_tokens", "truncated"}
        if contract.answer_shape == ANSWER_SHAPE_PROOF_TEXT:
            complete_markers = re.search(
                r"(?:证毕|q\.e\.d\.?|qed|therefore|thus|hence|命题成立|结论)\s*[。.!！]?$",
                text.strip(),
                re.I,
            )
            if text.strip() and complete_markers and not truncated:
                candidate = Candidate(
                    "typed_proof_1",
                    _clip(text.splitlines()[-1], MAX_CANDIDATE_CHARS),
                    "",
                    ANSWER_PROOF,
                    "typed_parser",
                    CANDIDATE_PARSED,
                    proof_status="complete",
                    response=text,
                )
                return TypedParseResult(contract.answer_shape, "typed_complete", True, candidate, False, "proof_complete")
            status = "typed_incomplete" if truncated or text.strip() else "typed_missing"
            return TypedParseResult(contract.answer_shape, status, False, None, truncated, "proof_not_complete")

        raw_values = self._raw_values(text, contract)
        candidates: list[Candidate] = []
        for raw_value, source in raw_values[:4]:
            value = _strip_math_wrappers(raw_value)
            valid, value_type, reason = self._shape_value(value, contract.answer_shape)
            if not valid:
                continue
            normalized = normalize_value(_scalar_rhs(value) if contract.answer_shape == ANSWER_SHAPE_SINGLE_NUMERIC else value)
            if any(value_equivalence(normalized, existing.normalized_value) == "EQUIVALENT" for existing in candidates):
                continue
            candidates.append(
                Candidate(
                    f"typed_{len(candidates) + 1}",
                    value,
                    normalized,
                    value_type,
                    "typed_parser",
                    CANDIDATE_PARSED,
                    response=text,
                    reason_summary=reason,
                )
            )
        # The public client contract may expose only a string, so a missing
        # finish_reason cannot be treated as proof that the response ended
        # cleanly. Reuse the bounded host heuristic for an obviously open
        # expression or unfinished conclusion.
        truncated = _response_is_truncated(text, finish_reason, candidates)
        if len(candidates) > 1:
            return TypedParseResult(contract.answer_shape, "typed_conflict", False, None, truncated, "multiple_typed_candidates")
        if not candidates:
            status = "typed_incomplete" if truncated or text.rstrip().endswith(("=", "+", "-", "*", "/", "^")) else "typed_missing" if not text.strip() else "typed_rejected"
            return TypedParseResult(contract.answer_shape, status, False, None, truncated, "no_typed_complete_candidate")
        candidate = candidates[0]
        if truncated:
            candidate.extraction_status = CANDIDATE_TRUNCATED
            return TypedParseResult(contract.answer_shape, "typed_incomplete", False, candidate, True, "truncated_typed_candidate")
        from reasoning_agent.answer_completeness import assess_answer_completeness

        complete, complete_reason = assess_answer_completeness(
            candidate,
            answer_shape=contract.answer_shape,
            parsed=type("TypedProbe", (), {"truncated": False, "typed_complete": True})(),
        )
        candidate.answer_complete = complete
        candidate.answer_complete_reason = complete_reason
        if not complete:
            return TypedParseResult(contract.answer_shape, "typed_incomplete", False, candidate, False, complete_reason)
        return TypedParseResult(contract.answer_shape, "typed_complete", True, candidate, False, "typed_complete")
