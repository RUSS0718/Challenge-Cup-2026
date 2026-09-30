"""Deterministic verification seam for ARM-Harness v2.1 conflicts."""

from __future__ import annotations

from dataclasses import dataclass
import json
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
    checked_issue: str = ""
    check_result: str = ""
    remaining_problem: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in FRESH_REVIEW_STATUSES:
            raise ValueError("invalid_fresh_review_status")

    def as_dict(self) -> dict[str, Any]:
        """Return bounded fields for trace and promotion diagnostics."""
        return {
            "status": self.status,
            "checked_issue": self.checked_issue[:240],
            "check_result": self.check_result[:480],
            "remaining_problem": self.remaining_problem,
            "reason": self.reason[:240],
        }


def replacement_decision(
    finding: ChallengerFinding,
    review: FreshReview | None,
) -> tuple[bool, str]:
    """Allow replacement only after a specific objection and passing review."""
    if not finding.supports_replacement:
        return False, "challenger_evidence_insufficient"
    if review is None or review.status != "PASS":
        return False, "fresh_review_not_passed"
    if not _fresh_review_matches_finding(finding, review):
        return False, "fresh_review_issue_mismatch"
    return True, "fresh_review_supported_replacement"


def _fresh_review_matches_finding(finding: ChallengerFinding, review: FreshReview) -> bool:
    """Require the review to name the objection it claims to have checked."""
    checked = " ".join(str(review.checked_issue).casefold().split())
    if not checked or not str(review.check_result).strip():
        return False
    location = " ".join(finding.issue_location.casefold().split())
    claim = " ".join(finding.claim.casefold().split())
    aligned = bool(location and checked == location)
    if not aligned and claim:
        aligned = checked == claim
    if not aligned:
        return False
    return review.remaining_problem in {None, ""}


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
    raw_repairable = payload.get("repairable", False)
    if not isinstance(raw_repairable, bool):
        return ChallengerFinding()
    return ChallengerFinding(
        verdict=verdict,
        issue_type=issue_type,
        issue_location=str(payload.get("issue_location", ""))[:240],
        claim=str(payload.get("claim", ""))[:240],
        evidence=str(payload.get("evidence", ""))[:240],
        repairable=raw_repairable,
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
    """Provide the v2.1.4 no-op verifier until a concrete check is configured."""

    def verify(self, candidate_a: Any, candidate_b: Any, problem: str) -> VerificationResult:
        """Return ``NOT_APPLICABLE`` without inferring a gold answer from text."""
        del candidate_a, candidate_b, problem
        return VerificationResult("NOT_APPLICABLE", None, "no_deterministic_check")


def parse_fresh_review(response: str | None) -> FreshReview:
    """Parse one structured fresh-review object and fail closed on malformed output."""
    text = str(response or "").strip()
    if not text:
        return FreshReview("UNKNOWN", reason="empty_fresh_review")
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        start = text.find("{")
        if start < 0:
            return FreshReview("UNKNOWN", reason="unstructured_fresh_review")
        try:
            payload, _end = json.JSONDecoder().raw_decode(text[start:])
        except (TypeError, ValueError, json.JSONDecodeError):
            return FreshReview("UNKNOWN", reason="malformed_fresh_review")
    if not isinstance(payload, Mapping):
        return FreshReview("UNKNOWN", reason="malformed_fresh_review")
    required_fields = {"status", "checked_issue", "check_result", "remaining_problem"}
    if not required_fields.issubset(payload):
        return FreshReview("UNKNOWN", reason="missing_remaining_problem")
    status = str(payload.get("status", "UNKNOWN")).upper()
    if status not in FRESH_REVIEW_STATUSES:
        return FreshReview("UNKNOWN", reason="invalid_fresh_review_status")
    remaining = payload.get("remaining_problem")
    return FreshReview(
        status=status,
        checked_issue=str(payload.get("checked_issue", ""))[:240],
        check_result=str(payload.get("check_result", ""))[:480],
        remaining_problem=None if remaining is None else str(remaining)[:240],
        reason="structured_fresh_review",
    )


__all__ = ["ChallengerFinding", "DeterministicVerifier", "FreshReview", "VerificationResult", "VerificationStatus", "parse_challenger_finding", "parse_fresh_review", "replacement_decision"]
