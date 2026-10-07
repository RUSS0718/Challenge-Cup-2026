"""Fail-closed substitution evidence for numeric answer candidates.

The model supplies only a constraint-checking program.  The candidate is
parsed as a small numeric value and passed to ``pot_executor`` as an execution
environment value; it is never interpolated into program source.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from pot_executor import PotExecutorConfig, execute_program
from user_agent import normalize_answer


_RATIONAL_RE = re.compile(r"^-?\d+(?:/\d+)?$")
_CODE_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_constraint_program(response: str) -> str:
    """Extract only an optional fenced program; otherwise preserve raw text."""
    if not isinstance(response, str):
        return ""
    match = _CODE_FENCE_RE.search(response)
    return (match.group(1) if match else response).strip()


def _numeric_candidate(candidate: str) -> Any | None:
    normalized = normalize_answer(candidate)
    if not _RATIONAL_RE.fullmatch(normalized):
        return None
    try:
        number = Fraction(normalized)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    try:
        import sympy
    except ImportError:
        return None
    return sympy.Rational(number.numerator, number.denominator)


def _evidence(
    execution_status: str,
    claim_status: str,
    evidence: str,
    *,
    reason: str | None = None,
    result: str | None = None,
) -> dict[str, Any]:
    output = {
        "source": "substitution_check",
        "execution_status": execution_status,
        "claim_status": claim_status,
        "evidence": evidence,
        "deterministic": True,
        "error": reason,
    }
    if result is not None:
        output["result"] = result
    return output


def check_substitution(
    program: str,
    candidate: str,
    *,
    config: PotExecutorConfig | None = None,
) -> dict[str, Any]:
    """Run a model-generated PASS/FAIL constraint check for one candidate.

    Only a numeric candidate can enter this validator.  A successful program
    must print exactly the boolean result of its constraint; malformed or
    unsupported programs produce UNKNOWN evidence and can never support a
    candidate.
    """
    value = _numeric_candidate(candidate)
    if value is None:
        return _evidence(
            "UNSUPPORTED",
            "UNKNOWN",
            "candidate_not_numeric",
            reason="candidate_not_numeric",
        )

    result = execute_program(program, config=config, environment={"candidate": value})
    if result.get("status") != "SUCCESS":
        reason = str(result.get("reason") or "execution_failed")
        return _evidence(
            str(result.get("status") or "ERROR"),
            "UNKNOWN",
            reason,
            reason=reason,
        )

    answer = result.get("answer")
    if answer == "True":
        return _evidence("SUCCESS", "SUPPORTED", "constraint_passed", result="PASS")
    if answer == "False":
        return _evidence("SUCCESS", "REFUTED", "constraint_failed", result="FAIL")
    return _evidence(
        "ERROR",
        "UNKNOWN",
        "program_must_print_boolean",
        reason="program_must_print_boolean",
    )
