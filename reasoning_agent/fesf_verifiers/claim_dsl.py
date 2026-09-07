"""Bounded Claim DSL for Host Loop verifiers.

The model may propose a local claim or request verification.  The host owns
parsing, adapter input, and evidence records.  Nothing here is imported by the
default solve path.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .adapters import (
    CounterexampleAdapter,
    FiniteDomainAdapter,
    SymbolicConstraintAdapter,
    VerificationResult,
)


DSL_VERSION = 1
MAX_OBJECT_CHARS = 1_200
MAX_EXPRESSION_CHARS = 256
MAX_ASSUMPTIONS = 8
MAX_VALUES = 64
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_BRANCH_RE = re.compile(r"^[BC]$")
ALLOWED_KINDS = frozenset({"claim", "verify"})
ALLOWED_CLAIM_TYPES = frozenset({"relation", "finite_predicate", "counterexample_search"})
ALLOWED_SCOPES = frozenset(
    {
        "symbolic_identity",
        "symbolic_relation",
        "finite_predicate",
        "counterexample_search",
    }
)
FORBIDDEN_SCOPES = frozenset(
    {
        "whole_problem",
        "proof_complete",
        "answer_verified",
        "domain_fully_satisfied",
        "whole_problem_is_solved",
        "therefore_final_answer_is_correct",
    }
)
ALLOWED_RELATIONS = frozenset({"==", "!=", "<", "<=", ">", ">="})
ALLOWED_ADAPTERS = frozenset({"symbolic-constraint", "finite-domain", "counterexample"})
CLAIM_TYPE_TO_ADAPTER = {
    "relation": "symbolic-constraint",
    "finite_predicate": "finite-domain",
    "counterexample_search": "counterexample",
}
CLAIM_TYPE_TO_SCOPE = {
    "relation": frozenset({"symbolic_identity", "symbolic_relation"}),
    "finite_predicate": frozenset({"finite_predicate"}),
    "counterexample_search": frozenset({"counterexample_search"}),
}
FORBIDDEN_OBJECT_FIELDS = frozenset(
    {
        "answer",
        "gold",
        "problem",
        "prompt",
        "response",
        "raw_prompt",
        "raw_response",
        "status",
        "evidence",
        "final_response",
    }
)
CLAIM_REQUIRED = frozenset({"v", "kind", "id", "type", "scope"})
VERIFY_REQUIRED = frozenset({"v", "kind", "id", "claim_id", "adapter"})
CLAIM_OPTIONAL = frozenset(
    {
        "left",
        "relation",
        "right",
        "assumptions",
        "variable",
        "predicate",
        "values",
        "branch",
    }
)
VERIFY_OPTIONAL = frozenset({"branch"})


class ClaimDslError(ValueError):
    """Fail-closed parse or binding error with a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ClaimObject:
    id: str
    type: str
    scope: str
    branch: str = ""
    left: str = ""
    relation: str = ""
    right: str = ""
    variable: str = ""
    predicate: str = ""
    values: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerifyRequest:
    id: str
    claim_id: str
    adapter: str
    branch: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    claim_id: str
    adapter: str
    status: str
    scope: str
    assumptions: tuple[str, ...] = ()
    result: str = ""
    witness: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = "evidence"
        payload["v"] = DSL_VERSION
        return payload


@dataclass
class ClaimLedger:
    """Host-owned registry for one solve.  The model never mutates it directly."""

    claims: dict[str, ClaimObject] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)

    def add_claim(self, claim: ClaimObject) -> None:
        if claim.id in self.claims or claim.id in self.evidence:
            raise ClaimDslError("duplicate_id")
        self.claims[claim.id] = claim

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.id in self.claims or record.id in self.evidence:
            raise ClaimDslError("duplicate_id")
        if record.claim_id not in self.claims:
            raise ClaimDslError("unknown_claim")
        self.evidence[record.id] = record

    def bind_synthesis(self, claim_id: str, evidence_id: str) -> str:
        """Return SUPPORTED, REFUTED or UNRESOLVED.  UNKNOWN never upgrades."""

        claim = self.claims.get(claim_id)
        record = self.evidence.get(evidence_id)
        if claim is None or record is None:
            return "UNRESOLVED"
        if record.claim_id != claim.id:
            return "UNRESOLVED"
        if record.status == "EXACT":
            return "SUPPORTED"
        if record.status == "REFUTED":
            return "REFUTED"
        return "UNRESOLVED"


