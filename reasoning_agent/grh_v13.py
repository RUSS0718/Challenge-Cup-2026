"""Opt-in GRH v1.3 host pipeline for candidate recovery and telemetry.

The pipeline is deliberately independent from the v1.1 submission facade.  It
can replay an existing response, preserve a safe incumbent, or validate one
bounded finalizer response; it never performs a model call by itself.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.answer_contract import Candidate, infer_task_contract
from reasoning_agent.candidate_canonicalizer import parse_response
from reasoning_agent.finalizer import FinalizerInput, accept_finalizer_response
from reasoning_agent.invalid_recovery import RecoveryAction, decide_recovery
from reasoning_agent.verification_gates import verify_candidate


def recover_response(problem: str, response: str, row: dict[str, Any] | None = None, *, finalizer_response: str | None = None) -> dict[str, Any]:
    """Recover only evidence already present in a solver response.

    ``finalizer_response`` is optional and must be supplied by an external,
    pre-budgeted caller.  It is accepted only when it repeats the incumbent
    canonical value exactly under the task contract.
    """
    metadata = dict(row or {})
    contract = infer_task_contract(problem)
    parsed = parse_response(response, contract)
    candidate: Candidate | None = parsed.candidates[0] if parsed.complete else None
    decision = decide_recovery(metadata, candidate)
    accepted = candidate if decision.action != RecoveryAction.UNKNOWN else None
    verification = verify_candidate(candidate, contract).as_dict() if candidate else {"status": "unknown", "check": "none", "reason": "no_candidate"}
    if decision.action == RecoveryAction.FINALIZER and candidate and finalizer_response is not None:
        finalized = accept_finalizer_response(finalizer_response, FinalizerInput(contract, candidate, verification["reason"]))
        # A rejected finalizer cannot erase a structurally safe incumbent.
        accepted = finalized or candidate
    return {
        "contract": contract.as_dict(),
        "candidate": accepted.as_dict() if accepted else None,
        "parsed_candidate_count": len(parsed.candidates),
        "parser_source": parsed.parser_source,
        "parser_rejection": parsed.rejection_reason,
        "recovery": decision.as_dict(),
        "verification": verification,
        "finalizer_used": bool(finalizer_response is not None and decision.action == RecoveryAction.FINALIZER),
        "model_calls": 0,
    }


__all__ = ["recover_response"]
