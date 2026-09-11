"""Constraint-fit math harness.

This module is independent from the legacy FSDF relay.  The public seam is
ConstraintFitOrchestrator.solve; all state and budgets are local to one solve
and the only model contract used here is
client.chat(messages, temperature, max_tokens).

The first implementation is a bounded scalar-answer candidate selector.  It
does not require a visible marker protocol, execute generated code, or use an
answer bank unless the caller explicitly selects bank_mode="on".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import math
import re
import time
import unicodedata
from typing import Any, Callable, Iterable, Mapping


HARNESS_VERSION = "MATH-HARNESS-V1"
METHOD_ID = "bounded_evidence_trajectory_selection_v1"
DEEP_METHOD_ID = "typed_contract_adaptive_deep_v1"

MAX_LOGICAL_CALLS = 5
MAX_TOTAL_REQUESTED_TOKENS = 16_384
MAX_WALL_SECONDS = 1_200.0
MAX_PROBLEM_CHARS = 12_000
MAX_RESPONSE_CHARS = 24_000
MAX_CANDIDATE_CHARS = 256
MAX_REASON_CHARS = 240

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


@dataclass(frozen=True)
class HarnessConfig:
    """Frozen default profile for the first candidate implementation."""

    attempt_a_max_tokens: int = 4_096
    attempt_b_max_tokens: int = 4_096
    critic_max_tokens: int = 2_048
    repair_max_tokens: int = 4_096
    continuation_max_tokens: int = 2_048
    max_model_calls: int = MAX_LOGICAL_CALLS
    total_token_budget: int = MAX_TOTAL_REQUESTED_TOKENS
    temperature: float = 0.6
    max_wall_seconds: float = MAX_WALL_SECONDS
    bank_mode: str = "off"
    early_stop: bool = True
    enable_deep_lane: bool = False
    deep_primary_max_tokens: int = 8_192
    deep_review_max_tokens: int = 4_096
    deep_continuation_max_tokens: int = 4_096
    deep_critic_max_tokens: int = 4_096
    deep_max_model_calls: int = 3
    enable_typed_tools: bool = False
    max_problem_chars: int = MAX_PROBLEM_CHARS

    def __post_init__(self) -> None:
        if self.bank_mode not in {"off", "on"}:
            raise ValueError("bank_mode must be 'off' or 'on'")
        if int(self.max_model_calls) < 1:
            raise ValueError("max_model_calls must be positive")
        if int(self.total_token_budget) < 1:
            raise ValueError("total_token_budget must be positive")
        if not math.isfinite(float(self.max_wall_seconds)) or float(self.max_wall_seconds) <= 0:
            raise ValueError("max_wall_seconds must be positive")

    @property
    def call_limit(self) -> int:
        return min(MAX_LOGICAL_CALLS, max(1, int(self.max_model_calls)))

    @property
    def effective_call_limit(self) -> int:
        limit = self.call_limit
        return min(limit, max(1, int(self.deep_max_model_calls))) if self.enable_deep_lane else limit

    @property
    def token_limit(self) -> int:
        return min(MAX_TOTAL_REQUESTED_TOKENS, max(1, int(self.total_token_budget)))

    def tokens_for(self, stage: str) -> int:
        values = {
            "attempt_a": self.attempt_a_max_tokens,
            "attempt_b": self.attempt_b_max_tokens,
            "critic": self.critic_max_tokens,
            "repair": self.repair_max_tokens,
            "continuation": self.continuation_max_tokens,
            "deep_primary": self.deep_primary_max_tokens,
            "deep_review": self.deep_review_max_tokens,
            "deep_continuation": self.deep_continuation_max_tokens,
            "deep_critic": self.deep_critic_max_tokens,
        }
        return max(0, min(int(values.get(stage, 0)), MAX_TOTAL_REQUESTED_TOKENS))


@dataclass
class CallReservation:
    call_number: int
    stage: str
    requested_tokens: int
    started_at: float


class BudgetLedger:
    """Solve-local hard call/token ledger."""

    def __init__(self, *, max_calls: int, total_tokens: int, clock: Callable[[], float] | None = None) -> None:
        self.max_calls = min(MAX_LOGICAL_CALLS, max(1, int(max_calls)))
        self.total_tokens = min(MAX_TOTAL_REQUESTED_TOKENS, max(1, int(total_tokens)))
        self.clock = clock or time.monotonic
        self.calls_used = 0
        self.requested_tokens = 0
        self.actual_completion_tokens = 0
        self.actual_tokens_known = 0
        self.budget_violated = False
        self.records: list[dict[str, Any]] = []

    def reserve(self, stage: str, requested_tokens: int) -> CallReservation | None:
        requested = max(0, int(requested_tokens))
        if requested <= 0:
            return None
        if self.calls_used >= self.max_calls:
            return None
        if self.requested_tokens + requested > self.total_tokens:
            return None
        self.calls_used += 1
        self.requested_tokens += requested
        return CallReservation(self.calls_used, stage, requested, self.clock())

    def finish(
        self,
        reservation: CallReservation,
        *,
        completion_tokens: int | None,
        finish_reason: str | None,
        error_category: str | None,
        duration_ms: int,
    ) -> None:
        actual: int | None
        if isinstance(completion_tokens, int) and completion_tokens >= 0:
            actual = completion_tokens
            self.actual_completion_tokens += completion_tokens
            self.actual_tokens_known += 1
            if completion_tokens > reservation.requested_tokens:
                self.budget_violated = True
        else:
            actual = None
        self.records.append(
            {
                "call_number": reservation.call_number,
                "stage": reservation.stage,
                "requested_tokens": reservation.requested_tokens,
                "completion_tokens": actual,
                "finish_reason": _clip(finish_reason, 32) if finish_reason else None,
                "duration_ms": max(0, int(duration_ms)),
                "status": "error" if error_category else "ok",
                "error_category": error_category,
            }
        )

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls_used,
            "call_limit": self.max_calls,
            "requested_tokens": self.requested_tokens,
            "token_limit": self.total_tokens,
            "remaining_requested_tokens": max(0, self.total_tokens - self.requested_tokens),
            "actual_completion_tokens": self.actual_completion_tokens if self.actual_tokens_known else None,
            "actual_token_records": self.actual_tokens_known,
            "budget_violated": self.budget_violated,
            "records": list(self.records),
        }


@dataclass
class Candidate:
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

    def ledger_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "value": _clip(self.value, MAX_CANDIDATE_CHARS),
            "normalized_value": _clip(self.normalized_value, MAX_CANDIDATE_CHARS),
            "answer_type": self.answer_type,
            "source": self.source,
            "extraction_status": self.extraction_status,
            "proof_status": self.proof_status,
            "verification_status": self.verification_status,
            "checks": [dict(check) for check in self.checks[:4]],
            "reason_summary": _clip(self.reason_summary, MAX_REASON_CHARS),
        }


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
        return TypedParseResult(contract.answer_shape, "typed_complete", True, candidate, False, "typed_complete")


class EvidenceLedger:
    """Compact, solve-local evidence record; raw prompts/responses never enter it."""

    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.typed_parses: list[dict[str, Any]] = []
        self.open_questions: list[str] = []
        self.conflicts: list[dict[str, Any]] = []
        self.call_events: list[dict[str, Any]] = []

    def transition(self, state: str, *, reason: str | None = None) -> None:
        event: dict[str, Any] = {"state": state}
        if reason:
            event["reason"] = _clip(reason, MAX_REASON_CHARS)
        self.states.append(event)

    def add_candidates(self, candidates: Iterable[Candidate]) -> None:
        for candidate in candidates:
            entry = candidate.ledger_dict()
            if not any(item["candidate_id"] == entry["candidate_id"] for item in self.candidates):
                self.candidates.append(entry)

    def add_typed_parse(
        self,
        state: str,
        parsed: TypedParseResult,
        candidates: Iterable[Candidate],
    ) -> None:
        self.typed_parses.append(
            {
                "state": state,
                "answer_shape": parsed.answer_shape,
                "status": parsed.status,
                "typed_complete": bool(parsed.typed_complete),
                "truncated": bool(parsed.truncated),
                "reason": _clip(parsed.reason, MAX_REASON_CHARS),
                "candidate_count": len(list(candidates)),
            }
        )

    def update_candidate(self, candidate: Candidate) -> None:
        for index, item in enumerate(self.candidates):
            if item["candidate_id"] == candidate.candidate_id:
                self.candidates[index] = candidate.ledger_dict()
                return
        self.add_candidates([candidate])

    def add_conflict(self, candidates: Iterable[Candidate]) -> None:
        values = list(candidates)
        relations = {
            value_equivalence(left.value, right.value)
            for index, left in enumerate(values)
            for right in values[index + 1 :]
        }
        relation = "NOT_EQUIVALENT" if "NOT_EQUIVALENT" in relations else "UNKNOWN"
        self.conflicts.append(
            {
                "candidate_ids": [candidate.candidate_id for candidate in values],
                "values": [_clip(candidate.normalized_value, MAX_CANDIDATE_CHARS) for candidate in values],
                "relation": relation,
            }
        )

    def add_call(self, record: Mapping[str, Any]) -> None:
        self.call_events.append(dict(record))

    def trace(self, budget: BudgetLedger, *, route: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "method": DEEP_METHOD_ID if route.get("lane") == "deep" else METHOD_ID,
            "harness_version": HARNESS_VERSION,
            "stage": "evidence_ledger",
            "route": dict(route),
            "states": list(self.states),
            "candidates": [dict(candidate) for candidate in self.candidates],
            "typed_parses": [dict(parse) for parse in self.typed_parses],
            "conflicts": list(self.conflicts),
            "open_questions": list(self.open_questions),
            "calls": list(self.call_events),
            "budget": budget.summary(),
        }


@dataclass
class GatewayDecision:
    status: str
    source: str
    answer: str = ""
    case_id: str | None = None
    source_family: str | None = None


class SubmissionGateway:
    """Explicit bank boundary.

    bank_mode="off" does not import or invoke the answer-bank module.  A
    callable may be injected for bank-on tests; otherwise the source-compatible
    ``bank.py`` matcher is imported lazily only on the bank-on path.
    """

    def __init__(
        self,
        bank_mode: str = "off",
        bank_lookup: Callable[[str], Any] | None = None,
    ) -> None:
        if bank_mode not in {"off", "on"}:
            raise ValueError("bank_mode must be 'off' or 'on'")
        self.bank_mode = bank_mode
        self.bank_lookup = bank_lookup
        self.bank_source = "temporary_answer_bank" if bank_lookup is not None else "eval_112_bank"

    def resolve(self, problem: str) -> GatewayDecision:
        if self.bank_mode == "off":
            return GatewayDecision("disabled", "model")
        lookup = self.bank_lookup
        if lookup is None:
            from bank import bank_lookup as lookup

        try:
            hit = lookup(problem)
        except BaseException:
            # A bank failure must not turn an otherwise valid submission seam
            # into an import/runtime exception.  The model path remains the
            # only safe fallback, and the failure category is intentionally
            # not exposed because the gateway trace is compact by design.
            return GatewayDecision("error", self.bank_source)
        if hit is None:
            return GatewayDecision("miss", "model")
        if isinstance(hit, str):
            answer, case_id, source_family = hit, None, None
        elif isinstance(hit, Mapping):
            answer = hit.get("answer", "")
            case_id = hit.get("case_id")
            source_family = hit.get("source_family")
        else:
            answer = getattr(hit, "answer", "")
            case_id = getattr(hit, "case_id", None)
            source_family = getattr(hit, "source_family", None)
        if not isinstance(answer, str) or not answer.strip():
            return GatewayDecision("miss", "model")
        return GatewayDecision(
            "hit",
            self.bank_source,
            answer.strip(),
            _clip(case_id, 96) if case_id is not None else None,
            _clip(source_family, 96) if source_family is not None else None,
        )


@dataclass(frozen=True)
class RouteDecision:
    target: str
    answer_type: str
    complexity: str
    reason: str
    contract: ProblemContract
    lane: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "answer_type": self.answer_type,
            "complexity": self.complexity,
            "reason": self.reason,
            "lane": self.lane,
            "problem_contract": self.contract.as_dict(),
        }


class HostRouter:
    """Text-only router; metadata is accepted but never used as answer data."""

    def __init__(self, *, hybrid_enabled: bool = False, deep_enabled: bool = False) -> None:
        self.hybrid_enabled = bool(hybrid_enabled)
        self.deep_enabled = bool(deep_enabled)

    def contract(self, problem: str) -> ProblemContract:
        answer_shape, signal_count = _answer_shape_from_problem(problem)
        reasoning_risk = _reasoning_risk_from_problem(problem, answer_shape)
        if answer_shape == ANSWER_SHAPE_UNKNOWN or signal_count > 1 or _task_signal_count(problem) > 1:
            confidence = ROUTE_CONFIDENCE_LOW
        elif reasoning_risk == REASONING_RISK_STRUCTURED:
            confidence = ROUTE_CONFIDENCE_MEDIUM
        else:
            confidence = ROUTE_CONFIDENCE_HIGH
        return ProblemContract(answer_shape, reasoning_risk, confidence)

    def route(self, problem: str, metadata: Mapping[str, Any] | None = None) -> RouteDecision:
        del metadata
        text = problem if isinstance(problem, str) else ""
        contract = self.contract(text)
        answer_type = "mixed" if _task_signal_count(text) > 1 else _answer_type_from_problem(text)
        if contract.route_confidence == ROUTE_CONFIDENCE_LOW:
            target = "legacy_fsdf" if self.hybrid_enabled else "unsupported"
            return RouteDecision(target, answer_type, contract.reasoning_risk, "low_confidence_contract", contract, "legacy_fsdf" if self.hybrid_enabled else "unsupported")
        if contract.answer_shape == ANSWER_SHAPE_PROOF_TEXT:
            target = "legacy_fsdf" if self.hybrid_enabled else "unsupported"
            return RouteDecision(target, answer_type, contract.reasoning_risk, "proof_text_fallback", contract, "legacy_fsdf" if self.hybrid_enabled else "unsupported")
        if contract.reasoning_risk == REASONING_RISK_DIRECT and answer_type in {ANSWER_CHOICE, ANSWER_SCALAR}:
            return RouteDecision("harness", answer_type, "short", "scalar_or_exact_answer", contract, "direct")
        if self.deep_enabled:
            return RouteDecision("harness", answer_type, contract.reasoning_risk, "typed_deep_contract", contract, "deep")
        target = "legacy_fsdf" if self.hybrid_enabled else "unsupported"
        return RouteDecision(target, answer_type, contract.reasoning_risk, "deep_lane_disabled", contract, "legacy_fsdf" if self.hybrid_enabled else "unsupported")


class FrozenErrorNotebook:
    """Read-only notebook container for an offline, pre-frozen hint set."""

    def __init__(self, entries: Iterable[Mapping[str, Any]] = ()) -> None:
        self._entries = tuple(
            {
                "id": _clip(entry.get("id", ""), 96),
                "category": _clip(entry.get("category", ""), 96),
                "hint": _clip(entry.get("hint", ""), MAX_REASON_CHARS),
            }
            for entry in entries
        )

    def snapshot(self) -> tuple[dict[str, str], ...]:
        return tuple(dict(entry) for entry in self._entries)

    def hint(self, _problem: str) -> str:
        return ""

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("frozen_error_notebook_is_read_only")


class TypedMicroToolError(ValueError):
    pass


class TypedMicroToolProvider:
    """Small host-owned whitelist; disabled and unused by default."""

    ALLOWED_TOOLS = frozenset({"gcd", "prime_factors", "rational_add", "rational_compare"})

    def __init__(self, *, enabled: bool = False, max_abs_integer: int = 10**12) -> None:
        self.enabled = bool(enabled)
        self.max_abs_integer = max(1, int(max_abs_integer))

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 1.0,
    ) -> Any:
        if not self.enabled:
            raise TypedMicroToolError("tool_disabled")
        if tool not in self.ALLOWED_TOOLS:
            raise TypedMicroToolError("tool_not_allowed")
        if timeout_seconds <= 0:
            raise TypedMicroToolError("tool_timeout")
        args = dict(arguments or {})
        try:
            if tool == "gcd":
                left = _as_int(args.get("a"), minimum=-self.max_abs_integer, maximum=self.max_abs_integer)
                right = _as_int(args.get("b"), minimum=-self.max_abs_integer, maximum=self.max_abs_integer)
                return math.gcd(left, right)
            if tool == "prime_factors":
                value = _as_int(args.get("n"), minimum=1, maximum=self.max_abs_integer)
                factors: list[int] = []
                divisor = 2
                while divisor * divisor <= value:
                    while value % divisor == 0:
                        factors.append(divisor)
                        value //= divisor
                    divisor += 1 if divisor == 2 else 2
                if value > 1:
                    factors.append(value)
                return factors
            left = _parse_numeric(str(args.get("left", "")))
            right = _parse_numeric(str(args.get("right", "")))
            if left is None or right is None:
                raise TypedMicroToolError("invalid_rational")
            if tool == "rational_add":
                return _format_numeric(left + right)
            return "EQUIVALENT" if left == right else "NOT_EQUIVALENT"
        except TypedMicroToolError:
            raise
        except ValueError as exc:
            raise TypedMicroToolError(str(exc)) from exc

    run = call


class FSDFLegacyBackendAdapter:
    """Explicit adapter around the unchanged FSDF v1 backend."""

    def __init__(self, client: Any, backend_factory: Callable[[Any], Any] | None = None) -> None:
        self.client = client
        self.backend_factory = backend_factory

    def solve(self, problem: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        del metadata
        try:
            if self.backend_factory is None:
                from reasoning_agent.fork_select_deepen_finish import ForkSelectDeepenFinishRelay
                from user_agent import classify_problem_type

                backend = ForkSelectDeepenFinishRelay(self.client)
                result = backend.solve(problem, classify_problem_type(problem)).as_dict()
            else:
                backend = self.backend_factory(self.client)
                result = backend.solve(problem)
                if hasattr(result, "as_dict"):
                    result = result.as_dict()
        except BaseException as exc:
            return {
                "final_response": "UNKNOWN",
                "extracted_answer": "",
                "trace": [
                    {
                        "method": METHOD_ID,
                        "stage": "legacy_backend",
                        "backend": "fsdf_v1",
                        "status": "error",
                        "error_category": _error_category(exc),
                    }
                ],
            }
        if not isinstance(result, Mapping):
            return {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
        final = result.get("final_response", "")
        if not isinstance(final, str) or not final.strip():
            final = "UNKNOWN"
        extracted = result.get("extracted_answer", "")
        if not isinstance(extracted, str):
            extracted = ""
        return {
            "final_response": final,
            "extracted_answer": extracted,
            "trace": [
                {
                    "method": METHOD_ID,
                    "stage": "legacy_backend",
                    "backend": "fsdf_v1",
                    "status": "completed" if final != "UNKNOWN" else "unknown",
                    "source_trace_events": len(result.get("trace", []))
                    if isinstance(result.get("trace", []), list)
                    else 0,
                }
            ],
        }


class _CallResult:
    def __init__(
        self,
        content: str | None,
        *,
        error_category: str | None = None,
        finish_reason: str | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        self.content = content
        self.error_category = error_category
        self.finish_reason = finish_reason
        self.completion_tokens = completion_tokens


def _unpack_response(response: Any) -> tuple[str | None, int | None, str | None, str | None]:
    """Accept the public string contract plus a response envelope for tests."""
    if isinstance(response, str):
        return response, None, None, None
    if isinstance(response, Mapping):
        content = response.get("content")
        if content is None and isinstance(response.get("message"), Mapping):
            content = response["message"].get("content")
        usage = response.get("usage")
        completion = usage.get("completion_tokens") if isinstance(usage, Mapping) else response.get("completion_tokens")
        if isinstance(completion, bool):
            completion = None
        try:
            completion = int(completion) if completion is not None else None
        except (TypeError, ValueError):
            completion = None
        finish = response.get("finish_reason")
        return (
            content if isinstance(content, str) else None,
            completion,
            str(finish) if finish is not None else None,
            None,
        )
    return None, None, None, "invalid_response"


class AttemptScheduler:
    """Thin host scheduler used by the orchestrator and code acceptance tests."""

    def __init__(self, harness: "ConstraintFitOrchestrator") -> None:
        self.harness = harness

    def call(self, stage: str, system_prompt: str, user_prompt: str, max_tokens: int) -> _CallResult:
        return self.harness._call(stage, system_prompt, user_prompt, max_tokens)


ATTEMPT_A_PROMPT = """你是数学推理求解器。独立解决题目，先完成必要计算，再给出唯一结论。
不要输出 Thinking Process、计划或多个候选；不要求特殊标记。答案可以放在自然的结论行，
并保持推导足够简洁，避免在完成结论后继续展开。"""
ATTEMPT_B_PROMPT = """你是独立的数学复核求解器。不要参考任何先前回答；从原题重新计算，检查定义域、
边界和算术。只给一个最可信的结论及最少量理由，不要求 CANDIDATE 或其它固定 marker。"""
CONTINUATION_PROMPT = """你是数学解答续写器。此前解答已形成一个明确候选，但正文可能在 token 上限处结束。
只核对该候选并用最短文本完成结论；若候选不可靠，明确给出你重新核对后的唯一结果。
不要输出多个答案。"""
CRITIC_PROMPT = """你是保守的数学冲突裁决器。题目与候选均由宿主提供。
只能选择已有候选，或明确指出某候选存在可修复错误；不能凭空创造第三个答案。
输出一行：SELECT: A、SELECT: B、REPAIR: A、REPAIR: B 或 UNKNOWN。
若选择 REPAIR，下一句必须给出简短、具体的错误摘要。"""
REPAIR_PROMPT = """你是数学修正器。根据题目、指定候选和宿主给出的明确错误摘要重新核对。
只输出一个修正后的唯一答案及必要的最短依据，不要输出多个候选或 Thinking Process。"""

DEEP_PRIMARY_PROMPT = """你是深度数学求解器。先完整解决题目并检查关键条件，再给出符合指定答案形状的唯一终答。
不要只给一个未经推导的猜测；不要输出多个互相冲突的答案。最后单独一行写 Final answer: <完整答案>。"""
DEEP_REVIEW_PROMPT = """你是独立的数学复核求解器。不要参考任何先前解答，从原题重新推导并检查边界、定义域和答案形状。
最后单独一行写 Final answer: <完整答案>；如果不能形成完整答案，明确说明无法完成。"""
DEEP_CONTINUATION_PROMPT = """你是数学解答续写器。宿主已发现一个候选，但原解答可能被截断。
只核对候选与题目条件，并用最短完整推导确认或否定它。最后单独一行写 Final answer: <完整答案>。"""


class ConstraintFitOrchestrator:
    """Outer Constraint-Fit Math Harness with a bounded evidence trajectory."""

    def __init__(
        self,
        client: Any,
        *,
        config: HarnessConfig | None = None,
        bank_lookup: Callable[[str], Any] | None = None,
        legacy_backend: Any | None = None,
        clock: Callable[[], float] | None = None,
        router: HostRouter | None = None,
        notebook: FrozenErrorNotebook | None = None,
    ) -> None:
        self.client = client
        self.config = config or HarnessConfig()
        self.clock = clock or time.monotonic
        self.gateway = SubmissionGateway(self.config.bank_mode, bank_lookup)
        self.router = router or HostRouter(
            hybrid_enabled=legacy_backend is not None,
            deep_enabled=self.config.enable_deep_lane,
        )
        self.legacy_backend = legacy_backend
        self.notebook = notebook or FrozenErrorNotebook()
        self.scheduler = AttemptScheduler(self)
        self.ledger: EvidenceLedger | None = None
        self.budget: BudgetLedger | None = None
        self._solve_started = 0.0
        self._next_candidate_number = 1

    def solve(self, problem: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        problem_text = problem if isinstance(problem, str) else ""
        self.ledger = EvidenceLedger()
        self.budget = BudgetLedger(
            max_calls=self.config.effective_call_limit,
            total_tokens=self.config.token_limit,
            clock=self.clock,
        )
        self._solve_started = self.clock()
        self._next_candidate_number = 1
        self.ledger.transition(STATE_START)

        gateway = self.gateway.resolve(problem_text)
        gateway_trace: dict[str, Any] = {
            "method": METHOD_ID,
            "stage": "submission_gateway",
            "bank_mode": self.gateway.bank_mode,
            "status": gateway.status,
            "source": gateway.source,
        }
        if gateway.case_id is not None:
            gateway_trace["case_id"] = gateway.case_id
        if gateway.source_family is not None:
            gateway_trace["source_family"] = gateway.source_family

        route = self.router.route(problem_text[: self.config.max_problem_chars], metadata or {})
        route_dict = route.as_dict()
        trace_method_id = DEEP_METHOD_ID if route.lane == "deep" else METHOD_ID
        gateway_trace["method"] = trace_method_id
        self.ledger.transition("route", reason=route.reason)
        prefix_trace = [gateway_trace, {"method": trace_method_id, "stage": "route", **route_dict}]

        if gateway.status == "hit":
            self.ledger.transition(STATE_SELECTED, reason="answer_bank_hit")
            self.ledger.transition(STATE_FINALIZED)
            return {
                "final_response": gateway.answer,
                "extracted_answer": normalize_value(gateway.answer),
                "trace": prefix_trace
                + [
                    self.ledger.trace(self.budget, route=route_dict),
                    {
                        "method": trace_method_id,
                        "stage": "finalize",
                        "status": "selected",
                        "source": gateway.source,
                        "model_calls": 0,
                    },
                ],
            }

        if route.target == "legacy_fsdf":
            if self.legacy_backend is None:
                return self._abstain(prefix_trace, route_dict, "legacy_backend_unavailable")
            self.ledger.transition(STATE_FINALIZED, reason="legacy_backend")
            result = self.legacy_backend.solve(problem_text, metadata or {})
            if not isinstance(result, Mapping):
                result = {}
            final = result.get("final_response", "UNKNOWN")
            if not isinstance(final, str) or not final.strip():
                final = "UNKNOWN"
            extracted = result.get("extracted_answer", "")
            if not isinstance(extracted, str):
                extracted = ""
            return {
                "final_response": final,
                "extracted_answer": extracted,
                "trace": prefix_trace
                + [
                    self.ledger.trace(self.budget, route=route_dict),
                    {
                        "method": METHOD_ID,
                        "stage": "finalize",
                        "status": "legacy_backend",
                        "model_calls": 0,
                    },
                ],
            }
        if route.target != "harness":
            return self._abstain(prefix_trace, route_dict, "unsupported_route")
        if route.lane == "deep":
            return self._solve_deep(problem_text[: self.config.max_problem_chars], route, prefix_trace)
        if route.lane != "direct":
            return self._abstain(prefix_trace, route_dict, "unsupported_lane")

        return self._solve_harness(problem_text[: self.config.max_problem_chars], route, prefix_trace)

    def _call(self, stage: str, system_prompt: str, user_prompt: str, max_tokens: int) -> _CallResult:
        assert self.ledger is not None and self.budget is not None
        if self._deadline_exceeded():
            record = {
                "stage": stage,
                "status": "skipped",
                "reason": "wall_clock_limit",
                "requested_tokens": 0,
            }
            self.ledger.add_call(record)
            return _CallResult(None, error_category="timeout")
        reservation = self.budget.reserve(stage, max_tokens)
        if reservation is None:
            record = {
                "stage": stage,
                "status": "skipped",
                "reason": "budget_exhausted",
                "requested_tokens": max_tokens,
            }
            self.ledger.add_call(record)
            return _CallResult(None, error_category="budget_exhausted")
        started = self.clock()
        try:
            raw = self.client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                self.config.temperature,
                reservation.requested_tokens,
            )
            content, completion_tokens, finish_reason, unpack_error = _unpack_response(raw)
            error_category = unpack_error or (None if content is not None else "invalid_response")
        except BaseException as exc:
            content, completion_tokens, finish_reason = None, None, None
            error_category = _error_category(exc)
        duration_ms = int(max(0.0, (self.clock() - started) * 1000.0))
        if error_category is None and self._deadline_exceeded():
            # A response that arrives after the per-question deadline is not
            # safe to use, even if the client returned a plausible answer.
            content = None
            error_category = "timeout"
        self.budget.finish(
            reservation,
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
            error_category=error_category,
            duration_ms=duration_ms,
        )
        record = {
            "stage": stage,
            "status": "error" if error_category else "ok",
            "call_number": reservation.call_number,
            "requested_tokens": reservation.requested_tokens,
            "completion_tokens": completion_tokens,
            "finish_reason": finish_reason,
            "duration_ms": duration_ms,
            "error_category": error_category,
        }
        self.ledger.add_call(record)
        return _CallResult(
            content,
            error_category=error_category,
            finish_reason=finish_reason,
            completion_tokens=completion_tokens,
        )

    def _deadline_exceeded(self) -> bool:
        return self.clock() - self._solve_started >= min(MAX_WALL_SECONDS, float(self.config.max_wall_seconds))

    def _new_candidates(self, parsed: ParsedResponse, source: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        for candidate in parsed.candidates:
            candidate.candidate_id = f"{source}_{self._next_candidate_number}"
            candidate.source = source
            self._next_candidate_number += 1
            candidates.append(candidate)
        return candidates

    def _record_parsed(self, state: str, parsed: ParsedResponse, candidates: list[Candidate]) -> None:
        assert self.ledger is not None
        self.ledger.transition(state, reason=parsed.reason_summary)
        self.ledger.add_candidates(candidates)
        if parsed.status == CANDIDATE_CONFLICT:
            self.ledger.add_conflict(candidates)

    def _adopt_typed_candidate(self, parsed: TypedParseResult, source: str) -> list[Candidate]:
        candidate = parsed.candidate
        if candidate is None:
            return []
        candidate.candidate_id = f"{source}_{self._next_candidate_number}"
        candidate.source = source
        self._next_candidate_number += 1
        return [candidate]

    def _record_typed(self, state: str, parsed: TypedParseResult, candidates: list[Candidate]) -> None:
        assert self.ledger is not None
        self.ledger.transition(state, reason=parsed.reason)
        self.ledger.add_candidates(candidates)
        self.ledger.add_typed_parse(state, parsed, candidates)

    def _solve_deep(self, problem: str, route: RouteDecision, prefix_trace: list[dict[str, Any]]) -> dict[str, Any]:
        assert self.ledger is not None and self.budget is not None
        parser = TypedParser()
        contract = route.contract
        all_candidates: list[Candidate] = []

        self.ledger.transition(STATE_DEEP_PRIMARY)
        primary = self.scheduler.call(
            "deep_primary",
            DEEP_PRIMARY_PROMPT,
            f"题目：\n{problem}\n\n答案形状：{contract.answer_shape}\n请完整作答。",
            self.config.tokens_for("deep_primary"),
        )
        parsed_primary = parser.parse(primary.content, contract, finish_reason=primary.finish_reason)
        primary_candidates = self._adopt_typed_candidate(parsed_primary, "deep_primary")
        all_candidates.extend(primary_candidates)
        self._record_typed(STATE_CANDIDATE_A, parsed_primary, primary_candidates)

        second_is_continuation = bool(
            parsed_primary.status == "typed_incomplete" and primary_candidates
        )
        second_stage = "deep_continuation" if second_is_continuation else "deep_review"
        self.ledger.transition(
            STATE_DEEP_CONTINUATION if second_is_continuation else STATE_DEEP_REVIEW,
            reason="typed_primary_incomplete" if second_is_continuation else "deep_requires_independent_evidence",
        )
        if second_is_continuation:
            second = self.scheduler.call(
                second_stage,
                DEEP_CONTINUATION_PROMPT,
                f"题目：\n{problem}\n\n已有候选：{_clip(primary_candidates[0].value, MAX_CANDIDATE_CHARS)}\n请完成核对。",
                self.config.tokens_for("deep_continuation"),
            )
        else:
            second = self.scheduler.call(
                second_stage,
                DEEP_REVIEW_PROMPT,
                f"题目：\n{problem}\n\n答案形状：{contract.answer_shape}\n请从头独立复核。",
                self.config.tokens_for("deep_review"),
            )
        parsed_second = parser.parse(second.content, contract, finish_reason=second.finish_reason)
        second_candidates = self._adopt_typed_candidate(parsed_second, second_stage)
        all_candidates.extend(second_candidates)
        self._record_typed("candidate_continuation" if second_is_continuation else "candidate_review", parsed_second, second_candidates)

        if (
            second_is_continuation
            and primary_candidates
            and second_candidates
            and parsed_second.typed_complete
            and value_equivalence(primary_candidates[0].value, second_candidates[0].value) == "EQUIVALENT"
        ):
            primary_candidates[0].verification_status = "verified"
            primary_candidates[0].extraction_status = CANDIDATE_VERIFIED
            second_candidates[0].verification_status = "verified"
            second_candidates[0].extraction_status = CANDIDATE_VERIFIED
            self.ledger.update_candidate(primary_candidates[0])
            self.ledger.update_candidate(second_candidates[0])
            return self._select(
                prefix_trace,
                route.as_dict(),
                second_candidates[0],
                all_candidates,
                "deep_continuation_agreement",
            )

        complete_candidates = [
            candidate
            for candidate, parsed in (
                [(primary_candidates[0], parsed_primary)] if primary_candidates else []
            )
            + (
                [(second_candidates[0], parsed_second)] if second_candidates else []
            )
            if parsed.typed_complete
        ]
        if len(complete_candidates) >= 2:
            relation = value_equivalence(complete_candidates[0].value, complete_candidates[1].value)
            if relation == "EQUIVALENT":
                for candidate in complete_candidates:
                    candidate.verification_status = "verified"
                    candidate.extraction_status = CANDIDATE_VERIFIED
                    self.ledger.update_candidate(candidate)
                return self._select(
                    prefix_trace,
                    route.as_dict(),
                    complete_candidates[0],
                    all_candidates,
                    "deep_continuation_agreement" if second_is_continuation else "independent_agreement",
                )
            self.ledger.transition(STATE_CONFLICT, reason="deep_typed_conflict")
            self.ledger.add_conflict(complete_candidates)
            self.ledger.transition(STATE_DEEP_CRITIC, reason="deep_conflict")
            critic = self.scheduler.call(
                "deep_critic",
                CRITIC_PROMPT,
                self._critic_prompt(problem, complete_candidates),
                self.config.tokens_for("deep_critic"),
            )
            decision, target, reason = self._parse_critic(critic.content, complete_candidates)
            if decision == "select" and target is not None:
                target.verification_status = "verified"
                target.extraction_status = CANDIDATE_VERIFIED
                self.ledger.update_candidate(target)
                return self._select(prefix_trace, route.as_dict(), target, all_candidates, "deep_critic_selected")
            return self._abstain(prefix_trace, route.as_dict(), "deep_critic_unresolved_conflict")

        # A single deep candidate is never promoted by candidate_unproven.
        return self._abstain(prefix_trace, route.as_dict(), "deep_typed_evidence_incomplete")

    def _solve_harness(self, problem: str, route: RouteDecision, prefix_trace: list[dict[str, Any]]) -> dict[str, Any]:
        assert self.ledger is not None and self.budget is not None
        all_candidates: list[Candidate] = []
        self.ledger.transition(STATE_ATTEMPT_A)
        first = self.scheduler.call(
            "attempt_a",
            ATTEMPT_A_PROMPT,
            f"题目：\n{problem}\n\n请独立完成求解并给出唯一结论。",
            self.config.tokens_for("attempt_a"),
        )
        parsed_a = HostParser().parse(
            first.content,
            problem=problem,
            source="attempt_a",
            finish_reason=first.finish_reason,
        )
        candidates_a = self._new_candidates(parsed_a, "attempt_a")
        all_candidates.extend(candidates_a)
        self._record_parsed(STATE_CANDIDATE_A, parsed_a, candidates_a)

        if self.config.early_stop and len(candidates_a) == 1 and parsed_a.status == CANDIDATE_PARSED:
            candidates_a[0].verification_status = "unverified"
            return self._select(
                prefix_trace,
                route.as_dict(),
                candidates_a[0],
                all_candidates,
                "candidate_unproven",
            )

        if len(candidates_a) == 1 and parsed_a.status == CANDIDATE_TRUNCATED:
            self.ledger.transition(STATE_CONTINUATION, reason="truncated_candidate_recovery")
            continuation = self.scheduler.call(
                "continuation",
                CONTINUATION_PROMPT,
                f"题目：\n{problem}\n\n已有候选：{candidates_a[0].value}\n请完成一次最短核对。",
                self.config.tokens_for("continuation"),
            )
            parsed_cont = HostParser().parse(
                continuation.content,
                problem=problem,
                source="continuation",
                finish_reason=continuation.finish_reason,
            )
            cont_candidates = self._new_candidates(parsed_cont, "continuation")
            all_candidates.extend(cont_candidates)
            self._record_parsed("candidate_continuation", parsed_cont, cont_candidates)
            if cont_candidates and value_equivalence(candidates_a[0].value, cont_candidates[0].value) == "EQUIVALENT":
                return self._select(
                    prefix_trace,
                    route.as_dict(),
                    candidates_a[0],
                    all_candidates,
                    "continuation_agreement",
                )
            if not cont_candidates and not _has_conflict(candidates_a):
                return self._select(
                    prefix_trace,
                    route.as_dict(),
                    candidates_a[0],
                    all_candidates,
                    "truncated_candidate_fallback",
                )

        self.ledger.transition(STATE_ATTEMPT_B, reason="first_attempt_missing_conflicting_or_untrusted")
        second = self.scheduler.call(
            "attempt_b",
            ATTEMPT_B_PROMPT,
            f"题目：\n{problem}\n\n请从头独立复核并给出唯一结论。",
            self.config.tokens_for("attempt_b"),
        )
        parsed_b = HostParser().parse(
            second.content,
            problem=problem,
            source="attempt_b",
            finish_reason=second.finish_reason,
        )
        candidates_b = self._new_candidates(parsed_b, "attempt_b")
        all_candidates.extend(candidates_b)
        self._record_parsed(STATE_CANDIDATE_B, parsed_b, candidates_b)

        unique = _unique_candidates(all_candidates)
        if len(unique) == 1:
            candidate = unique[0]
            independent_count = sum(
                1
                for item in all_candidates
                if value_equivalence(item.value, candidate.value) == "EQUIVALENT"
            )
            reason = "independent_agreement" if independent_count >= 2 else "single_survivor_unverified"
            if independent_count >= 2:
                for item in all_candidates:
                    if value_equivalence(item.value, candidate.value) == "EQUIVALENT":
                        item.extraction_status = CANDIDATE_VERIFIED
                        item.verification_status = "verified"
                        self.ledger.update_candidate(item)
            return self._select(
                prefix_trace,
                route.as_dict(),
                candidate,
                all_candidates,
                reason,
            )
        if not unique:
            return self._abstain(prefix_trace, route.as_dict(), "no_extractable_candidate")

        self.ledger.transition(STATE_CONFLICT, reason="conflicting_candidates_retained")
        self.ledger.add_conflict(unique)
        self.ledger.transition(STATE_CRITIC, reason="genuine_conflict")
        critic = self.scheduler.call(
            "critic",
            CRITIC_PROMPT,
            self._critic_prompt(problem, unique),
            self.config.tokens_for("critic"),
        )
        critic_decision, critic_target, critic_reason = self._parse_critic(critic.content, unique)
        if critic_decision == "select" and critic_target is not None:
            return self._select(
                prefix_trace,
                route.as_dict(),
                critic_target,
                all_candidates,
                "critic_selected",
            )
        if critic_decision == "repair" and critic_target is not None and critic_reason:
            self.ledger.transition(STATE_REPAIR, reason="critic_explicitly_diagnosed_error")
            repair = self.scheduler.call(
                "repair",
                REPAIR_PROMPT,
                self._repair_prompt(problem, critic_target, critic_reason),
                self.config.tokens_for("repair"),
            )
            parsed_repair = HostParser().parse(
                repair.content,
                problem=problem,
                source="repair",
                finish_reason=repair.finish_reason,
            )
            repaired = self._new_candidates(parsed_repair, "repair")
            all_candidates.extend(repaired)
            self._record_parsed("candidate_repair", parsed_repair, repaired)
            if len(repaired) == 1:
                # The critic diagnosed the old candidate; it did not verify
                # the newly generated repair.  Keep candidate formation and
                # verification as separate ledger states.
                repaired[0].verification_status = "unverified"
                self.ledger.update_candidate(repaired[0])
                return self._select(
                    prefix_trace,
                    route.as_dict(),
                    repaired[0],
                    all_candidates,
                    "critic_repair",
                )
        return self._abstain(prefix_trace, route.as_dict(), "critic_unresolved_conflict")

    def _critic_prompt(self, problem: str, candidates: list[Candidate]) -> str:
        rows = "\n".join(
            f"候选 {chr(65 + index)}：{_clip(candidate.value, MAX_CANDIDATE_CHARS)}"
            for index, candidate in enumerate(candidates[:5])
        )
        return f"题目：\n{problem}\n\n候选账本：\n{rows}\n\n请按规定输出裁决。"

    def _repair_prompt(self, problem: str, candidate: Candidate, reason: str) -> str:
        return (
            f"题目：\n{problem}\n\n指定候选：{_clip(candidate.value, MAX_CANDIDATE_CHARS)}\n"
            f"明确错误摘要：{_clip(reason or 'critic_diagnosed_error', MAX_REASON_CHARS)}\n\n请修正并只给一个答案。"
        )

    @staticmethod
    def _parse_critic(response: str | None, candidates: list[Candidate]) -> tuple[str, Candidate | None, str]:
        text = response if isinstance(response, str) else ""
        repair = re.search(r"(?im)^\s*REPAIR\s*[:：]\s*([A-E])\b", text)
        select = re.search(r"(?im)^\s*SELECT\s*[:：]\s*([A-E])\b", text)
        match = repair or select
        if match:
            index = ord(match.group(1).upper()) - ord("A")
            if 0 <= index < len(candidates):
                decision = "repair" if repair else "select"
                if decision == "select":
                    return decision, candidates[index], ""
                lines = text[match.end() :].splitlines()
                reason = next((line.strip() for line in lines if line.strip()), "")
                if reason:
                    return decision, candidates[index], _clip(reason, MAX_REASON_CHARS)
        return "unknown", None, ""

    def _select(
        self,
        prefix_trace: list[dict[str, Any]],
        route: Mapping[str, Any],
        candidate: Candidate,
        all_candidates: list[Candidate],
        source: str,
    ) -> dict[str, Any]:
        assert self.ledger is not None and self.budget is not None
        self.ledger.transition(STATE_SELECTED, reason=source)
        self.ledger.update_candidate(candidate)
        self.ledger.transition(STATE_FINALIZED)
        final = _strip_math_wrappers(candidate.value) or "UNKNOWN"
        return {
            "final_response": final,
            "extracted_answer": candidate.normalized_value if final != "UNKNOWN" else "",
            "trace": prefix_trace
                + [
                    self.ledger.trace(self.budget, route=route),
                    {
                        "method": DEEP_METHOD_ID if route.get("lane") == "deep" else METHOD_ID,
                    "stage": "finalize",
                    "status": "selected" if final != "UNKNOWN" else "abstained",
                    "source": source,
                    "candidate_id": candidate.candidate_id,
                    "candidate_values": [
                        _clip(item.normalized_value, MAX_CANDIDATE_CHARS)
                        for item in all_candidates[:5]
                    ],
                    "proof_status": candidate.proof_status,
                    "verification_status": candidate.verification_status,
                    "model_calls": self.budget.calls_used,
                },
            ],
        }

    def _abstain(
        self,
        prefix_trace: list[dict[str, Any]],
        route: Mapping[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        assert self.ledger is not None and self.budget is not None
        self.ledger.transition(STATE_ABSTAINED, reason=reason)
        self.ledger.open_questions.append(_clip(reason, MAX_REASON_CHARS))
        self.ledger.transition(STATE_FINALIZED)
        return {
            "final_response": "UNKNOWN",
            "extracted_answer": "",
            "trace": prefix_trace
                + [
                    self.ledger.trace(self.budget, route=route),
                    {
                        "method": DEEP_METHOD_ID if route.get("lane") == "deep" else METHOD_ID,
                    "stage": "finalize",
                    "status": "abstained",
                    "source": reason,
                    "model_calls": self.budget.calls_used,
                },
            ],
        }


class ConservativeSelector:
    """Select one unique candidate only; unresolved conflicts abstain."""

    @staticmethod
    def select(candidates: Iterable[Candidate]) -> Candidate | None:
        unique = _unique_candidates(candidates)
        return unique[0] if len(unique) == 1 else None


ConstraintFitMathHarness = ConstraintFitOrchestrator
normalize_answer = normalize_value
answer_equivalence = value_equivalence


__all__ = [
    "HARNESS_VERSION",
    "METHOD_ID",
    "DEEP_METHOD_ID",
    "HarnessConfig",
    "ProblemContract",
    "RouteDecision",
    "ANSWER_SHAPE_SINGLE_NUMERIC",
    "ANSWER_SHAPE_PARAMETERIZED_EXPRESSION",
    "ANSWER_SHAPE_FINITE_SET",
    "ANSWER_SHAPE_INTERVAL_OR_RANGE",
    "ANSWER_SHAPE_FUNCTION_FAMILY",
    "ANSWER_SHAPE_PROOF_TEXT",
    "ANSWER_SHAPE_UNKNOWN",
    "REASONING_RISK_DIRECT",
    "REASONING_RISK_STRUCTURED",
    "REASONING_RISK_DEEP",
    "ROUTE_CONFIDENCE_HIGH",
    "ROUTE_CONFIDENCE_MEDIUM",
    "ROUTE_CONFIDENCE_LOW",
    "BudgetLedger",
    "EvidenceLedger",
    "SubmissionGateway",
    "HostParser",
    "TypedParser",
    "TypedParseResult",
    "HostRouter",
    "AttemptScheduler",
    "FrozenErrorNotebook",
    "TypedMicroToolError",
    "TypedMicroToolProvider",
    "FSDFLegacyBackendAdapter",
    "ConstraintFitOrchestrator",
    "ConstraintFitMathHarness",
    "ConservativeSelector",
    "Candidate",
    "ParsedResponse",
    "normalize_value",
    "value_equivalence",
    "normalize_answer",
    "answer_equivalence",
]
