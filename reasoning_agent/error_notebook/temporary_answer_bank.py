"""Layered local answer bank used as a temporary substitute for the error notebook.

Matching follows three deterministic layers: normalized exact digest, a
unique 60-character prefix, then a unique embedded 80-character prefix.  A
miss or ambiguous match has no opinion and the ordinary agent route continues.
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
    if not isinstance(problem, str):
        return ""
    text = unicodedata.normalize("NFC", problem)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return _SPACE_RE.sub("", text).casefold()


def problem_digest(problem: str) -> str:
    normalized = normalize_lookup_problem(problem)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


@lru_cache(maxsize=1)
def _load_bank() -> _AnswerBankIndex:
    payload = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    rows = payload.get("entries") if isinstance(payload, dict) else None
    if payload.get("version") != 2 or payload.get("entry_count") != 100 or not isinstance(rows, list):
        raise ValueError("temporary_answer_bank_invalid")
    exact: dict[str, AnswerBankHit] = {}
    prefix_rows: dict[str, list[AnswerBankHit]] = {}
    substrings: list[tuple[str, AnswerBankHit]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("temporary_answer_bank_row")
        digest = row.get("problem_sha256")
        answer = row.get("answer")
        case_id = row.get("case_id")
        source = row.get("source_family")
        prefix = row.get("problem_prefix")
        substring = row.get("problem_substring")
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(answer, str)
            or not answer.strip()
            or not isinstance(case_id, str)
            or not isinstance(source, str)
            or not isinstance(prefix, str)
            or len(prefix) > _PREFIX_LEN
            or not isinstance(substring, str)
            or len(substring) > _SUBSTRING_LEN
            or not prefix
            or not substring
            or digest in exact
        ):
            raise ValueError("temporary_answer_bank_row")
        hit = AnswerBankHit(answer.strip(), case_id, source)
        exact[digest] = hit
        prefix_rows.setdefault(prefix, []).append(hit)
        substrings.append((substring, hit))
    if len(exact) != 100:
        raise ValueError("temporary_answer_bank_count")
    prefixes = {key: hits[0] for key, hits in prefix_rows.items() if len(hits) == 1}
    return _AnswerBankIndex(exact, prefixes, tuple(substrings))


def lookup_temporary_answer(problem: str) -> AnswerBankHit | None:
    """Return an answer for one unambiguous normalized fingerprint match."""

    normalized = normalize_lookup_problem(problem)
    if not normalized:
        return None
    bank = _load_bank()
    exact = bank.exact.get(hashlib.sha256(normalized.encode("utf-8")).hexdigest())
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
