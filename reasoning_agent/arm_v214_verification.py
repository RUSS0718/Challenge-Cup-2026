"""Deterministic verification seam for ARM-Harness v2.1 conflicts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Literal, Mapping


VerificationStatus = Literal["A", "B", "UNKNOWN", "NOT_APPLICABLE"]
_STATUSES = frozenset({"A", "B", "UNKNOWN", "NOT_APPLICABLE"})
CHALLENGER_VERDICTS = frozenset({"NO_OBJECTION", "OBJECTION", "UNKNOWN"})
CHALLENGER_ISSUE_TYPES = frozenset({"arithmetic", "substitution", "domain", "boundary", "missing_case", "format", "other"})
FRESH_REVIEW_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})


@dataclass(frozen=True)
class ChallengerFinding:
    """Bounded structured objection emitted by a challenger."""

    verdict: str = "UNKNOWN"
    issue_type: str = "other"
    issue_location: str = ""
    claim: str = ""
    evidence: str = ""
    repairable: bool = False
    coverage: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in CHALLENGER_VERDICTS:
            raise ValueError("invalid_challenger_verdict")
        if self.issue_type not in CHALLENGER_ISSUE_TYPES:
            raise ValueError("invalid_challenger_issue_type")

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "issue_type": self.issue_type,
            "issue_location": self.issue_location[:240],
            "claim": self.claim[:240],
            "evidence": self.evidence[:240],
            "repairable": bool(self.repairable),
            "coverage": self.coverage[:240],
        }

    @property
    def supports_replacement(self) -> bool:
        return bool(
            self.verdict == "OBJECTION"
            and self.issue_location.strip()
            and self.evidence.strip()
            and self.repairable
        )


@dataclass(frozen=True)
class FreshReview:
    """Result of rechecking a repaired candidate against the original issue."""

    status: str
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in FRESH_REVIEW_STATUSES:
            raise ValueError("invalid_fresh_review_status")


def replacement_decision(
    finding: ChallengerFinding,
    review: FreshReview | None,
) -> tuple[bool, str]:
    """Allow replacement only after a specific objection and passing review."""
    if not finding.supports_replacement:
        return False, "challenger_evidence_insufficient"
    if review is None or review.status != "PASS":
        return False, "fresh_review_not_passed"
    return True, "fresh_review_supported_replacement"


def parse_challenger_finding(response: str | None) -> ChallengerFinding:
    """Parse one JSON challenger object and fail closed on malformed output."""
    text = str(response or "").strip()
    if not text:
        return ChallengerFinding()
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        start = text.find("{")
        if start < 0:
            return ChallengerFinding()
        try:
            payload, _end = json.JSONDecoder().raw_decode(text[start:])
        except (TypeError, ValueError, json.JSONDecodeError):
            return ChallengerFinding()
    if not isinstance(payload, Mapping):
        return ChallengerFinding()
    verdict = str(payload.get("verdict", "UNKNOWN")).upper()
    issue_type = str(payload.get("issue_type", "other")).lower()
    if verdict not in CHALLENGER_VERDICTS or issue_type not in CHALLENGER_ISSUE_TYPES:
        return ChallengerFinding()
    return ChallengerFinding(
        verdict=verdict,
        issue_type=issue_type,
        issue_location=str(payload.get("issue_location", ""))[:240],
        claim=str(payload.get("claim", ""))[:240],
        evidence=str(payload.get("evidence", ""))[:240],
        repairable=bool(payload.get("repairable", False)),
        coverage=str(payload.get("coverage", ""))[:240],
    )


@dataclass(frozen=True)
class VerificationResult:
    """Describe a bounded check between two existing candidates."""

    status: VerificationStatus
    candidate_id: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        """Reject unsupported decisions before they reach the resolver seam."""
        if self.status not in _STATUSES:
            raise ValueError("invalid_verification_status")
        if self.status in {"A", "B"} and not str(self.candidate_id or "").strip():
            raise ValueError("selected_verification_requires_candidate_id")


class DeterministicVerifier:
    """Run only narrow, explicit numeric checks and fail closed otherwise."""

    def verify(self, candidate_a: Any, candidate_b: Any, problem: str) -> VerificationResult:
        """Select a candidate only when the problem states an exact numeric RHS."""
        match = re.search(r"(?:=|等于)\s*([+-]?\d+(?:/\d+)?)\s*[。.!！?？]*$", str(problem or ""))
        if match:
            from reasoning_agent.harness_contracts import value_equivalence

            expected = match.group(1)
            a_match = value_equivalence(str(getattr(candidate_a, "value", "")), expected) == "EQUIVALENT"
            b_match = value_equivalence(str(getattr(candidate_b, "value", "")), expected) == "EQUIVALENT"
            if a_match != b_match:
                selected = candidate_a if a_match else candidate_b
                return VerificationResult(
                    "A" if a_match else "B",
                    str(getattr(selected, "candidate_id", "")),
                    "explicit_numeric_rhs_match",
                )
        return VerificationResult("NOT_APPLICABLE", None, "no_deterministic_check")


__all__ = ["ChallengerFinding", "DeterministicVerifier", "FreshReview", "VerificationResult", "VerificationStatus", "parse_challenger_finding", "replacement_decision"]
