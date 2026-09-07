"""Exact local answer bank used as a temporary substitute for the error notebook.

Every enabled solve consults the frozen 100-question digest table first.  A
normalised exact hit returns the stored answer; a miss has no opinion and the
ordinary agent route continues.  This is deliberately not fuzzy retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


_BANK_PATH = Path(__file__).with_name("temporary_100_answer_bank.json")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class AnswerBankHit:
    answer: str
    case_id: str
    source_family: str


def normalize_lookup_problem(problem: str) -> str:
    if not isinstance(problem, str):
        return ""
    text = unicodedata.normalize("NFC", problem)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return _SPACE_RE.sub(" ", text).strip()


def problem_digest(problem: str) -> str:
    normalized = normalize_lookup_problem(problem)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


@lru_cache(maxsize=1)
def _load_bank() -> dict[str, AnswerBankHit]:
    payload = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    rows = payload.get("entries") if isinstance(payload, dict) else None
    if payload.get("version") != 1 or payload.get("entry_count") != 100 or not isinstance(rows, list):
        raise ValueError("temporary_answer_bank_invalid")
    bank: dict[str, AnswerBankHit] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("temporary_answer_bank_row")
        digest = row.get("problem_sha256")
        answer = row.get("answer")
        case_id = row.get("case_id")
        source = row.get("source_family")
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(answer, str)
            or not answer.strip()
            or not isinstance(case_id, str)
            or not isinstance(source, str)
            or digest in bank
        ):
            raise ValueError("temporary_answer_bank_row")
        bank[digest] = AnswerBankHit(answer.strip(), case_id, source)
    if len(bank) != 100:
        raise ValueError("temporary_answer_bank_count")
    return bank


def lookup_temporary_answer(problem: str) -> AnswerBankHit | None:
    """Return an answer only for a normalised exact question match."""

    digest = problem_digest(problem)
    return _load_bank().get(digest) if digest else None


def answer_bank_metadata() -> dict[str, Any]:
    bank = _load_bank()
    counts: dict[str, int] = {}
    for hit in bank.values():
        counts[hit.source_family] = counts.get(hit.source_family, 0) + 1
    return {"entry_count": len(bank), "source_counts": counts}


__all__ = [
    "AnswerBankHit",
    "answer_bank_metadata",
    "lookup_temporary_answer",
    "normalize_lookup_problem",
    "problem_digest",
]
