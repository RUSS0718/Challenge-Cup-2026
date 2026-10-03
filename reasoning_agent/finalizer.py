"""One-shot OFF finalizer contract that cannot invent a mathematical answer."""

from __future__ import annotations

from dataclasses import dataclass

from reasoning_agent.answer_contract import Candidate, TaskContract
from reasoning_agent.candidate_canonicalizer import parse_response


@dataclass(frozen=True)
class FinalizerInput:
    """Only the already extracted candidate and validation summary are exposed."""

    contract: TaskContract
    candidate: Candidate
    validation_summary: str


def build_finalizer_prompt(data: FinalizerInput) -> str:
    """Build a bounded prompt that forbids re-solving and new candidates."""
    return (
        "Format the existing candidate only. Do not solve, recompute, add, or change its value.\n"
        f"Task contract: {data.contract.as_dict()}\n"
        f"Canonical value: {data.candidate.canonical_value or data.candidate.value}\n"
        f"Validation summary: {data.validation_summary}\n"
        "Return exactly FINAL_CANDIDATE: <the same canonical value>, or UNKNOWN."
    )


def accept_finalizer_response(response: str, data: FinalizerInput) -> Candidate | None:
    """Accept only a response equivalent to the incumbent candidate."""
    if str(response or "").strip().upper() == "UNKNOWN":
        return None
    parsed = parse_response(response, data.contract)
    if not parsed.complete:
        return None
    candidate = parsed.candidates[0]
    expected = data.candidate.canonical_value or data.candidate.value
    if candidate.canonical_value != expected:
        return None
    return data.candidate


__all__ = ["FinalizerInput", "accept_finalizer_response", "build_finalizer_prompt"]
