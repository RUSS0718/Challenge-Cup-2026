"""Deterministic candidate extraction and surface canonicalization.

The parser follows a fixed, auditable order.  It preserves source metadata and
fails closed when multiple conflicting answers or incomplete structures appear.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable

from reasoning_agent.answer_contract import AnswerType, Candidate, Completeness, TaskContract, Verification


_PLACEHOLDERS = {"unknown", "答案", "final answer", "<answer>", "[answer]", "n/a", "none", "null"}
_MARKER_RE = re.compile(r"(?im)^\s*(?:FINAL_CANDIDATE|FINAL ANSWER|答案|最终答案)\s*[:：]\s*(.+?)\s*$")
_BOXED_RE = re.compile(r"\\boxed\{([^{}]{1,256})\}")
_JSON_RE = re.compile(r"(?s)\{\s*['\"](?:value|answer)['\"]\s*:\s*['\"](.+?)['\"]\s*(?:,|})")


@dataclass(frozen=True)
class ParseResult:
    """Result of parsing one response, including explicit rejection details."""

    candidates: tuple[Candidate, ...] = ()
    rejection_reason: str = ""
    parser_source: str = "none"

    @property
    def complete(self) -> bool:
        """Return true when exactly one accepted candidate exists."""
        return len(self.candidates) == 1 and self.candidates[0].accepted


def _hash_span(value: str) -> str:
    """Hash a raw candidate span so ledgers remain free of full responses."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize(value: str, contract: TaskContract) -> str:
    """Normalize presentation wrappers without reordering mathematical data."""
    text = str(value or "").strip().replace("−", "-").replace("–", "-")
    if text.startswith(r"\boxed{") and text.endswith("}"):
        body = text[len(r"\boxed{"):-1]
        if _balanced(body):
            text = body.strip()
    text = re.sub(r"^\$+|\$+$", "", text).strip()
    text = re.sub(r"^\\(?:dfrac|tfrac)\{([^{}]+)\}\{([^{}]+)\}$", r"\\frac{\1}{\2}", text)
    text = re.sub(r"\\left|\\right|\\,|\\!", "", text)
    if contract.answer_type == AnswerType.SET and text.startswith("{") and text.endswith("}"):
        # A set is unordered; only this contract permits sorting its numeric surface.
        parts = [part.strip() for part in text[1:-1].split(",") if part.strip()]
        if parts and all(re.fullmatch(r"[+-]?\d+(?:/\d+)?", part) for part in parts):
            text = "{" + ",".join(sorted(set(parts), key=lambda item: (float(item.split("/")[0]) / float(item.split("/")[1]) if "/" in item else float(item)))) + "}"
    return re.sub(r"\s+", "", text).rstrip("。；;.!?")


def _is_placeholder(value: str) -> bool:
    """Reject empty, placeholder, or visibly unfinished candidate values."""
    compact = str(value or "").strip().casefold()
    return not compact or compact in _PLACEHOLDERS or bool(re.fullmatch(r"[.。…]+", compact))


def _balanced(value: str) -> bool:
    """Check basic delimiter balance before admitting a candidate."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in value:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def _answer_type(value: str, contract: TaskContract) -> AnswerType:
    """Use the task type when known, otherwise infer a bounded surface type."""
    if contract.answer_type != AnswerType.UNKNOWN:
        return contract.answer_type
    if re.fullmatch(r"[A-Da-d][.)]?", value.strip()):
        return AnswerType.CHOICE
    if re.fullmatch(r"[+-]?\d+", value.strip()):
        return AnswerType.INTEGER
    if re.fullmatch(r"[+-]?\d+(?:/\d+)?", value.strip()):
        return AnswerType.RATIONAL
    if value.strip().startswith("{") and value.strip().endswith("}"):
        return AnswerType.SET
    return AnswerType.EXPRESSION


def _candidate(value: str, source: str, contract: TaskContract, *, complete: bool = True, reason: str = "") -> Candidate:
    """Build one candidate while recording its raw-span hash and canonical form."""
    clean = str(value or "").strip()
    canonical = canonicalize(clean, contract)
    rejected = reason or ("placeholder" if _is_placeholder(clean) else "unbalanced" if not _balanced(clean) else "")
    return Candidate(
        value=clean,
        answer_type=_answer_type(clean, contract),
        source=source,
        completeness=Completeness.COMPLETE if complete and not rejected else Completeness.PARTIAL,
        confidence="unverified",
        verification=Verification.UNKNOWN,
        raw_span_hash=_hash_span(clean),
        rejection_reason=rejected,
        canonical_value=canonical,
    )


def parse_response(response: str, contract: TaskContract) -> ParseResult:
    """Extract candidates in the contract's fixed precedence order."""
    text = str(response or "").strip()
    if not text:
        return ParseResult(rejection_reason="empty_response")
    staged: list[tuple[str, str]] = []
    try:
        for match in _JSON_RE.finditer(text):
            staged.append(("typed_answer", match.group(1)))
        if not staged:
            staged.extend(("answer_marker", match.group(1)) for match in _MARKER_RE.finditer(text))
        if not staged:
            staged.extend(("boxed", match.group(1)) for match in _BOXED_RE.finditer(text))
        if not staged and contract.answer_type == AnswerType.CHOICE:
            staged.extend(("choice", match.group(1)) for match in re.finditer(r"(?im)^\s*([A-D])\s*[.)]?\s*$", text))
        if not staged and contract.answer_type in {AnswerType.INTEGER, AnswerType.RATIONAL, AnswerType.UNKNOWN}:
            staged.extend(("standalone_numeric", match.group(1)) for match in re.finditer(r"(?m)^\s*([+-]?\d+(?:/\d+)?)\s*$", text))
        if not staged:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                staged.append(("terminal_line", lines[-1]))
    except (TypeError, ValueError):
        return ParseResult(rejection_reason="parser_error")
    candidates = tuple(_candidate(value, source, contract) for source, value in staged if value.strip())
    usable = tuple(candidate for candidate in candidates if candidate.accepted)
    if not usable:
        reason = candidates[0].rejection_reason if candidates else "no_candidate"
        return ParseResult(candidates=candidates, rejection_reason=reason, parser_source=staged[0][0] if staged else "none")
    canonical_values = {candidate.canonical_value for candidate in usable}
    if len(canonical_values) > 1:
        return ParseResult(candidates=usable, rejection_reason="conflicting_candidates", parser_source=usable[0].source)
    return ParseResult(candidates=(usable[0],), parser_source=usable[0].source)


def candidate_from_mapping(data: dict, contract: TaskContract) -> Candidate:
    """Parse a persisted typed candidate without trusting model confidence fields."""
    value = str(data.get("value", data.get("answer", "")))
    source = str(data.get("source", "persisted"))
    return _candidate(value, source, contract, complete=bool(data.get("answer_complete", True)))


__all__ = ["ParseResult", "candidate_from_mapping", "canonicalize", "parse_response"]
