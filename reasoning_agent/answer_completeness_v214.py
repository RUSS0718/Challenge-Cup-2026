"""v2.1.4 answer-completeness extension with bounded boxed-answer support.

This module decides whether an extracted value is a complete answer for the
host-inferred shape.  It does not judge mathematical correctness.
"""

from __future__ import annotations

import re
from typing import Any

from reasoning_agent.harness_contracts import (
    ANSWER_SHAPE_FINITE_SET,
    ANSWER_SHAPE_FUNCTION_FAMILY,
    ANSWER_SHAPE_INTERVAL_OR_RANGE,
    ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
    ANSWER_SHAPE_PROOF_TEXT,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    _extract_boxed,
    _is_placeholder,
    _strip_math_wrappers,
)


_BARE_SYMBOL = re.compile(r"^[A-Za-z](?:[A-Za-z0-9_']*)$")
_FUNCTION_DEFINITION = re.compile(r"^[A-Za-z][A-Za-z0-9_']*\s*\([^)]*\)\s*=")
_FINAL_ANSWER_MARKER = re.compile(r"(?im)^\s*(?:\*\*)?\s*(?:final\s+answer|最终答案)\s*[:：]")


def assess_answer_completeness(
    candidate: Any,
    *,
    answer_shape: str,
    parsed: Any,
) -> tuple[bool, str]:
    """Return whether a parsed candidate is a complete final answer.

    A bare symbol such as ``x_s`` is intentionally incomplete, while a
    parameterized definition such as ``x_s = ...`` is complete.  The check is
    syntax- and contract-based; it never evaluates the proposed answer.
    """
    if candidate is None:
        return False, "no_candidate"
    source = str(getattr(candidate, "source", ""))
    response = str(getattr(candidate, "response", "") or "")
    arm_source = source in {"arm_primary", "arm_second", "arm_salvage", "arm_runtime_retry", "arm_repair"}
    has_final_marker = arm_source and bool(_FINAL_ANSWER_MARKER.search(response))
    boxed = _extract_boxed(response) if arm_source else []
    has_unique_boxed_answer = len(boxed) == 1 and str(getattr(candidate, "value", "")).strip() == boxed[0].strip()
    has_final_marker = has_final_marker or has_unique_boxed_answer
    if arm_source:
        if not has_final_marker:
            return False, "missing_final_answer_marker"
    if (bool(getattr(parsed, "truncated", False)) or bool(getattr(candidate, "truncated", False))) and not has_final_marker:
        return False, "truncated"
    if (bool(getattr(parsed, "truncated", False)) or bool(getattr(candidate, "truncated", False))) and has_final_marker:
        truncated_tail_reason = "answer_complete_truncated_tail"
    else:
        truncated_tail_reason = "answer_complete"
    if getattr(parsed, "typed_complete", True) is False:
        return False, "typed_parse_incomplete"
    value = _strip_math_wrappers(
        str(getattr(candidate, "normalized_value", "") or getattr(candidate, "value", ""))
    ).strip()
    interval_notation = bool(re.fullmatch(r"(?:\[[^\[\]]+\]|\([^()]+\))", value))
    if not value or (_is_placeholder(value) and not (answer_shape == ANSWER_SHAPE_INTERVAL_OR_RANGE and interval_notation)):
        return False, "placeholder_or_empty"
    if value.endswith(("=", "+", "-", "*", "/", "^", "\\")):
        return False, "open_expression"

    if answer_shape in {ANSWER_SHAPE_SINGLE_NUMERIC, "unknown"} and _BARE_SYMBOL.fullmatch(value):
        return False, "bare_symbol_fragment"
    if answer_shape == ANSWER_SHAPE_PARAMETERIZED_EXPRESSION:
        if _BARE_SYMBOL.fullmatch(value) or not re.search(r"[A-Za-z0-9]|=|→|\\mapsto", value):
            return False, "parameterized_expression_incomplete"
    elif answer_shape == ANSWER_SHAPE_FUNCTION_FAMILY:
        if not _FUNCTION_DEFINITION.search(value):
            return False, "function_definition_incomplete"
    elif answer_shape == ANSWER_SHAPE_FINITE_SET:
        if not (value.startswith(("{", r"\{")) and value.endswith(("}", r"\}"))):
            return False, "finite_set_not_closed"
    elif answer_shape == ANSWER_SHAPE_INTERVAL_OR_RANGE:
        if not (
            re.fullmatch(r"(?:\[[^\[\]]+\]|\([^()]+\))", value)
            or re.search(r"[A-Za-z]\s*[<>≤≥]=?\s*[^,;]+", value)
            or re.search(r"[A-Za-z]\s*∈\s*", value, re.I)
        ):
            return False, "interval_or_range_incomplete"
    elif answer_shape == ANSWER_SHAPE_PROOF_TEXT:
        if str(getattr(candidate, "proof_status", "")) != "complete":
            return False, "proof_not_complete"

    return True, truncated_tail_reason


__all__ = ["assess_answer_completeness"]
