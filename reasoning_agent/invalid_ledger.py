"""Build compact, auditable invalid ledgers from persisted answer artifacts."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from reasoning_agent.answer_contract import TaskContract
from reasoning_agent.candidate_canonicalizer import candidate_from_mapping, parse_response
from reasoning_agent.invalid_recovery import decide_recovery


def raw_response_hash(response: str) -> str:
    """Hash raw response bytes without persisting chain-of-thought content."""
    return sha256(str(response or "").encode("utf-8")).hexdigest()


def ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one saved answer row into the schema required by the plan."""
    contract = TaskContract()
    parsed = parse_response(str(row.get("final_response", "")), contract)
    candidate = parsed.candidates[0] if parsed.complete else None
    if candidate is None:
        trace = row.get("trace", [])
        summary = next((item for item in trace if item.get("stage") == "arm_v2_summary"), {}) if isinstance(trace, list) else {}
        mapping = summary.get("safe_candidate") or summary.get("primary_candidate")
        if isinstance(mapping, dict) and mapping.get("value"):
            candidate = candidate_from_mapping(mapping, contract)
    decision = decide_recovery(row, candidate)
    old = str(row.get("verdict", row.get("outcome", "unknown")))
    is_invalid_pool = old in {"invalid", "unknown", "error"}
    return {
        "run_id": str(row.get("run_id", "")),
        "question_id": str(row.get("item_id", row.get("idx", ""))),
        "old_verdict": old,
        "raw_response_hash": raw_response_hash(str(row.get("final_response", ""))),
        "finish_reason": (row.get("finish_reasons") or [None])[-1],
        "timeout": bool(row.get("timeout", False)),
        "answer_marker_hit": parsed.parser_source not in {"none", "terminal_line"},
        "candidate_count": int(row.get("candidate_count", len(parsed.candidates)) or 0),
        "candidate_source": candidate.source if candidate else "none",
        "candidate_completeness": candidate.completeness.value if candidate else "unknown",
        "candidate_type": candidate.answer_type.value if candidate else "unknown",
        "canonicalization_status": "accepted" if candidate and candidate.accepted else parsed.rejection_reason or "unknown",
        "deterministic_check": candidate.verification.value if candidate else "unknown",
        "failure_class": decision.failure_class.value if is_invalid_pool else "UNKNOWN",
        "salvage_eligible": bool(is_invalid_pool and decision.action.value != "unknown"),
        "proposed_action": decision.action.value if is_invalid_pool else "unknown",
        "new_verdict": "unknown",
        "transition": f"{old} → unknown",
        "reviewer_note": decision.reason if is_invalid_pool else "regression_protection_row",
        "evidence_source": decision.evidence_source if is_invalid_pool else "none",
    }


__all__ = ["ledger_row", "raw_response_hash"]
