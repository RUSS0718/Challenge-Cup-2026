"""Concrete Claim DSL executor.  Imported only by the opt-in factory."""

from __future__ import annotations

import re
from typing import Any

from ..fesf_memory import SolveMemory
from .claim_dsl import (
    ClaimDslError,
    ClaimLedger,
    ClaimObject,
    execute_verify,
    parse_claim,
    parse_verify,
)


_CLAIM_LINE_RE = re.compile(r"(?im)^[ \t]*CLAIM_DSL[ \t]*[:：][ \t]*(.*?)\s*$")
_VERIFY_LINE_RE = re.compile(r"(?im)^[ \t]*VERIFY_DSL[ \t]*[:：][ \t]*(.*?)\s*$")


def _claim_content(claim: ClaimObject) -> str:
    if claim.type == "relation":
        return f"{claim.left}{claim.relation}{claim.right}"
    return f"{claim.variable}:{claim.predicate}"


def _event(**fields: Any) -> dict[str, Any]:
    return {
        "stage": "tool_claim_dsl",
        "status": str(fields.get("status") or "UNKNOWN"),
        "evidence_id": str(fields.get("evidence_id") or ""),
        "claim_id": str(fields.get("claim_id") or "UNKNOWN"),
        "error": str(fields.get("error") or "none"),
        "execution_status": str(fields.get("execution_status") or "unknown"),
        "claim_known": bool(fields.get("claim_known")),
        "binding_ok": bool(fields.get("binding_ok")),
        "tool_request_valid": bool(fields.get("tool_request_valid")),
    }


class HostClaimExecutor:
    """One-solve executor: a fresh ledger per ``verify`` call."""

    def verify(self, branch: str, packet_text: str, memory: SolveMemory) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        ledger = ClaimLedger()
        branch_text = str(branch or "").upper()
        for line in (packet_text or "").splitlines():
            claim_match = _CLAIM_LINE_RE.match(line)
            if claim_match:
                events.append(self._ingest_claim(claim_match.group(1), branch_text, ledger, memory))
                continue
            verify_match = _VERIFY_LINE_RE.match(line)
            if verify_match:
                events.append(self._ingest_verify(verify_match.group(1), branch_text, ledger, memory))
        return events

    def _ingest_claim(
        self,
        raw: str,
        branch: str,
        ledger: ClaimLedger,
        memory: SolveMemory,
    ) -> dict[str, Any]:
        try:
            claim = parse_claim(raw, branch=branch)
            ledger.add_claim(claim)
        except ClaimDslError as exc:
            return _event(status="UNKNOWN", error=exc.code, execution_status="rejected")
        content = _claim_content(claim)
        if not memory.add_claim(claim.id, content, claim.branch or branch):
            return _event(
                status="UNKNOWN",
                claim_id="CLAIM",
                error="duplicate_or_invalid_claim",
                execution_status="rejected",
            )
        return _event(
            status="ok",
            claim_id="CLAIM",
            execution_status="ok",
            claim_known=True,
            tool_request_valid=True,
        )

    def _ingest_verify(
        self,
        raw: str,
        branch: str,
        ledger: ClaimLedger,
        memory: SolveMemory,
    ) -> dict[str, Any]:
        try:
            request = parse_verify(raw, branch=branch)
            record = execute_verify(request, ledger)
        except ClaimDslError as exc:
            return _event(status="UNKNOWN", error=exc.code, execution_status="rejected")
        known = any(item.id == record.claim_id for item in memory.claims)
        if not known:
            return _event(
                status="UNKNOWN",
                evidence_id=record.id,
                claim_id="UNKNOWN",
                error="unknown_claim",
                execution_status="rejected",
            )
        written = memory.add_evidence(
            record.id,
            record.adapter,
            record.status,
            record.scope,
            record.result,
            record.assumptions,
            record.claim_id,
        )
        return _event(
            status=record.status,
            evidence_id=record.id,
            claim_id="CLAIM",
            error=record.error or "none",
            execution_status="ok" if written else "rejected",
            claim_known=True,
            binding_ok=written,
            tool_request_valid=written,
        )


def build_fesf_claim_executor() -> HostClaimExecutor:
    return HostClaimExecutor()


__all__ = ["HostClaimExecutor", "build_fesf_claim_executor"]
