"""Bounded, serialisable memory for the FESF per-question protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_STATUS = frozenset({"PROPOSED", "SUPPORTED", "REFUTED", "UNRESOLVED"})


def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value or "")
    limit = max(0, int(limit))
    if len(text) <= limit:
        return text
    marker = "\n...[省略]...\n"
    if limit <= len(marker):
        return text[:limit]
    head = (limit - len(marker) + 1) // 2
    tail = limit - len(marker) - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def _closed_content(text: str) -> bool:
    """Reject visibly unfinished protocol fragments before they become claims."""
    if not text.strip() or text.rstrip().endswith(("\\", "=", "+", "-", "*", "/", "^")):
        return False
    depth = 0
    for char in text:
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


@dataclass
class ClaimRecord:
    id: str
    content: str
    source: str
    status: str = "PROPOSED"
    evidence_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class CandidateRecord:
    branch: str
    answer: str
    supporting_claim_ids: list[str] = field(default_factory=list)


@dataclass
class EvidenceRecord:
    id: str
    source: str
    status: str
    scope: str
    result: str = ""
    assumptions: list[str] = field(default_factory=list)
    claim_id: str = ""
    checked_expression: str = ""
    checked_expected: str = ""


@dataclass
class SolveMemory:
    """State that is allowed to cross A→E within one ``solve`` call.

    The model never mutates this object directly.  The host parser adds
    closed records and controls status transitions after checking identifiers,
    evidence scope, and protocol completeness.
    """

    goal: str = ""
    answer_type: str = ""
    constraints: list[str] = field(default_factory=list)
    claims: list[ClaimRecord] = field(default_factory=list)
    candidates: list[CandidateRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    open_obligations: list[str] = field(default_factory=list)
    loaded_skills: list[dict[str, str]] = field(default_factory=list)
    remaining_calls: int = 5
    remaining_stage_tokens: dict[str, int] = field(default_factory=dict)
    selected_branch: str = ""
    supported_claim_ids: list[str] = field(default_factory=list)
    auxiliary_claim_ids: list[str] = field(default_factory=list)
    refuted_claim_ids: list[str] = field(default_factory=list)
    unresolved_claim_ids: list[str] = field(default_factory=list)
    primary_reason: str = ""

    def add_claim(
        self,
        claim_id: str,
        content: str,
        source: str,
        *,
        depends_on: Iterable[str] = (),
    ) -> bool:
        """Add one closed proposed claim; duplicate IDs are rejected."""
        if not _ID_RE.fullmatch(str(claim_id or "")):
            return False
        content = _clip(content, 900).strip()
        source = _clip(source, 32).strip()
        if not _closed_content(content) or not source or any(c.id == claim_id for c in self.claims):
            return False
        deps = [str(item) for item in depends_on if _ID_RE.fullmatch(str(item))]
        self.claims.append(ClaimRecord(str(claim_id), content, source, depends_on=deps))
        return True

    def add_candidate(self, branch: str, answer: str, supporting_claim_ids: Iterable[str] = ()) -> bool:
        branch = str(branch or "").upper()
        answer = _clip(answer, 500).strip()
        if branch not in {"B", "C"} or not answer:
            return False
        known = {claim.id for claim in self.claims}
        ids = [str(item) for item in supporting_claim_ids if _ID_RE.fullmatch(str(item)) and str(item) in known]
        self.candidates.append(CandidateRecord(branch, answer, ids))
        return True

    def add_evidence(
        self,
        evidence_id: str,
        source: str,
        status: str,
        scope: str,
        result: str = "",
        assumptions: Iterable[str] = (),
        claim_id: str = "",
        *,
        checked_expression: str = "",
        checked_expected: str = "",
    ) -> bool:
        evidence_id = str(evidence_id or "")
        status = str(status or "").upper()
        source_text = _clip(source, 32).strip()
        scope_text = _clip(scope, 240).strip()
        normalized_claim_id = str(claim_id or "")
        if not _ID_RE.fullmatch(evidence_id) or status not in {"EXACT", "REFUTED", "UNKNOWN"}:
            return False
        if not source_text or not scope_text:
            return False
        if normalized_claim_id and not _ID_RE.fullmatch(normalized_claim_id):
            return False
        if normalized_claim_id and not any(
            claim.id == normalized_claim_id for claim in self.claims
        ):
            return False
        if status in {"EXACT", "REFUTED"} and not normalized_claim_id:
            return False
        if any(e.id == evidence_id for e in self.evidence):
            return False
        expression_text = _clip(checked_expression, 300).strip()
        expected_text = _clip(checked_expected, 300).strip()
        if expression_text and normalized_claim_id:
            claim = next((item for item in self.claims if item.id == normalized_claim_id), None)
            # Tool evidence is only attributable when the named claim carries
            # one standalone canonical equation.  A claim id alone, or a
            # substring embedded in a larger/conjunctive claim, is not a
            # semantic proof of that mapping.
            claim_text = re.sub(r"\s+", "", claim.content if claim else "").replace("^", "**")
            expr = re.sub(r"\s+", "", expression_text).replace("^", "**")
            value = re.sub(r"\s+", "", expected_text or result).replace("^", "**")
            if claim is None or not expr or not value or claim_text not in {f"{expr}={value}", f"{expr}=={value}"}:
                return False
        self.evidence.append(
            EvidenceRecord(
                id=evidence_id,
                source=source_text,
                status=status,
                scope=scope_text,
                result=_clip(result, 500).strip(),
                assumptions=[_clip(a, 180).strip() for a in assumptions if str(a).strip()][:6],
                claim_id=normalized_claim_id,
                checked_expression=expression_text,
                checked_expected=expected_text,
            )
        )
        return True

    def set_claim_status(self, claim_id: str, status: str, evidence_ids: Iterable[str] = ()) -> bool:
        status = str(status or "").upper()
        if status not in _STATUS:
            return False
        evidence_values = [str(item) for item in evidence_ids if _ID_RE.fullmatch(str(item))]
        evidence_map = {item.id: item for item in self.evidence}
        # Evidence IDs are host-owned references.  Never let a missing or
        # cross-claim ID enter a claim record; supported/refuted transitions
        # additionally require the corresponding deterministic status.
        evidence_values = [
            item for item in evidence_values
            if item in evidence_map and evidence_map[item].claim_id == claim_id
        ]
        if status in {"SUPPORTED", "REFUTED"} and not evidence_values:
            return False
        if status == "SUPPORTED" and any(evidence_map[item].status != "EXACT" for item in evidence_values):
            return False
        if status == "REFUTED" and any(evidence_map[item].status != "REFUTED" for item in evidence_values):
            return False
        for claim in self.claims:
            if claim.id == claim_id:
                claim.status = status
                claim.evidence_ids = evidence_values
                return True
        return False

    def set_synthesis(
        self,
        *,
        primary_branch: str,
        primary_reason: str,
        supported: Iterable[str] = (),
        auxiliary: Iterable[str] = (),
        refuted: Iterable[str] = (),
        unresolved: Iterable[str] = (),
        open_obligations: Iterable[str] = (),
    ) -> None:
        self.selected_branch = primary_branch if primary_branch in {"B", "C"} else ""
        self.primary_reason = _clip(primary_reason, 700).strip()
        known = {claim.id for claim in self.claims}

        def valid_ids(values: Iterable[str]) -> list[str]:
            return list(dict.fromkeys(str(i) for i in values if _ID_RE.fullmatch(str(i)) and str(i) in known))

        # Synthesis categories are mutually exclusive.  If a caller supplies
        # a conflicting claim (for example both supported and refuted), expose
        # it only as unresolved rather than leaking contradictory state to E.
        categories = {
            "supported": set(valid_ids(supported)),
            "auxiliary": set(valid_ids(auxiliary)),
            "refuted": set(valid_ids(refuted)),
            "unresolved": set(valid_ids(unresolved)),
        }
        memberships: dict[str, set[str]] = {}
        for category, ids in categories.items():
            for claim_id in ids:
                memberships.setdefault(claim_id, set()).add(category)
        self.supported_claim_ids = [
            claim_id for claim_id in (valid_ids(supported))
            if memberships.get(claim_id) == {"supported"}
        ]
        self.auxiliary_claim_ids = [
            claim_id for claim_id in (valid_ids(auxiliary))
            if memberships.get(claim_id) == {"auxiliary"}
        ]
        self.refuted_claim_ids = [
            claim_id for claim_id in (valid_ids(refuted))
            if memberships.get(claim_id) == {"refuted"}
        ]
        explicit_unresolved = valid_ids(unresolved)
        conflict_ids = {
            claim_id for claim_id, claim_categories in memberships.items()
            if len(claim_categories) > 1
        }
        self.unresolved_claim_ids = list(dict.fromkeys(
            explicit_unresolved
            + [claim.id for claim in self.claims if claim.id in conflict_ids]
            + [claim.id for claim in self.claims
               if claim.id not in self.supported_claim_ids
               and claim.id not in self.auxiliary_claim_ids
               and claim.id not in self.refuted_claim_ids
               and claim.id not in explicit_unresolved
               and claim.id not in conflict_ids]
        ))
        self.open_obligations = [_clip(item, 500).strip() for item in open_obligations if str(item).strip()][:8]

    def consume_call(self, stage: str, max_tokens: int) -> None:
        self.remaining_calls = max(0, int(self.remaining_calls) - 1)
        self.remaining_stage_tokens[str(stage)] = max(0, int(max_tokens))

    def mark_loaded_skill(self, name: str, content_hash: str) -> None:
        if name and not any(item.get("name") == name for item in self.loaded_skills):
            self.loaded_skills.append({"name": _clip(name, 64), "content_hash": _clip(content_hash, 64)})

    def _claim_rows(self, ids: Iterable[str] | None = None) -> list[ClaimRecord]:
        allowed = set(ids) if ids is not None else None
        return [claim for claim in self.claims if allowed is None or claim.id in allowed]

    def render_for_d(self, max_chars: int = 7000) -> str:
        rows = [
            f"ANALYSIS_GOAL: {_clip(self.goal, 700)}",
            f"ANSWER_TYPE: {_clip(self.answer_type, 180)}",
            "CONSTRAINTS: " + " | ".join(_clip(x, 240) for x in self.constraints[:8]),
            "CLAIMS:",
        ]
        for claim in self.claims:
            rows.append(
                f"{claim.id} [{claim.source}; {claim.status}; evidence={','.join(claim.evidence_ids) or 'none'}]: "
                f"{_clip(claim.content, 520)}"
            )
        if self.candidates:
            rows.append("CANDIDATES:")
            for candidate in self.candidates:
                rows.append(f"{candidate.branch}: {_clip(candidate.answer, 420)} (claims={','.join(candidate.supporting_claim_ids) or 'none'})")
        if self.evidence:
            rows.append("EVIDENCE:")
            for item in self.evidence:
                assumptions = ", ".join(_clip(a, 120) for a in item.assumptions[:6]) or "none"
                rows.append(
                    f"{item.id} [{item.status}; claim={item.claim_id or 'none'}; scope={_clip(item.scope, 160)}; "
                    f"expr={_clip(item.checked_expression, 180) or 'none'}; expected={_clip(item.checked_expected, 180) or 'none'}; "
                    f"assumptions={assumptions}]: "
                    f"{_clip(item.result, 300)}"
                )
        return _clip("\n".join(rows), max_chars)

    def render_for_e(self, max_chars: int = 7000) -> str:
        """Render only parsed, bounded state; never raw B/C/D responses."""
        rows = [
            f"PRIMARY_BRANCH: {self.selected_branch or 'UNKNOWN'}",
            f"PRIMARY_REASON: {_clip(self.primary_reason, 500)}",
            "SUPPORTED_CLAIMS: " + (", ".join(self.supported_claim_ids) or "none"),
            "AUXILIARY_CLAIMS: " + (", ".join(self.auxiliary_claim_ids) or "none"),
            "REFUTED_CLAIMS: " + (", ".join(self.refuted_claim_ids) or "none"),
            "UNRESOLVED_CLAIMS: " + (", ".join(self.unresolved_claim_ids) or "none"),
            "CLAIM_DETAILS:",
        ]
        visible = set(self.supported_claim_ids + self.auxiliary_claim_ids + self.refuted_claim_ids + self.unresolved_claim_ids)
        for claim in self._claim_rows(visible or None):
            rows.append(f"{claim.id} [{claim.source}; {claim.status}; evidence={','.join(claim.evidence_ids) or 'none'}]: {_clip(claim.content, 520)}")
        if self.candidates:
            rows.append("CANDIDATES:")
            allowed_branches = {self.selected_branch} if self.selected_branch else set()
            auxiliary_sources = {
                claim.source for claim in self.claims if claim.id in set(self.auxiliary_claim_ids)
            }
            allowed_branches.update(auxiliary_sources)
            for candidate in self.candidates:
                if candidate.branch in allowed_branches:
                    rows.append(f"{candidate.branch}: {_clip(candidate.answer, 420)} (claims={','.join(candidate.supporting_claim_ids) or 'none'})")
        if self.evidence:
            rows.append("EVIDENCE:")
            for item in self.evidence:
                assumptions = ", ".join(_clip(a, 120) for a in item.assumptions[:6]) or "none"
                rows.append(
                    f"{item.id} [{item.status}; claim={item.claim_id or 'none'}; scope={_clip(item.scope, 160)}; "
                    f"expr={_clip(item.checked_expression, 180) or 'none'}; expected={_clip(item.checked_expected, 180) or 'none'}; "
                    f"assumptions={assumptions}]: "
                    f"{_clip(item.result, 300)}"
                )
        rows.append("OPEN: " + " | ".join(self.open_obligations[:8]))
        return _clip("\n".join(rows), max_chars)

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal": _clip(self.goal, 700),
            "answer_type": _clip(self.answer_type, 180),
            "constraints": [_clip(x, 240) for x in self.constraints[:8]],
            "claims": [asdict(c) for c in self.claims[:32]],
            "candidates": [asdict(c) for c in self.candidates[:8]],
            "evidence": [asdict(e) for e in self.evidence[:32]],
            "open_obligations": self.open_obligations[:8],
            "loaded_skills": self.loaded_skills[:4],
            "remaining_calls": self.remaining_calls,
            "remaining_stage_tokens": dict(self.remaining_stage_tokens),
            "selected_branch": self.selected_branch,
            "supported_claim_ids": self.supported_claim_ids[:32],
            "auxiliary_claim_ids": self.auxiliary_claim_ids[:32],
            "refuted_claim_ids": self.refuted_claim_ids[:32],
            "unresolved_claim_ids": self.unresolved_claim_ids[:32],
        }


__all__ = ["ClaimRecord", "EvidenceRecord", "CandidateRecord", "SolveMemory"]
