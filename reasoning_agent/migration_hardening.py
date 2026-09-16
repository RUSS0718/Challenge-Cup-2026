"""Small, opt-in host contracts for Issue #19.

This module is deliberately independent from the default solver.  It provides
solve-local bookkeeping and bounded adapters; it is not a second orchestrator.
Only compact, sanitized summaries are exposed by ledger traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction
import hashlib
import math
from pathlib import Path, PurePath, PureWindowsPath
import re
import time
from typing import Any, Callable, Iterable, Mapping


MAX_LOGICAL_CALLS = 5
MAX_TOTAL_TOKENS = 16_384
MAX_WALL_SECONDS = 1_200.0
MAX_SUMMARY_CHARS = 240
MAX_CANDIDATE_CHARS = 256
MAX_RESPONSE_CHARS = 24_000
MAX_TRACE_ITEMS = 32
MAX_SET_ITEMS = 32
MAX_FRACTION_ABS = 10**12


STATE_START = "start"
STATE_ATTEMPT = "attempt"
STATE_CANDIDATE = "candidate"
STATE_VERIFIED = "verified"
STATE_CONFLICT = "conflict"
STATE_REPAIR = "repair"
STATE_CONTINUATION = "continuation"
STATE_SELECTED = "selected"
STATE_ABSTAINED = "abstained"
STATE_FINALIZED = "finalized"
STATES = frozenset(
    {
        STATE_START,
        STATE_ATTEMPT,
        STATE_CANDIDATE,
        STATE_VERIFIED,
        STATE_CONFLICT,
        STATE_REPAIR,
        STATE_CONTINUATION,
        STATE_SELECTED,
        STATE_ABSTAINED,
        STATE_FINALIZED,
    }
)
HARDENING_STATES = STATES
STATE_TRANSITIONS = {
    STATE_START: frozenset({STATE_START, STATE_ATTEMPT, STATE_CANDIDATE, STATE_SELECTED, STATE_FINALIZED, STATE_ABSTAINED}),
    STATE_ATTEMPT: frozenset({STATE_ATTEMPT, STATE_CANDIDATE, STATE_CONFLICT, STATE_CONTINUATION, STATE_REPAIR, STATE_ABSTAINED}),
    STATE_CANDIDATE: frozenset({STATE_ATTEMPT, STATE_CANDIDATE, STATE_VERIFIED, STATE_CONFLICT, STATE_REPAIR, STATE_CONTINUATION, STATE_SELECTED, STATE_ABSTAINED, STATE_FINALIZED}),
    STATE_VERIFIED: frozenset({STATE_VERIFIED, STATE_SELECTED, STATE_REPAIR, STATE_FINALIZED}),
    STATE_CONFLICT: frozenset({STATE_ATTEMPT, STATE_CANDIDATE, STATE_VERIFIED, STATE_REPAIR, STATE_SELECTED, STATE_ABSTAINED}),
    STATE_REPAIR: frozenset({STATE_REPAIR, STATE_CANDIDATE, STATE_VERIFIED, STATE_SELECTED, STATE_ABSTAINED}),
    STATE_CONTINUATION: frozenset({STATE_CANDIDATE, STATE_VERIFIED, STATE_SELECTED, STATE_ABSTAINED}),
    STATE_SELECTED: frozenset({STATE_SELECTED, STATE_FINALIZED}),
    STATE_ABSTAINED: frozenset({STATE_FINALIZED}),
    STATE_FINALIZED: frozenset(),
}


class EvidenceStatus(str, Enum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    INCONCLUSIVE = "inconclusive"


EVIDENCE_SUPPORT = EvidenceStatus.SUPPORT.value
EVIDENCE_CONTRADICT = EvidenceStatus.CONTRADICT.value
EVIDENCE_INCONCLUSIVE = EvidenceStatus.INCONCLUSIVE.value
EVIDENCE_STATUSES = frozenset(
    {EVIDENCE_SUPPORT, EVIDENCE_CONTRADICT, EVIDENCE_INCONCLUSIVE}
)
SUPPORT = EVIDENCE_SUPPORT
CONTRADICT = EVIDENCE_CONTRADICT
INCONCLUSIVE = EVIDENCE_INCONCLUSIVE


PLAYOFF_A = "A"
PLAYOFF_B = "B"
PLAYOFF_BOTH = "BOTH"
PLAYOFF_NEITHER = "NEITHER"
PLAYOFF_INCONCLUSIVE = "INCONCLUSIVE"
PLAYOFF_DECISIONS = frozenset(
    {PLAYOFF_A, PLAYOFF_B, PLAYOFF_BOTH, PLAYOFF_NEITHER, PLAYOFF_INCONCLUSIVE}
)


PREFILL_PURPOSES = frozenset({"classification", "selection", "evidence_state"})
LOW_ENTROPY_PURPOSES = PREFILL_PURPOSES


_SENSITIVE_TEXT = re.compile(
    r"(?:raw[\s_-]*(?:prompt|response)|"
    r"(?<![A-Za-z])(?:prompt|response|secret|gold)(?![A-Za-z])|"
    r"credential|api[\s_-]*key|access[\s_-]*token|password)",
    re.IGNORECASE,
)
_ASSET_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_CHOICE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_NUMERIC = re.compile(
    r"[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:/[+-]?(?:\d+(?:\.\d*)?|\.\d+))?)"
)


def _clip(value: Any, limit: int = MAX_SUMMARY_CHARS) -> str:
    if value is None:
        text = ""
    else:
        text = str(value)
    text = text.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _summary(value: Any, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = _clip(value, limit)
    return "[redacted]" if _SENSITIVE_TEXT.search(text) else text


def _error_category(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    if "timeout" in name or "timeout" in detail or "deadline" in detail:
        return "timeout"
    if "typeerror" in name:
        return "type_error"
    return "client_error"


def _json_safe(value: Any, *, limit: int = MAX_CANDIDATE_CHARS) -> Any:
    """Return bounded JSON-compatible data without retaining sensitive fields."""

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _summary(value, limit)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:16]:
            key_text = _clip(key, 64)
            if _SENSITIVE_TEXT.search(key_text):
                continue
            result[key_text] = _json_safe(item, limit=limit)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, limit=limit) for item in list(value)[:MAX_SET_ITEMS]]
    if isinstance(value, (set, frozenset)):
        items = [_json_safe(item, limit=limit) for item in list(value)[:MAX_SET_ITEMS]]
        return sorted(items, key=repr)
    return _summary("<" + type(value).__name__ + ">", limit)


def _bounded_value(value: Any) -> Any:
    """Keep a candidate value bounded while retaining its basic type."""

    if value is None or isinstance(value, (bool, int, Fraction)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _clip(value, MAX_CANDIDATE_CHARS)
    if isinstance(value, Mapping):
        return {
            _clip(key, 64): _bounded_value(item)
            for key, item in list(value.items())[:16]
            if not _SENSITIVE_TEXT.search(_clip(key, 64))
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_value(item) for item in list(value)[:MAX_SET_ITEMS]]
    if isinstance(value, (set, frozenset)):
        return {_bounded_value(item) for item in list(value)[:MAX_SET_ITEMS]}
    return _clip("<" + type(value).__name__ + ">", MAX_CANDIDATE_CHARS)


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    value: Any
    source: str = ""
    extraction_status: str = ""
    answer_type: str = "unknown"
    verification_status: str = "unverified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": _clip(self.candidate_id, 64),
            "value": _json_safe(self.value),
            "source": _summary(self.source, 64),
            "extraction_status": _summary(self.extraction_status, 64),
            "answer_type": _summary(self.answer_type, 64),
            "verification_status": _summary(self.verification_status, 64),
        }


Candidate = CandidateRecord


@dataclass(frozen=True)
class CallReservation:
    call_number: int
    stage: str
    requested_tokens: int
    started_at: float


@dataclass(frozen=True)
class BudgetCallRecord:
    call_number: int
    stage: str
    requested_tokens: int
    actual_tokens: int | None
    finish: str
    finished_at: float
    duration: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        record = {
            "call_number": self.call_number,
            "stage": _summary(self.stage, 64),
            "requested_tokens": self.requested_tokens,
            "actual_tokens": self.actual_tokens,
            "finish": _clip(self.finish, 32),
            "finished_at": self.finished_at,
            "duration": self.duration,
            "error": _summary(self.error, 64) if self.error else None,
        }
        record.update(
            {
                "completion_tokens": self.actual_tokens,
                "finish_reason": self.finish,
                "duration_ms": int(self.duration * 1000),
                "status": "error" if self.error else "ok",
                "error_category": _summary(self.error, 64) if self.error else None,
            }
        )
        return record


CallRecord = BudgetCallRecord


class HardeningBudget:
    """One admission gate for logical calls, requested tokens, and wall time."""

    def __init__(
        self,
        max_calls: int = MAX_LOGICAL_CALLS,
        total_tokens: int = MAX_TOTAL_TOKENS,
        max_wall_seconds: float = MAX_WALL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_logical_calls: int | None = None,
        max_requested_tokens: int | None = None,
        wall_deadline: float | None = None,
    ) -> None:
        if max_logical_calls is not None:
            max_calls = max_logical_calls
        if max_requested_tokens is not None:
            total_tokens = max_requested_tokens
        if isinstance(max_calls, bool) or int(max_calls) < 1:
            raise ValueError("invalid_budget")
        if isinstance(total_tokens, bool) or int(total_tokens) < 1:
            raise ValueError("invalid_budget")
        if not math.isfinite(float(max_wall_seconds)) or float(max_wall_seconds) <= 0:
            raise ValueError("invalid_budget")
        if wall_deadline is not None and not math.isfinite(float(wall_deadline)):
            raise ValueError("invalid_budget")
        self.max_calls = min(MAX_LOGICAL_CALLS, int(max_calls))
        self.total_tokens = min(MAX_TOTAL_TOKENS, int(total_tokens))
        self.max_logical_calls = self.max_calls
        self.max_requested_tokens = self.total_tokens
        self.clock = clock
        self.started_at = float(self.clock())
        self.max_wall_seconds = min(MAX_WALL_SECONDS, float(max_wall_seconds))
        self.wall_deadline = (
            float(wall_deadline)
            if wall_deadline is not None
            else self.started_at + self.max_wall_seconds
        )
        self.calls_used = 0
        self.requested_tokens = 0
        self.records: list[dict[str, Any]] = []
        self.refusals: list[dict[str, Any]] = []
        self._pending: dict[int, CallReservation] = {}

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, float(self.clock()) - self.started_at)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.wall_deadline - float(self.clock()))

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.total_tokens - self.requested_tokens)

    @property
    def exhausted(self) -> bool:
        return any(
            value <= 0
            for value in (
                self.max_calls - self.calls_used,
                self.total_tokens - self.requested_tokens,
                self.remaining_seconds,
            )
        )

    def remaining(self) -> dict[str, Any]:
        calls = max(0, self.max_calls - self.calls_used)
        tokens = self.remaining_tokens
        wall = self.remaining_seconds
        return {
            "logical_calls": calls,
            "requested_tokens": tokens,
            "wall_seconds": wall,
            "calls": calls,
            "tokens": tokens,
            "max_logical_calls": self.max_calls,
            "max_requested_tokens": self.total_tokens,
            "wall_deadline": self.wall_deadline,
        }

    def admit(
        self,
        *args: Any,
        stage: str = "call",
        requested_tokens: int | None = None,
    ) -> CallReservation | None:
        """Reserve one logical call; no retry or implicit second admission exists."""

        if len(args) == 2:
            stage, requested_tokens = args
        elif len(args) == 1:
            if isinstance(args[0], str) and requested_tokens is not None:
                stage = args[0]
            elif requested_tokens is None:
                requested_tokens = args[0]
            else:
                raise TypeError("admit_arguments")
        elif args:
            raise TypeError("admit_arguments")

        valid_tokens = isinstance(requested_tokens, int) and not isinstance(requested_tokens, bool)
        requested = int(requested_tokens) if valid_tokens else 0
        now = float(self.clock())
        reasons: list[str] = []
        if not valid_tokens or requested <= 0:
            reasons.append("invalid_requested_tokens")
        if self.calls_used >= self.max_calls:
            reasons.append("call_budget_exhausted")
        if self.requested_tokens + requested > self.total_tokens:
            reasons.append("token_budget_exhausted")
        if now >= self.wall_deadline:
            reasons.append("wall_clock_exhausted")
        if reasons:
            self.refusals.append(
                {
                    "stage": _clip(stage, 64),
                    "requested_tokens": max(0, requested),
                    "reason": "+".join(reasons),
                }
            )
            return None

        reservation = CallReservation(
            call_number=self.calls_used + 1,
            stage=_clip(stage, 64),
            requested_tokens=requested,
            started_at=now,
        )
        self.calls_used += 1
        self.requested_tokens += requested
        self._pending[reservation.call_number] = reservation
        return reservation

    reserve = admit

    def finish(
        self,
        reservation: CallReservation | int | None = None,
        *,
        actual_tokens: int | None = None,
        completion_tokens: int | None = None,
        finish: str | None = None,
        finish_reason: str | None = None,
        finished_at: float | None = None,
        duration: float | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
        error_category: str | None = None,
    ) -> dict[str, Any]:
        if reservation is None:
            if not self._pending:
                raise ValueError("unknown_reservation")
            reservation = next(iter(self._pending.values()))
        call_number = reservation if isinstance(reservation, int) else reservation.call_number
        stored = self._pending.get(call_number)
        if stored is None:
            raise ValueError("unknown_reservation")
        if isinstance(reservation, CallReservation) and reservation != stored:
            raise ValueError("unknown_reservation")

        finished = float(self.clock()) if finished_at is None else float(finished_at)
        if actual_tokens is None:
            actual_tokens = completion_tokens
        if actual_tokens is not None and (
            not isinstance(actual_tokens, int) or isinstance(actual_tokens, bool) or actual_tokens < 0
        ):
            actual_tokens = None
        if duration is None:
            duration = duration_ms / 1000.0 if duration_ms is not None else finished - stored.started_at
        duration = max(0.0, float(duration))
        error_text = _clip(error if error is not None else error_category, 64) or None
        finish_text = finish if finish is not None else finish_reason
        if not finish_text:
            if error_text:
                finish_text = "timeout" if _error_category(ValueError(error_text)) == "timeout" else "error"
            elif finished >= self.wall_deadline:
                finish_text = "timeout"
                error_text = error_text or "wall_deadline"
            else:
                finish_text = "completed"
        finish_text = _clip(finish_text, 32)
        if finished >= self.wall_deadline and finish_text == "completed":
            finish_text = "timeout"
            error_text = error_text or "wall_deadline"

        record = BudgetCallRecord(
            call_number=stored.call_number,
            stage=stored.stage,
            requested_tokens=stored.requested_tokens,
            actual_tokens=actual_tokens,
            finish=finish_text,
            finished_at=finished,
            duration=duration,
            error=error_text,
        ).as_dict()
        self.records.append(record)
        del self._pending[call_number]
        return dict(record)

    @property
    def call_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self.records)

    def summary(self) -> dict[str, Any]:
        remaining = self.remaining()
        actual = [
            record["actual_tokens"]
            for record in self.records
            if isinstance(record.get("actual_tokens"), int)
        ]
        return {
            "calls": self.calls_used,
            "call_limit": self.max_calls,
            "requested_tokens": self.requested_tokens,
            "token_limit": self.total_tokens,
            "remaining": remaining,
            "remaining_requested_tokens": remaining["requested_tokens"],
            "started_at": self.started_at,
            "wall_deadline": self.wall_deadline,
            "elapsed_ms": int(self.elapsed_seconds * 1000),
            "remaining_ms": int(remaining["wall_seconds"] * 1000),
            "actual_completion_tokens": sum(actual) if actual else None,
            "actual_token_records": len(actual),
            "records": sorted((dict(record) for record in self.records), key=lambda record: record.get("call_number", 0)),
            "pending_calls": sorted(self._pending),
            "refusals": [dict(refusal) for refusal in self.refusals],
        }


class HardeningLedger:
    """Bounded state, candidate, evidence, audit, and call records for one solve."""

    def __init__(self) -> None:
        self.state = STATE_START
        self.states: list[dict[str, str]] = []
        self.candidates: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.audit_hints: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.playoffs: list[dict[str, Any]] = []

    def transition(self, state: str, *, reason: str = "") -> None:
        if state not in STATES:
            raise ValueError("invalid_state")
        if state not in STATE_TRANSITIONS[self.state]:
            raise ValueError("invalid_state_transition")
        self.state = state
        if len(self.states) < MAX_TRACE_ITEMS:
            event = {"state": state}
            if reason:
                event["reason"] = _summary(reason)
            self.states.append(event)

    def add_candidate(
        self,
        candidate_id: str,
        value: Any,
        *,
        source: str = "",
        extraction_status: str = "",
        answer_type: str = "unknown",
        verification_status: str = "unverified",
    ) -> CandidateRecord | None:
        candidate_id = _clip(candidate_id, 64)
        if not candidate_id:
            return None
        record = CandidateRecord(
            candidate_id=candidate_id,
            value=_bounded_value(value),
            source=_clip(source, 64),
            extraction_status=_clip(extraction_status, 64),
            answer_type=_clip(answer_type, 64),
            verification_status=_clip(verification_status, 64),
        )
        for index, item in enumerate(self.candidates):
            if item["candidate_id"] == candidate_id:
                self.candidates[index] = record.as_dict()
                return record
        if len(self.candidates) < MAX_TRACE_ITEMS:
            self.candidates.append(record.as_dict())
        return record

    def candidate(self, candidate_id: str) -> dict[str, Any] | None:
        return next(
            (dict(item) for item in self.candidates if item["candidate_id"] == candidate_id),
            None,
        )

    def add_conflict(
        self,
        candidates: Iterable[Mapping[str, Any] | CandidateRecord | str],
        *,
        summary: str = "",
    ) -> None:
        rows: list[Any] = []
        try:
            for candidate in candidates:
                rows.append(candidate)
                if len(rows) >= 2:
                    break
        except TypeError:
            rows = []
        ids: list[str] = []
        values: list[Any] = []
        for candidate in rows:
            if isinstance(candidate, str):
                stored = self.candidate(candidate) or {}
                candidate_id = candidate
                value = stored.get("value")
            elif isinstance(candidate, CandidateRecord):
                candidate_id = candidate.candidate_id
                value = candidate.value
            elif isinstance(candidate, Mapping):
                candidate_id = candidate.get("candidate_id", candidate.get("id", ""))
                value = candidate.get("value", candidate.get("normalized_value", ""))
            else:
                candidate_id = getattr(candidate, "candidate_id", getattr(candidate, "id", ""))
                value = getattr(candidate, "value", "")
            ids.append(_clip(candidate_id, 64))
            values.append(_json_safe(value))
        self.conflicts.append(
            {
                "candidate_ids": ids,
                "values": values,
                "summary": _summary(summary or "candidate_conflict"),
            }
        )

    @property
    def conflict_sides(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(item.get("candidate_ids", ())) for item in self.conflicts)

    def add_evidence(self, record: "EvidenceRecord") -> None:
        if len(self.evidence) < MAX_TRACE_ITEMS:
            self.evidence.append(record.as_dict())

    def add_playoff(self, result: "PlayoffResult") -> None:
        if not self.playoffs:
            self.playoffs.append(result.as_dict())

    def add_audit_hint(self, hint: str) -> None:
        if hint and len(self.audit_hints) < 8:
            self.audit_hints.append(_summary(hint))

    def add_call(self, record: Mapping[str, Any] | BudgetCallRecord) -> None:
        if len(self.calls) >= MAX_TRACE_ITEMS:
            return
        payload = record.as_dict() if isinstance(record, BudgetCallRecord) else dict(record)
        allowed = {
            "call_number",
            "stage",
            "requested_tokens",
            "actual_tokens",
            "completion_tokens",
            "finish",
            "finish_reason",
            "finished_at",
            "duration",
            "duration_ms",
            "error",
            "error_category",
            "status",
            "prefill_status",
            "prefill_used",
            "prefill_fallback",
            "physical_calls",
        }
        clean: dict[str, Any] = {}
        for key in allowed:
            if key not in payload:
                continue
            value = payload[key]
            if key in {"stage"}:
                clean[key] = _summary(value, 64)
            elif key in {"finish", "finish_reason", "error", "error_category", "prefill_status"}:
                clean[key] = _summary(value, 64)
            elif key in {"requested_tokens", "actual_tokens", "completion_tokens", "duration_ms", "physical_calls"}:
                clean[key] = value if isinstance(value, int) and value >= 0 else None
            elif key in {"finished_at", "duration"}:
                clean[key] = float(value) if isinstance(value, (int, float)) else None
            elif key in {"call_number"}:
                clean[key] = value if isinstance(value, int) and value >= 0 else None
            else:
                clean[key] = bool(value) if key.startswith("prefill_") else _summary(value, 32)
        self.calls.append(clean)

    @property
    def call_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self.calls)

    def trace(
        self,
        *,
        budget: HardeningBudget | None = None,
        route: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        route_clean: dict[str, Any] = {}
        for key in (
            "name",
            "mode",
            "source",
            "status",
            "reason",
            "answer_shape",
            "reasoning_risk",
        ):
            if route and key in route:
                value = route[key]
                if isinstance(value, (str, int, bool, float)):
                    route_clean[key] = _summary(value, 64) if isinstance(value, str) else value
        return {
            "stage": "migration_hardening_ledger",
            "state": self.state,
            "states": [dict(item) for item in self.states[:MAX_TRACE_ITEMS]],
            "candidates": [
                {
                    key: (_json_safe(value) if key == "value" else value)
                    for key, value in item.items()
                    if key not in {"prompt", "response", "credential", "gold"}
                }
                for item in self.candidates[:MAX_TRACE_ITEMS]
            ],
            "conflicts": [_json_safe(item) for item in self.conflicts[:MAX_TRACE_ITEMS]],
            "evidence": [dict(item) for item in self.evidence[:MAX_TRACE_ITEMS]],
            "audit_hints": list(self.audit_hints[:8]),
            "calls": sorted(
                (dict(item) for item in self.calls[:MAX_TRACE_ITEMS]),
                key=lambda item: item.get("call_number", 0),
            ),
            "playoffs": [dict(item) for item in self.playoffs[:1]],
            "route": route_clean,
            "budget": budget.summary() if budget is not None else None,
        }

    as_dict = trace
    summary = trace


@dataclass(frozen=True)
class EvidenceRecord:
    candidate_id: str
    status: EvidenceStatus | str
    source: str
    summary: str = ""
    deterministic: bool = False
    error: str | None = None
    candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        status = self.status.value if isinstance(self.status, EvidenceStatus) else str(self.status)
        if status not in EVIDENCE_STATUSES:
            raise ValueError("invalid_evidence_status")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "candidate_id", _clip(self.candidate_id, 64))
        object.__setattr__(self, "source", _summary(self.source, 64))
        object.__setattr__(self, "summary", _summary(self.summary))
        object.__setattr__(self, "error", _summary(self.error, 64) if self.error else None)
        object.__setattr__(
            self,
            "candidate_ids",
            tuple(_clip(item, 64) for item in self.candidate_ids[:2]),
        )

    def as_dict(self) -> dict[str, Any]:
        ids = list(self.candidate_ids or ((self.candidate_id,) if self.candidate_id else ()))
        return {
            "candidate_id": self.candidate_id,
            "candidate_ids": ids,
            "status": self.status,
            "source": self.source,
            "summary": self.summary,
            "deterministic": bool(self.deterministic),
            "error": self.error,
        }


def adapt_evidence(
    result: Any,
    *,
    candidate_id: str = "",
    source: str = "",
    candidate_ids: Iterable[str] = (),
    trusted: bool = False,
) -> EvidenceRecord:
    """Accept only an explicit lower-case three-state, attributable result."""

    ids = tuple(_clip(item, 64) for item in list(candidate_ids)[:2])
    if isinstance(result, EvidenceRecord):
        if candidate_id and result.candidate_id and result.candidate_id != candidate_id:
            return EvidenceRecord(
                _clip(candidate_id, 64),
                EVIDENCE_INCONCLUSIVE,
                _clip(source, 64),
                "candidate_binding_failed",
                error="candidate_mismatch",
                candidate_ids=ids,
            )
        record_source = result.source or source
        record_id = candidate_id or result.candidate_id
        if result.status in EVIDENCE_STATUSES and record_source and (
            result.status == EVIDENCE_INCONCLUSIVE or result.deterministic or trusted
        ):
            return EvidenceRecord(
                record_id,
                result.status,
                record_source,
                result.summary or "provider_result",
                result.deterministic,
                result.error,
                ids or result.candidate_ids,
            )
        return EvidenceRecord(
            record_id,
            EVIDENCE_INCONCLUSIVE,
            record_source,
            "unattributed_result",
            error="evidence_unattributed",
            candidate_ids=ids,
        )

    if not isinstance(result, Mapping) and hasattr(result, "status") and hasattr(result, "adapter"):
        raw_status = str(getattr(result, "status", "")).strip().upper()
        status = {
            "EXACT": EVIDENCE_SUPPORT,
            "SUPPORT": EVIDENCE_SUPPORT,
            "REFUTED": EVIDENCE_CONTRADICT,
            "CONTRADICT": EVIDENCE_CONTRADICT,
            "UNKNOWN": EVIDENCE_INCONCLUSIVE,
            "INCONCLUSIVE": EVIDENCE_INCONCLUSIVE,
        }.get(raw_status)
        claim_id = str(getattr(result, "claim_id", "") or "")
        if candidate_id and claim_id and claim_id != candidate_id:
            return EvidenceRecord(
                _clip(candidate_id, 64),
                EVIDENCE_INCONCLUSIVE,
                _clip(source, 64),
                "candidate_binding_failed",
                error="candidate_mismatch",
                candidate_ids=ids,
            )
        if status is None:
            return EvidenceRecord(
                _clip(candidate_id, 64),
                EVIDENCE_INCONCLUSIVE,
                _clip(source, 64),
                "status_missing",
                error="status_missing",
                candidate_ids=ids,
            )
        safe_adapter = type(result).__module__.endswith("fesf_verifiers.adapters")
        return adapt_evidence(
            {
                "status": status,
                "source": str(getattr(result, "adapter", source) or source),
                "summary": getattr(result, "evidence", ""),
                "deterministic": bool(trusted or safe_adapter),
                "error": getattr(result, "error", ""),
            },
            candidate_id=candidate_id or claim_id,
            source=source,
            candidate_ids=ids,
            trusted=trusted or safe_adapter,
        )

    if not isinstance(result, Mapping):
        return EvidenceRecord(
            _clip(candidate_id, 64),
            EVIDENCE_INCONCLUSIVE,
            _clip(source, 64),
            "untyped_provider_result",
            error="status_missing",
            candidate_ids=ids,
        )

    result_candidate_id = result.get("candidate_id")
    if candidate_id and result_candidate_id and str(result_candidate_id) != candidate_id:
        return EvidenceRecord(
            _clip(candidate_id, 64),
            EVIDENCE_INCONCLUSIVE,
            _clip(source, 64),
            "candidate_binding_failed",
            error="candidate_mismatch",
            candidate_ids=ids,
        )

    raw_status = result.get("status")
    status = raw_status.value if isinstance(raw_status, EvidenceStatus) else raw_status
    if not isinstance(status, str) or status not in EVIDENCE_STATUSES:
        return EvidenceRecord(
            _clip(candidate_id, 64),
            EVIDENCE_INCONCLUSIVE,
            _clip(result.get("source") or result.get("provider") or source, 64),
            "status_missing",
            error="status_missing",
            candidate_ids=ids,
        )

    record_source = _clip(result.get("source") or result.get("provider") or source, 64)
    if status in {EVIDENCE_SUPPORT, EVIDENCE_CONTRADICT} and not record_source:
        return EvidenceRecord(
            _clip(candidate_id, 64),
            EVIDENCE_INCONCLUSIVE,
            "",
            "unattributed_result",
            error="evidence_unattributed",
            candidate_ids=ids,
        )
    is_trusted = bool(
        trusted
        or result.get("deterministic")
        or result.get("trusted")
        or result.get("computed")
        or result.get("verified")
    )
    if status in {EVIDENCE_SUPPORT, EVIDENCE_CONTRADICT} and not is_trusted:
        return EvidenceRecord(
            _clip(candidate_id, 64),
            EVIDENCE_INCONCLUSIVE,
            record_source,
            "evidence_untrusted",
            error="evidence_untrusted",
            candidate_ids=ids,
        )
    summary = result.get("summary") or result.get("evidence") or result.get("reason")
    return EvidenceRecord(
        _clip(candidate_id, 64),
        status,
        record_source,
        _summary(summary or "provider_result"),
        bool(result.get("deterministic", False)),
        _summary(result.get("error"), 64) if result.get("error") else None,
        ids,
    )


evidence_from_result = adapt_evidence


class EvidenceAdapter:
    """Run an injected typed provider without treating execution as truth."""

    def __init__(
        self,
        provider: Callable[[Any], Any] | None = None,
        *,
        name: str = "verifier",
        trusted: bool = False,
    ) -> None:
        self.provider = provider
        self.name = _clip(name, 64)
        self.trusted = bool(trusted)

    def evaluate(
        self,
        candidate_id: str,
        request: Any = None,
        *,
        source: str | None = None,
        candidate_ids: Iterable[str] = (),
    ) -> EvidenceRecord:
        record_source = _clip(source or self.name, 64)
        if self.provider is None:
            return EvidenceRecord(
                _clip(candidate_id, 64),
                EVIDENCE_INCONCLUSIVE,
                record_source,
                "verifier_unavailable",
                error="not_applicable",
                candidate_ids=tuple(candidate_ids)[:2],
            )
        try:
            result = self.provider(request)
        except Exception as exc:
            return EvidenceRecord(
                _clip(candidate_id, 64),
                EVIDENCE_INCONCLUSIVE,
                record_source,
                "verifier_error",
                error=_error_category(exc),
                candidate_ids=tuple(candidate_ids)[:2],
            )
        return adapt_evidence(
            result,
            candidate_id=candidate_id,
            source=record_source,
            candidate_ids=candidate_ids,
            trusted=self.trusted,
        )

    check = evaluate


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean_not_numeric")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non_finite")
        result = Fraction(str(value))
    elif isinstance(value, Decimal):
        result = Fraction(value)
    elif isinstance(value, str):
        compact = re.sub(r"\s+", "", value.strip()).replace("−", "-")
        if not _NUMERIC.fullmatch(compact):
            raise ValueError("numeric_expression")
        try:
            if "/" in compact:
                left, right = compact.split("/", 1)
                result = Fraction(Decimal(left)) / Fraction(Decimal(right))
            else:
                result = Fraction(Decimal(compact))
        except (InvalidOperation, ValueError, ZeroDivisionError) as exc:
            raise ValueError("numeric_invalid") from exc
    else:
        raise ValueError("not_numeric")
    if abs(result.numerator) > MAX_FRACTION_ABS or result.denominator > MAX_FRACTION_ABS:
        raise ValueError("numeric_limit")
    return result


def _normal_atom(value: Any) -> tuple[str, Any]:
    try:
        return "numeric", _fraction(value)
    except ValueError:
        pass
    if not isinstance(value, str):
        raise ValueError("choice_invalid")
    text = value.strip()
    if len(text) > MAX_CANDIDATE_CHARS or not text:
        raise ValueError("choice_invalid")
    if len(text) == 2 and text[0].upper() in "ABCD" and text[1] in ".)":
        text = text[:-1].strip()
    if not _CHOICE.fullmatch(text):
        raise ValueError("expression_or_choice_invalid")
    return "choice", text


def _normal_mechanical(value: Any) -> tuple[str, Any]:
    if isinstance(value, Mapping) and value.get("type") == "set" and "items" in value:
        value = value["items"]
    if isinstance(value, str):
        text = value.strip()
        if len(text) > MAX_CANDIDATE_CHARS:
            raise ValueError("candidate_too_large")
        try:
            return _normal_atom(text)
        except ValueError:
            if not (text.startswith("{") and text.endswith("}")):
                raise
            inner = text[1:-1].strip()
            parts = [] if not inner else inner.split(",")
            value = parts
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        if len(items) > MAX_SET_ITEMS:
            raise ValueError("set_too_large")
        normalized = [_normal_atom(item) for item in items]
        return "set", tuple(sorted(normalized, key=repr))
    return _normal_atom(value)


def _canonical(value: tuple[str, Any]) -> str:
    kind, normalized = value
    if kind == "numeric":
        return str(normalized)
    if kind == "choice":
        return str(normalized)
    return "{" + ",".join(str(item[1]) for item in normalized) + "}"


def _row_value(row: Mapping[str, Any] | CandidateRecord | Any) -> Any:
    if isinstance(row, CandidateRecord):
        return row.value
    if isinstance(row, Mapping):
        if "value" in row:
            return row["value"]
        return row.get("normalized_value")
    return getattr(row, "value", getattr(row, "normalized_value", None))


def _row_id(row: Mapping[str, Any] | CandidateRecord | Any) -> str:
    if isinstance(row, CandidateRecord):
        return _clip(row.candidate_id, 64)
    if isinstance(row, Mapping):
        return _clip(row.get("candidate_id", row.get("id", "")), 64)
    return _clip(getattr(row, "candidate_id", getattr(row, "id", "")), 64)


@dataclass(frozen=True)
class PlayoffResult:
    decision: str
    candidate_ids: tuple[str, ...] = ()
    summary: str = ""
    evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in PLAYOFF_DECISIONS:
            raise ValueError("invalid_playoff_decision")
        object.__setattr__(
            self,
            "candidate_ids",
            tuple(_clip(item, 64) for item in self.candidate_ids[:2]),
        )
        object.__setattr__(self, "summary", _summary(self.summary))

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "candidate_ids": list(self.candidate_ids),
            "summary": self.summary,
            "evidence": [_json_safe(item) for item in self.evidence[:2]],
        }


class DeterministicPlayoff:
    """At most one finite check over two existing, mechanically typed candidates."""

    def __init__(self, checker: Callable[[Mapping[str, Any]], Any] | None = None) -> None:
        self.checker = checker
        self._result: PlayoffResult | None = None

    @property
    def has_run(self) -> bool:
        return self._result is not None

    def run(
        self,
        candidates: Iterable[Mapping[str, Any] | CandidateRecord | Any] | HardeningLedger,
    ) -> PlayoffResult:
        if self._result is not None:
            return PlayoffResult(
                PLAYOFF_INCONCLUSIVE,
                self._result.candidate_ids,
                "playoff_already_run",
            )
        if isinstance(candidates, HardeningLedger):
            source = candidates.candidates
        elif isinstance(candidates, Mapping) and not (
            "candidate_id" in candidates or "id" in candidates or "value" in candidates
        ):
            source = (
                {"candidate_id": candidate_id, "value": value}
                for candidate_id, value in list(candidates.items())[:3]
            )
        else:
            source = candidates
        try:
            iterator = iter(source)
            rows = []
            for row in iterator:
                rows.append(row)
                if len(rows) > 2:
                    break
        except TypeError:
            return self._save(PlayoffResult(PLAYOFF_INCONCLUSIVE, (), "candidate_input_invalid"))
        if len(rows) != 2:
            return self._save(
                PlayoffResult(PLAYOFF_INCONCLUSIVE, (), "requires_exactly_two_existing_candidates")
            )
        ids = tuple(_row_id(row) for row in rows)
        if not ids[0] or not ids[1] or ids[0] == ids[1]:
            return self._save(PlayoffResult(PLAYOFF_INCONCLUSIVE, (), "candidate_ids_invalid"))
        try:
            normalized = [_normal_mechanical(_row_value(row)) for row in rows]
        except (TypeError, ValueError, OverflowError):
            return self._save(PlayoffResult(PLAYOFF_INCONCLUSIVE, ids, "not_mechanically_checkable"))
        if normalized[0][0] != normalized[1][0]:
            return self._save(PlayoffResult(PLAYOFF_INCONCLUSIVE, ids, "candidate_types_differ"))
        if normalized[0] == normalized[1]:
            return self._save(PlayoffResult(PLAYOFF_BOTH, ids, "equivalent_existing_candidates"))
        if self.checker is None:
            return self._save(PlayoffResult(PLAYOFF_INCONCLUSIVE, ids, "mechanical_checker_unavailable"))

        evidence: list[dict[str, Any]] = []
        statuses: list[str] = []
        adapter = EvidenceAdapter(self.checker, name="deterministic_playoff", trusted=True)
        for row, candidate_id, typed_value in zip(rows, ids, normalized):
            probe = {
                "candidate_id": candidate_id,
                "value": _json_safe(_row_value(row)),
                "normalized_value": _canonical(typed_value),
                "kind": typed_value[0],
            }
            record = adapter.evaluate(candidate_id, probe, source="deterministic_playoff")
            evidence.append(record.as_dict())
            statuses.append(record.status)
        if statuses == [EVIDENCE_SUPPORT, EVIDENCE_CONTRADICT]:
            decision = PLAYOFF_A
        elif statuses == [EVIDENCE_CONTRADICT, EVIDENCE_SUPPORT]:
            decision = PLAYOFF_B
        elif statuses == [EVIDENCE_SUPPORT, EVIDENCE_SUPPORT]:
            decision = PLAYOFF_BOTH
        elif statuses == [EVIDENCE_CONTRADICT, EVIDENCE_CONTRADICT]:
            decision = PLAYOFF_NEITHER
        else:
            decision = PLAYOFF_INCONCLUSIVE
        return self._save(
            PlayoffResult(decision, ids, "finite_candidate_check", tuple(evidence))
        )

    resolve = run

    def _save(self, result: PlayoffResult) -> PlayoffResult:
        self._result = result
        return result


@dataclass(frozen=True)
class ProcessAuditResult:
    status: str
    hints: tuple[str, ...] = ()
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": _clip(self.status, 32),
            "hints": [_summary(item) for item in self.hints[:3]],
            "summary": _summary(self.summary),
        }


class ProcessAuditParser:
    """Keep audit hints bounded; it never returns or replaces a candidate."""

    _STATUS = re.compile(
        r"(?im)^\s*(?:AUDIT|AUDIT_STATUS|STATUS)\s*[:：]\s*"
        r"(COMPLETE|REPAIR|INCONCLUSIVE)\s*$"
    )
    _HINT = re.compile(r"(?im)^\s*(?:HINT|REPAIR_HINT)\s*[:：]\s*(.+?)\s*$")

    def parse(self, response: str | None) -> ProcessAuditResult:
        text = response if isinstance(response, str) else ""
        match = self._STATUS.search(text[:MAX_RESPONSE_CHARS])
        if not match:
            return ProcessAuditResult("inconclusive", (), "audit_protocol_missing")
        status = match.group(1).lower()
        hints = tuple(
            _summary(item) for item in self._HINT.findall(text)[:3] if item.strip()
        )
        if status == "repair" and not hints:
            return ProcessAuditResult("inconclusive", (), "repair_hint_missing")
        return ProcessAuditResult(status, hints, "audit_protocol_valid")


@dataclass(frozen=True)
class PrefillResult:
    content: str | None
    status: str
    attempted: bool
    used: bool
    fallback: bool
    logical_calls: int = 0
    error_category: str | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    physical_calls: int = 0
    attempt_completion_tokens: int | None = None
    attempt_finish_reason: str | None = None
    attempt_error_category: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "attempted": self.attempted,
            "used": self.used,
            "fallback": self.fallback,
            "logical_calls": self.logical_calls,
            "error_category": self.error_category,
            "completion_tokens": self.completion_tokens,
            "finish_reason": _summary(self.finish_reason, 32) if self.finish_reason else None,
            "physical_calls": self.physical_calls,
            "attempt_completion_tokens": self.attempt_completion_tokens,
            "attempt_finish_reason": _summary(self.attempt_finish_reason, 32) if self.attempt_finish_reason else None,
            "attempt_error_category": self.attempt_error_category,
        }


class PrefillAdapter:
    """Try a low-entropy seed through the public three-argument client."""

    def call(
        self,
        client: Any,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        *,
        prefill: str,
        purpose: str,
        fallback_call: Callable[[], Any] | None = None,
    ) -> PrefillResult:
        if purpose not in PREFILL_PURPOSES:
            return PrefillResult(
                None,
                "not_applicable",
                False,
                False,
                False,
                0,
                "purpose_not_allowed",
            )
        seed = prefill if isinstance(prefill, str) else ""
        seed = seed[:64]
        if not seed or "\n" in seed or "\x00" in seed:
            return PrefillResult(
                None,
                "not_applicable",
                False,
                False,
                False,
                0,
                "prefill_invalid",
            )
        try:
            seeded_messages = [
                *messages,
                {"role": "assistant", "content": seed},
            ]
            raw = client.chat(seeded_messages, temperature, max_tokens)
            content = self._content(raw)
            status = self._status(raw, content, seed)
            first = PrefillResult(
                content,
                status,
                True,
                status == "continuation",
                False,
                1,
                None if content is not None else "invalid_response",
                self._completion_tokens(raw),
                self._finish_reason(raw),
                1,
            )
            if status == "continuation":
                return first
            return self._ordinary(
                client,
                messages,
                temperature,
                max_tokens,
                status=f"{status}_fallback",
                error_category=f"prefill_{status}",
                physical_calls=2,
                fallback_call=fallback_call,
                attempt=first,
            )
        except TypeError as exc:
            return self._ordinary(
                client,
                messages,
                temperature,
                max_tokens,
                status="type_error_fallback",
                error_category=_error_category(exc),
                physical_calls=2,
                fallback_call=fallback_call,
            )
        except Exception as exc:
            return self._ordinary(
                client,
                messages,
                temperature,
                max_tokens,
                status="exception_fallback",
                error_category=_error_category(exc),
                physical_calls=2,
                fallback_call=fallback_call,
            )

    def chat(self, *args: Any, **kwargs: Any) -> PrefillResult:
        return self.call(*args, **kwargs)

    def _ordinary(
        self,
        client: Any,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        *,
        status: str,
        error_category: str,
        physical_calls: int = 2,
        fallback_call: Callable[[], Any] | None = None,
        attempt: PrefillResult | None = None,
    ) -> PrefillResult:
        try:
            raw = fallback_call() if fallback_call is not None else client.chat(messages, temperature, max_tokens)
            content = self._content(raw)
            return PrefillResult(
                content,
                status,
                True,
                False,
                True,
                2,
                None if content is not None else "invalid_response",
                self._completion_tokens(raw),
                self._finish_reason(raw),
                physical_calls,
                attempt_completion_tokens=attempt.completion_tokens if attempt else None,
                attempt_finish_reason=attempt.finish_reason if attempt else None,
                attempt_error_category=error_category,
            )
        except Exception as exc:
            return PrefillResult(
                None,
                "error",
                True,
                False,
                True,
                2,
                _error_category(exc) or error_category,
                None,
                None,
                physical_calls,
                attempt_completion_tokens=attempt.completion_tokens if attempt else None,
                attempt_finish_reason=attempt.finish_reason if attempt else None,
                attempt_error_category=error_category,
            )

    @staticmethod
    def _content(raw: Any) -> str | None:
        if isinstance(raw, str):
            return raw[:MAX_RESPONSE_CHARS]
        if isinstance(raw, Mapping):
            for key in ("content", "final_response", "response"):
                if isinstance(raw.get(key), str):
                    return raw[key][:MAX_RESPONSE_CHARS]
        return None

    @staticmethod
    def _completion_tokens(raw: Any) -> int | None:
        if not isinstance(raw, Mapping):
            return None
        usage = raw.get("usage")
        value = usage.get("completion_tokens") if isinstance(usage, Mapping) else raw.get("completion_tokens")
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    @staticmethod
    def _finish_reason(raw: Any) -> str | None:
        value = raw.get("finish_reason") if isinstance(raw, Mapping) else None
        return str(value)[:32] if value is not None else None

    @staticmethod
    def _status(raw: Any, content: str | None, seed: str) -> str:
        if isinstance(raw, Mapping):
            explicit = raw.get("prefill_status", raw.get("status"))
            if isinstance(explicit, str):
                normalized = {
                    "continued": "continuation",
                    "continuation": "continuation",
                    "echoed": "echo",
                    "echo": "echo",
                    "ignored": "ignored",
                }.get(explicit.lower())
                if normalized:
                    return normalized
        if content is None:
            return "ignored"
        if content.strip() == seed.strip():
            return "echo"
        if content.startswith(seed) or content.lstrip().startswith(seed.lstrip()):
            return "continuation"
        return "ignored"


@dataclass(frozen=True)
class AssetResult:
    logical_id: str
    relative_path: str
    status: str
    available: bool
    sha256: str | None = None
    reason: str | None = None
    content: str | None = None

    @property
    def enabled(self) -> bool:
        return self.available and self.status == "enabled"

    def as_dict(self) -> dict[str, Any]:
        return {
            "logical_id": self.logical_id,
            "relative_path": self.relative_path,
            "status": self.status,
            "available": self.available,
            "enabled": self.enabled,
            "sha256": self.sha256,
            "reason": self.reason,
        }


class LogicalAssetRegistry:
    """Map stable logical IDs to registered relative assets, fail-closed."""

    def __init__(
        self,
        root: str | Path,
        assets: Mapping[str, str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self._assets: dict[str, str] = {}
        for logical_id, relative_path in (assets or {}).items():
            self.register(logical_id, relative_path)

    def register(self, logical_id: str, relative_path: str) -> None:
        logical = str(logical_id or "").strip()
        raw = relative_path if isinstance(relative_path, str) else ""
        raw = raw.strip()
        if not _ASSET_ID.fullmatch(logical):
            raise ValueError("invalid_logical_asset_id")
        if self._unsafe_path(raw):
            raise ValueError("asset_path_must_be_relative")
        self._assets[logical] = raw.replace("\\", "/")

    def load(self, logical_id: str, *, encoding: str = "utf-8") -> AssetResult:
        logical = str(logical_id or "").strip()
        relative = self._assets.get(logical, "")
        if not relative:
            return AssetResult(logical, "", "unavailable", False, reason="asset_not_registered")
        path = (self.root / PurePath(relative)).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            return AssetResult(logical, relative, "unavailable", False, reason="asset_path_escape")
        try:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            content = data.decode(encoding)
        except FileNotFoundError:
            return AssetResult(logical, relative, "unavailable", False, reason="asset_missing")
        except UnicodeError:
            return AssetResult(logical, relative, "unavailable", False, reason="asset_encoding_error")
        except OSError:
            return AssetResult(logical, relative, "unavailable", False, reason="asset_read_error")
        return AssetResult(logical, relative, "enabled", True, digest, content=content)

    inspect = load
    resolve = load
    get = load

    @staticmethod
    def _unsafe_path(value: str) -> bool:
        if not value or "\x00" in value:
            return True
        if value.startswith(("/", "\\")):
            return True
        windows_path = PureWindowsPath(value)
        if Path(value).is_absolute() or windows_path.is_absolute() or windows_path.root:
            return True
        if re.match(r"^[A-Za-z]:", value):
            return True
        parts = PurePath(value.replace("\\", "/")).parts
        return ".." in parts


__all__ = [
    "MAX_LOGICAL_CALLS",
    "MAX_TOTAL_TOKENS",
    "MAX_WALL_SECONDS",
    "MAX_SUMMARY_CHARS",
    "STATE_START",
    "STATE_ATTEMPT",
    "STATE_CANDIDATE",
    "STATE_VERIFIED",
    "STATE_CONFLICT",
    "STATE_REPAIR",
    "STATE_CONTINUATION",
    "STATE_SELECTED",
    "STATE_ABSTAINED",
    "STATE_FINALIZED",
    "STATES",
    "STATE_TRANSITIONS",
    "HARDENING_STATES",
    "CandidateRecord",
    "Candidate",
    "HardeningLedger",
    "CallReservation",
    "BudgetCallRecord",
    "CallRecord",
    "HardeningBudget",
    "EvidenceStatus",
    "EVIDENCE_SUPPORT",
    "EVIDENCE_CONTRADICT",
    "EVIDENCE_INCONCLUSIVE",
    "EVIDENCE_STATUSES",
    "SUPPORT",
    "CONTRADICT",
    "INCONCLUSIVE",
    "EvidenceRecord",
    "EvidenceAdapter",
    "adapt_evidence",
    "evidence_from_result",
    "PLAYOFF_A",
    "PLAYOFF_B",
    "PLAYOFF_BOTH",
    "PLAYOFF_NEITHER",
    "PLAYOFF_INCONCLUSIVE",
    "PLAYOFF_DECISIONS",
    "PlayoffResult",
    "DeterministicPlayoff",
    "ProcessAuditResult",
    "ProcessAuditParser",
    "PREFILL_PURPOSES",
    "LOW_ENTROPY_PURPOSES",
    "PrefillResult",
    "PrefillAdapter",
    "AssetResult",
    "LogicalAssetRegistry",
]
