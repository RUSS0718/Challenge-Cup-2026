"""Bounded, deterministic intake for the experimental Host Loop.

The public runner may provide arbitrary metadata, but metadata is not an
answer source.  This module keeps only a small allow-list of scalar fields and
derives coarse complexity *signals* from the problem text.  It deliberately
does not choose a solver, read a reference answer, or make a model call.

The module is a preparation seam for future routing.  ``user_agent`` may
import the opt-in bridge, but Host Loop context is only constructed when
``enable_host_intake`` or ``enable_bounded_obligation_extractor`` is on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re
import unicodedata
from typing import Any, Mapping


MAX_PROBLEM_CHARS = 12_000
MAX_METADATA_FIELDS = 16
MAX_METADATA_VALUE_CHARS = 256
MAX_ANSWER_TYPE_CHARS = 64

# These are descriptive runner fields only.  None of them is used as a
# question-specific answer lookup or routing key by this module.
ALLOWED_METADATA_KEYS = frozenset(
    {
        "idx",
        "question_id",
        "task_id",
        "split",
        "language",
        "difficulty",
        "source",
        "domain",
        "category",
    }
)
_SENSITIVE_METADATA_KEYS = frozenset(
    {
        "answer",
        "answers",
        "gold",
        "gold_answer",
        "reference_answer",
        "solution",
        "reference_solution",
        "judger",
        "hidden_answer",
    }
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_PROOF_RE = re.compile(r"(?:证明|求证|推导|证明题|prove|show\s+that|derive)", re.I)
_UNIVERSAL_RE = re.compile(r"(?:任意|所有|全部|每个|任何|∀|for\s+all|for\s+every)", re.I)
_PART_RE = re.compile(r"(?:^|\n)\s*(?:\d+\s*[.)、]|[一二三四五六七八九十]+\s*[、.)])")
_EQUATION_RE = re.compile(r"(?<![<>=!])=(?!=)|[≤≥≠]")
_VARIABLE_RE = re.compile(r"(?<![A-Za-z])[A-Za-z](?:_[A-Za-z0-9]+|[A-Za-z0-9]*)?")


@dataclass(frozen=True)
class ComplexitySignals:
    """Coarse text-only signals; they are hints, not a semantic classifier."""

    char_count: int
    line_count: int
    equation_count: int
    variable_count: int
    has_proof_language: bool
    has_universal_language: bool
    has_multiple_parts: bool
    profile: str


@dataclass(frozen=True)
class HostIntake:
    """A bounded, serialisable intake record for one question."""

    problem: str
    problem_hash: str
    answer_type: str
    metadata: dict[str, str | int | float | bool]
    metadata_rejections: tuple[str, ...]
    complexity: ComplexitySignals

    def as_dict(self) -> dict[str, Any]:
        return {
            "problem": self.problem,
            "problem_hash": self.problem_hash,
            "answer_type": self.answer_type,
            "metadata": dict(self.metadata),
            "metadata_rejections": list(self.metadata_rejections),
            "complexity": asdict(self.complexity),
        }


def normalize_problem(problem: str, *, max_chars: int = MAX_PROBLEM_CHARS) -> str:
    """Normalize line endings/control noise without changing mathematical text.

    Overlong or empty input is rejected instead of clipped: clipping a problem
    can silently remove a constraint and create a false answer.
    """

    if not isinstance(problem, str):
        raise ValueError("problem_type")
    text = unicodedata.normalize("NFC", problem)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    lines = [line.rstrip() for line in text.split("\n")]
    normalized = "\n".join(lines).strip()
    if not normalized:
        raise ValueError("problem_empty")
    if len(normalized) > max(1, int(max_chars)):
        raise ValueError("problem_too_long")
    return normalized


def _safe_metadata_key(value: Any) -> str:
    key = str(value or "").strip().casefold()
    return key if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) else "invalid_key"


def sanitize_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    max_fields: int = MAX_METADATA_FIELDS,
    max_value_chars: int = MAX_METADATA_VALUE_CHARS,
) -> tuple[dict[str, str | int | float | bool], tuple[str, ...]]:
    """Return allow-listed scalar metadata and bounded rejection reasons.

    The rejection tuple contains reason codes only (never rejected values or
    arbitrary key names), which keeps diagnostics safe to serialize.
    """

    if metadata is None:
        return {}, ()
    if not isinstance(metadata, Mapping):
        return {}, ("metadata_type",)
    accepted: dict[str, str | int | float | bool] = {}
    reasons: list[str] = []
    for raw_key, raw_value in list(metadata.items())[: max(0, int(max_fields))]:
        key = _safe_metadata_key(raw_key)
        if key == "invalid_key":
            reasons.append("invalid_key")
            continue
        if key in _SENSITIVE_METADATA_KEYS:
            reasons.append("sensitive_key")
            continue
        if key not in ALLOWED_METADATA_KEYS:
            reasons.append("not_allowlisted")
            continue
        if isinstance(raw_value, bool):
            accepted[key] = raw_value
            continue
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            accepted[key] = raw_value
            continue
        if isinstance(raw_value, float):
            if math.isfinite(raw_value):
                accepted[key] = raw_value
            else:
                reasons.append("non_finite")
            continue
        if isinstance(raw_value, str):
            value = _CONTROL_RE.sub("", raw_value).strip()
            if len(value) > max(1, int(max_value_chars)):
                reasons.append("value_too_long")
            else:
                accepted[key] = value
            continue
        reasons.append("non_scalar")
    if len(metadata) > max(0, int(max_fields)):
        reasons.append("field_limit")
    return accepted, tuple(dict.fromkeys(reasons))


def estimate_complexity(problem: str) -> ComplexitySignals:
    """Derive bounded, text-only complexity hints for a future planner."""

    text = normalize_problem(problem)
    variables = {
        match.group(0).casefold()
        for match in _VARIABLE_RE.finditer(text)
        if match.group(0).casefold() not in {"sin", "cos", "tan", "mod"}
    }
    equation_count = len(_EQUATION_RE.findall(text))
    line_count = text.count("\n") + 1
    has_multiple_parts = bool(_PART_RE.search(text) or re.search(r"第\s*[一二三四五六七八九十0-9]+\s*[问题]", text))
    has_proof = bool(_PROOF_RE.search(text))
    has_universal = bool(_UNIVERSAL_RE.search(text))
    if len(text) > 2_000 or line_count > 24:
        profile = "long"
    elif has_multiple_parts or equation_count >= 2 or has_proof or has_universal:
        profile = "structured"
    else:
        profile = "short"
    return ComplexitySignals(
        char_count=len(text),
        line_count=line_count,
        equation_count=equation_count,
        variable_count=min(len(variables), 64),
        has_proof_language=has_proof,
        has_universal_language=has_universal,
        has_multiple_parts=has_multiple_parts,
        profile=profile,
    )


def build_host_intake(
    problem: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    answer_type: str = "",
) -> HostIntake:
    """Build a bounded intake record without selecting a solving strategy."""

    normalized = normalize_problem(problem)
    clean_metadata, rejections = sanitize_metadata(metadata)
    answer_text = str(answer_type or "").strip()
    if len(answer_text) > MAX_ANSWER_TYPE_CHARS:
        raise ValueError("answer_type_too_long")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return HostIntake(
        problem=normalized,
        problem_hash=digest,
        answer_type=answer_text,
        metadata=clean_metadata,
        metadata_rejections=rejections,
        complexity=estimate_complexity(normalized),
    )


__all__ = [
    "ALLOWED_METADATA_KEYS",
    "ComplexitySignals",
    "HostIntake",
    "build_host_intake",
    "estimate_complexity",
    "normalize_problem",
    "sanitize_metadata",
]
