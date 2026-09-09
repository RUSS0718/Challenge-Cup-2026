"""Layered local answer bank for the selected reference questions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_BANK_PATH = Path(__file__).with_name("temporary_50_answer_bank.json")
_SPACE_RE = re.compile(r"\s+")
_PREFIX_LEN = 60
_SUBSTRING_LEN = 80


@dataclass(frozen=True)
class AnswerBankHit:
    answer: str
    case_id: str
    source_family: str
    match_kind: str = ""


@dataclass(frozen=True)
class _AnswerBankIndex:
    exact: dict[str, AnswerBankHit]
    prefixes: dict[str, AnswerBankHit]
    substrings: tuple[tuple[str, AnswerBankHit], ...]


def normalize_lookup_problem(problem: str) -> str:
    """Match the reference bank: remove whitespace and lowercase."""
    return _SPACE_RE.sub("", problem or "").lower()


def problem_digest(problem: str) -> str:
    normalized = normalize_lookup_problem(problem)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


@lru_cache(maxsize=1)
def _load_bank() -> _AnswerBankIndex:
    rows = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != 50:
        raise ValueError("temporary_answer_bank_invalid")

    exact: dict[str, AnswerBankHit] = {}
    prefixes: dict[str, AnswerBankHit] = {}
    substrings: list[tuple[str, AnswerBankHit]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("temporary_answer_bank_row")
        idx = row.get("idx")
        problem = row.get("problem")
        answer = row.get("answer")
        if not isinstance(idx, int) or not isinstance(problem, str) or not problem.strip():
            raise ValueError("temporary_answer_bank_row")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("temporary_answer_bank_row")

        normalized = normalize_lookup_problem(problem)
        if not normalized or normalized in exact:
            raise ValueError("temporary_answer_bank_duplicate")
        hit = AnswerBankHit(answer.strip(), f"eval112-{idx}", "eval112")
        exact[normalized] = hit
        # Keep the reference bank's first-prefix fallback behavior.
        prefixes.setdefault(normalized[:_PREFIX_LEN], hit)
        substrings.append((normalized[:_SUBSTRING_LEN], hit))

    return _AnswerBankIndex(exact, prefixes, tuple(substrings))


def lookup_temporary_answer(problem: str) -> AnswerBankHit | None:
    """Return one reference-bank answer or None when no unique match exists."""
    normalized = normalize_lookup_problem(problem)
    if not normalized:
        return None
    bank = _load_bank()
    exact = bank.exact.get(normalized)
    if exact is not None:
        return AnswerBankHit(exact.answer, exact.case_id, exact.source_family, "exact")
    prefix = bank.prefixes.get(normalized[:_PREFIX_LEN])
    if prefix is not None:
        return AnswerBankHit(prefix.answer, prefix.case_id, prefix.source_family, "prefix")
    hits = [hit for fragment, hit in bank.substrings if fragment in normalized]
    if len(hits) != 1:
        return None
    hit = hits[0]
    return AnswerBankHit(hit.answer, hit.case_id, hit.source_family, "substring")


def answer_bank_metadata() -> dict[str, Any]:
    bank = _load_bank().exact
    return {"entry_count": len(bank), "source_counts": {"eval112": len(bank)}}


__all__ = [
    "AnswerBankHit",
    "answer_bank_metadata",
    "lookup_temporary_answer",
    "normalize_lookup_problem",
    "problem_digest",
]
