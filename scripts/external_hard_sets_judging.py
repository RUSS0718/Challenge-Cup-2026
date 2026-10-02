"""Apply answer extraction and local verdict rules to external hard-set rows.

This module owns the distinction between the runner's native diagnostic
judgment and the stricter submission-contract judgment. It has no model-call
or artifact-writing responsibilities.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from user_agent import answer_equivalence, extract_answer_first, extract_final_answer

ROOT = Path(__file__).resolve().parents[1]
INTEGER_RE = re.compile(r"-?\d+")
_UNKNOWN_FINALS = frozenset({"UNKNOWN", "未能生成有效数学答案。"})
_MATH_WORDS = frozenset({
    "arccos", "arcsin", "arctan", "cdot", "circ", "cos", "dfrac", "det",
    "exp", "frac", "gcd", "ge", "in", "infty", "lcm", "le", "lim", "ln",
    "log", "max", "mathbb", "mathcal", "mathbf", "mathrm", "mid", "min",
    "mod", "neq", "pi", "pm", "prod", "sin", "sqrt", "sum", "tan", "tfrac",
    "times",
})
_CONTRACT_VALUE_RE = re.compile(r"^[\sA-Za-z0-9_+*/^=<>≤≥.,(){}\[\]\\|±×÷%\-]+$")
_CONTRACT_SENTENCE_PUNCTUATION_RE = re.compile(r"[，。；;、？！:：\"“”‘’]")


def is_unknown_final(final_response: Any) -> bool:
    """Return whether a final response is empty or explicitly abstains."""
    if not isinstance(final_response, str) or not final_response.strip():
        return True
    return final_response.strip().upper() in _UNKNOWN_FINALS


def normalize_answer(text: str) -> str:
    """Normalize common LaTeX and numeric wrappers for diagnostic comparison."""
    normalized = str(text or "").strip().strip("$").strip()
    normalized = normalized.replace("\\left", "").replace("\\right", "")
    normalized = normalized.replace("\\!", "").replace("\\,", "")
    normalized = normalized.replace("dfrac", "frac").replace("tfrac", "frac")
    normalized = re.sub(r"\\text\{[^}]*\}", "", normalized)
    normalized = re.sub(r"\s+", "", normalized).rstrip(".")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", normalized):
        normalized = normalized.replace(",", "")
    return normalized.lower()


def math_verify_ok(pred: str, gold: str) -> bool | None:
    """Run the repository's one-shot Math-Verify helper without importing it."""
    helper = ROOT / "scripts" / "_math_verify_once.py"
    payload = json.dumps({"pred": pred, "gold": gold})
    try:
        proc = subprocess.run(
            [sys.executable, str(helper), payload],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        output = proc.stdout.strip()
        if not output:
            return None
        return bool(json.loads(output).get("ok"))
    except Exception:
        return None


def judge(pred: str, gold: str, family: str) -> dict[str, str]:
    """Return the native diagnostic verdict and the check that produced it."""
    if not pred or pred.strip().upper() in _UNKNOWN_FINALS:
        return {"verdict": "invalid", "detail": "empty_or_unknown"}
    if family == "AIME":
        matches = INTEGER_RE.findall(pred or "")
        if not matches:
            return {"verdict": "invalid", "detail": "pred_not_int"}
        try:
            ok = int(matches[-1]) == int(str(gold).strip())
        except ValueError:
            return {"verdict": "invalid", "detail": "gold_not_int"}
        return {"verdict": "correct" if ok else "incorrect", "detail": "aime_integer_exact"}
    if normalize_answer(pred) == normalize_answer(gold):
        return {"verdict": "correct", "detail": "normalized_string"}
    verified = math_verify_ok(pred, gold)
    if verified:
        return {"verdict": "correct", "detail": "math_verify"}
    if verified is None and re.fullmatch(r"-?\d+", normalize_answer(pred)) and normalize_answer(pred) == normalize_answer(gold):
        return {"verdict": "correct", "detail": "int_string"}
    if answer_equivalence(pred, str(gold)) == "EQUIVALENT":
        return {"verdict": "correct", "detail": "answer_equivalence"}
    return {"verdict": "incorrect", "detail": "no_check_matched"}


def _is_contract_math_value(value: str) -> bool:
    """Accept a compact mathematical token while rejecting prose sentences."""
    candidate = str(value or "").strip().strip("$*").strip().rstrip(".").strip()
    if not candidate or len(candidate) > 120:
        return False
    if _CONTRACT_SENTENCE_PUNCTUATION_RE.search(candidate):
        return False
    if not _CONTRACT_VALUE_RE.fullmatch(candidate):
        return False
    words = re.findall(r"[A-Za-z]+", candidate)
    if any(len(word) > 1 and word.lower() not in _MATH_WORDS for word in words):
        return False
    return bool(re.search(r"\d|[=<>≤≥]|\\[A-Za-z]+|[A-Za-z]", candidate))


def extract_contract_answer(final_response: str, family: str = "") -> str:
    """Extract a format-valid answer or return an empty string.

    The general parser supplies a candidate; this boundary rejects prose and
    requires a single integer for AIME submissions.
    """
    if is_unknown_final(final_response):
        return ""
    extracted = extract_answer_first(final_response) or extract_final_answer(final_response) or ""
    if not _is_contract_math_value(extracted):
        return ""
    if family == "AIME":
        aime_value = normalize_answer(extracted.strip().strip("$*").rstrip(".").strip())
        if not re.fullmatch(r"-?\d+", aime_value):
            return ""
        return aime_value
    return extracted.strip()


def contract_check(final_response: str, gold: str, family: str = "") -> dict[str, str]:
    """Return the submission-contract verdict using the problem-family rules."""
    extracted = extract_contract_answer(final_response, family)
    if not extracted:
        return {"verdict": "invalid"}
    family_gold = str(gold)
    if family == "AIME":
        try:
            correct = int(normalize_answer(extracted)) == int(family_gold.strip())
        except ValueError:
            return {"verdict": "invalid"}
        return {"verdict": "correct" if correct else "incorrect"}
    if normalize_answer(extracted) == normalize_answer(family_gold):
        return {"verdict": "correct"}
    if math_verify_ok(extracted, family_gold):
        return {"verdict": "correct"}
    if answer_equivalence(extracted, family_gold) == "EQUIVALENT":
        return {"verdict": "correct"}
    return {"verdict": "incorrect"}