def _load_object(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text or len(text) > MAX_OBJECT_CHARS:
            raise ClaimDslError("object_too_large" if text else "empty_object")
        if "\n" in text.strip():
            # Nested/pretty JSON is rejected: the protocol is one compact object.
            raise ClaimDslError("multiline_object")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ClaimDslError("json_invalid") from exc
    else:
        raise ClaimDslError("object_type")
    if not isinstance(payload, dict):
        raise ClaimDslError("object_type")
    keys = {str(key) for key in payload}
    if keys & FORBIDDEN_OBJECT_FIELDS:
        raise ClaimDslError("forbidden_field")
    return payload


def _bounded_text(value: Any, *, code: str, limit: int = MAX_EXPRESSION_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimDslError(code)
    text = value.strip()
    if len(text) > limit or "\x00" in text:
        raise ClaimDslError(code)
    return text


def _bounded_id(value: Any, *, code: str = "id_invalid") -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise ClaimDslError(code)
    return text


def parse_claim(raw: str | Mapping[str, Any], *, branch: str = "") -> ClaimObject:
    payload = _load_object(raw)
    keys = {str(key) for key in payload}
    if keys - CLAIM_REQUIRED - CLAIM_OPTIONAL:
        raise ClaimDslError("unknown_field")
    if CLAIM_REQUIRED - keys:
        raise ClaimDslError("missing_field")
    if payload.get("v") != DSL_VERSION:
        raise ClaimDslError("version_invalid")
    if payload.get("kind") != "claim":
        raise ClaimDslError("kind_invalid")
    claim_type = str(payload.get("type") or "")
    if claim_type not in ALLOWED_CLAIM_TYPES:
        raise ClaimDslError("type_invalid")
    scope = str(payload.get("scope") or "")
    if scope in FORBIDDEN_SCOPES or scope not in ALLOWED_SCOPES:
        raise ClaimDslError("scope_invalid")
    if scope not in CLAIM_TYPE_TO_SCOPE[claim_type]:
        raise ClaimDslError("scope_mismatch")
    branch_text = str(payload.get("branch") or branch or "")
    if branch_text and not _BRANCH_RE.fullmatch(branch_text):
        raise ClaimDslError("branch_invalid")
    assumptions_raw = payload.get("assumptions", [])
    if assumptions_raw in (None, ""):
        assumptions_raw = []
    if not isinstance(assumptions_raw, list) or len(assumptions_raw) > MAX_ASSUMPTIONS:
        raise ClaimDslError("assumptions_invalid")
    assumptions = tuple(_bounded_text(item, code="assumptions_invalid", limit=160) for item in assumptions_raw)

    left = relation = right = variable = predicate = ""
    values: tuple[str, ...] = ()
    if claim_type == "relation":
        left = _bounded_text(payload.get("left"), code="expression_invalid")
        right = _bounded_text(payload.get("right"), code="expression_invalid")
        relation = str(payload.get("relation") or "")
        if relation not in ALLOWED_RELATIONS:
            raise ClaimDslError("relation_invalid")
        if scope == "symbolic_identity" and relation != "==":
            raise ClaimDslError("scope_mismatch")
    else:
        variable = _bounded_text(payload.get("variable"), code="variable_invalid", limit=32)
        if not re.fullmatch(r"^[A-Za-z][A-Za-z0-9_]{0,31}$", variable):
            raise ClaimDslError("variable_invalid")
        predicate = _bounded_text(payload.get("predicate"), code="expression_invalid")
        raw_values = payload.get("values", [])
        if not isinstance(raw_values, list) or not raw_values or len(raw_values) > MAX_VALUES:
            raise ClaimDslError("values_invalid")
        values = tuple(_bounded_text(item, code="values_invalid", limit=32) for item in raw_values)
    return ClaimObject(
        id=_bounded_id(payload.get("id")),
        type=claim_type,
        scope=scope,
        branch=branch_text,
        left=left,
        relation=relation,
        right=right,
        variable=variable,
        predicate=predicate,
        values=values,
        assumptions=assumptions,
    )


def parse_verify(raw: str | Mapping[str, Any], *, branch: str = "") -> VerifyRequest:
    payload = _load_object(raw)
    keys = {str(key) for key in payload}
    extra_expression_keys = {"left", "right", "relation", "predicate", "values", "variable", "assumptions", "scope"}
    if keys & extra_expression_keys:
        raise ClaimDslError("verify_rewrites_claim")
    if keys - VERIFY_REQUIRED - VERIFY_OPTIONAL:
        raise ClaimDslError("unknown_field")
    if VERIFY_REQUIRED - keys:
        raise ClaimDslError("missing_field")
    if payload.get("v") != DSL_VERSION:
        raise ClaimDslError("version_invalid")
    if payload.get("kind") != "verify":
        raise ClaimDslError("kind_invalid")
    adapter = str(payload.get("adapter") or "")
    if adapter not in ALLOWED_ADAPTERS:
        raise ClaimDslError("adapter_invalid")
    branch_text = str(payload.get("branch") or branch or "")
    if branch_text and not _BRANCH_RE.fullmatch(branch_text):
        raise ClaimDslError("branch_invalid")
    return VerifyRequest(
        id=_bounded_id(payload.get("id")),
        claim_id=_bounded_id(payload.get("claim_id"), code="claim_id_invalid"),
        adapter=adapter,
        branch=branch_text,
    )


def bind_verify(request: VerifyRequest, ledger: ClaimLedger) -> ClaimObject:
    claim = ledger.claims.get(request.claim_id)
    if claim is None:
        raise ClaimDslError("unknown_claim")
    if request.branch and claim.branch and request.branch != claim.branch:
        raise ClaimDslError("cross_branch")
    expected_adapter = CLAIM_TYPE_TO_ADAPTER[claim.type]
    if request.adapter != expected_adapter:
        raise ClaimDslError("adapter_mismatch")
    return claim


def execute_verify(request: VerifyRequest, ledger: ClaimLedger) -> EvidenceRecord:
    claim = bind_verify(request, ledger)
    if request.id in ledger.claims or request.id in ledger.evidence:
        raise ClaimDslError("duplicate_id")
    result = _run_adapter(claim, request.adapter)
    if result.status not in {"EXACT", "REFUTED", "UNKNOWN"}:
        result_status = "UNKNOWN"
    else:
        result_status = result.status
    if claim.type == "counterexample_search" and result_status == "EXACT":
        result_status = "UNKNOWN"
    record = EvidenceRecord(
        id=request.id,
        claim_id=claim.id,
        adapter=request.adapter,
        status=result_status,
        scope=claim.scope,
        assumptions=claim.assumptions,
        result=str(result.result or "")[:240],
        witness=str(result.witness or "")[:160],
        error=str(result.error or "")[:160],
    )
    ledger.add_evidence(record)
    return record


def _run_adapter(claim: ClaimObject, adapter_name: str) -> VerificationResult:
    if adapter_name == "symbolic-constraint":
        return SymbolicConstraintAdapter().check_relation(
            claim.left,
            claim.relation,
            claim.right,
            claim_id=claim.id,
            assumptions=claim.assumptions,
        )
    values: list[Any] = []
    for item in claim.values:
        if re.fullmatch(r"[+-]?\d+(?:/\d+)?", item):
            values.append(item)
        else:
            return VerificationResult(
                status="UNKNOWN",
                adapter=adapter_name,
                claim_id=claim.id,
                evidence="unsupported",
                error="domain_value",
            )
    if adapter_name == "finite-domain":
        return FiniteDomainAdapter().check_all(claim.variable, claim.predicate, values, claim_id=claim.id)
    return CounterexampleAdapter().find(claim.variable, claim.predicate, values, claim_id=claim.id)


__all__ = [
    "ALLOWED_ADAPTERS",
    "ALLOWED_SCOPES",
    "ClaimDslError",
    "ClaimLedger",
    "ClaimObject",
    "EvidenceRecord",
    "VerifyRequest",
    "bind_verify",
    "execute_verify",
    "parse_claim",
    "parse_verify",
]
