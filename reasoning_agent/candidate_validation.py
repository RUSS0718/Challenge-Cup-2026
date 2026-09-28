"""Bounded structural checks for answer candidates.

This module owns shape validation only.  It deliberately does not decide
whether a mathematically well-formed expression is correct.
"""

from __future__ import annotations

import re
from typing import Any

from reasoning_agent.harness_contracts import (
    ANSWER_CHOICE,
    ANSWER_EXACT_EXPRESSION,
    ANSWER_EXPLANATION,
    ANSWER_INTEGER,
    ANSWER_PROOF,
    ANSWER_RATIONAL,
    ANSWER_SET,
    ANSWER_UNKNOWN,
    Candidate,
    _canonical_set,
    _is_placeholder,
    _parse_numeric,
    _strip_math_wrappers,
)


INTEGER_RE = re.compile(r"^[+-]?\d+$")
CHOICE_RE = re.compile(r"^[A-Da-d](?:[.)）])?$")


def _expression_shape_is_valid(value: str) -> bool:
    """Accept bounded mathematical notation while rejecting prose fragments."""
    if value.endswith((":", "：")):
        return False
    if re.search(r"[，。；;？！]", value):
        return False
    if re.fullmatch(r"(?i)(?:the answer is|answer|the area is|答案|结果是)", value):
        return False
    if re.search(r"[\u4e00-\u9fff]", value) and not re.search(
        r"[0-9=+\-*/^()[\]{}<>≤≥\\]", value
    ):
        return False
    return bool(re.search(r"\d|[A-Za-z]|\\", value))


def validate_candidate_shape(candidate: Candidate | Any, answer_type: str) -> tuple[bool, str]:
    """Validate a candidate's syntax without evaluating its mathematical truth.

    ``answer_type`` is the expected host type.  For the generic scalar type,
    the parser's more specific candidate type is used when available.
    Returns a stable reason suitable for the solve ledger.
    """
    value = _strip_math_wrappers(getattr(candidate, "value", ""))
    if not value:
        return False, "empty"
    if _is_placeholder(value):
        return False, "placeholder"

    candidate_type = getattr(candidate, "answer_type", ANSWER_UNKNOWN)
    expected = candidate_type if answer_type == "scalar" and candidate_type != "scalar" else answer_type
    if expected == ANSWER_INTEGER:
        return (True, "valid") if INTEGER_RE.fullmatch(value) else (False, "integer_shape")
    if expected == ANSWER_RATIONAL:
        return (True, "valid") if _parse_numeric(value) is not None else (False, "rational_shape")
    if expected == ANSWER_CHOICE:
        return (True, "valid") if CHOICE_RE.fullmatch(value) else (False, "choice_shape")
    if expected == ANSWER_SET:
        return (True, "valid") if _canonical_set(value) is not None else (False, "set_shape")
    if expected in {ANSWER_EXACT_EXPRESSION, ANSWER_UNKNOWN, "scalar"}:
        return (True, "valid") if _expression_shape_is_valid(value) else (False, "expression_prose")
    if expected in {ANSWER_PROOF, ANSWER_EXPLANATION}:
        return (True, "valid") if not value.endswith((":", "：")) else (False, "incomplete_structured_answer")
    return False, "unsupported_answer_type"


__all__ = ["CHOICE_RE", "INTEGER_RE", "validate_candidate_shape"]
