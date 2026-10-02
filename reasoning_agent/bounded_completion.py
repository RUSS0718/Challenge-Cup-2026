"""Bounded completion observation and zero-model probe infrastructure.

The module deliberately owns execution and evidence boundaries, not math
selection.  A model is only called through the public
``client.chat(messages, temperature, max_tokens)`` contract.  Raw responses
are written only to an explicitly supplied local diagnostic store; reports
and solve traces contain summaries and hashes instead.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


BCOMP_VERSION = "BCOMP-001"
METHOD_ID = "bounded_completion_foundations_v1"
PARSER_VERSION = "host_parser_v1"
CANDIDATE_PROTOCOL_ID = "ordinary_free_format_typed_formation_v1"

MAX_WORKERS = 3
MAX_ITEM_SECONDS = 20 * 60
MAX_WINDOW_SECONDS = 6 * 60 * 60
MAX_CALLS_PER_ITEM = 5
MAX_REQUESTED_TOKENS_PER_ITEM = 16_384

FAILURE_TIMEOUT = "timeout"
FAILURE_TRANSPORT = "transport"
FAILURE_EMPTY = "empty"
FAILURE_MALFORMED = "malformed"
FAILURE_BUDGET_REFUSAL = "budget_refusal"
FAILURE_DEADLINE_REFUSAL = "deadline_refusal"
FAILURE_CANCELLED = "cancelled"
FAILURE_UNKNOWN = "unknown"

FAILURE_CATEGORIES = frozenset(
    {
        FAILURE_TIMEOUT,
        FAILURE_TRANSPORT,
        FAILURE_EMPTY,
        FAILURE_MALFORMED,
        FAILURE_BUDGET_REFUSAL,
        FAILURE_DEADLINE_REFUSAL,
        FAILURE_CANCELLED,
        FAILURE_UNKNOWN,
    }
)

_PLACEHOLDER_VALUES = {"", "none", "null", "unknown", "todo", "tbd", "unfrozen"}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_FORBIDDEN_GOLD_KEYS = frozenset(
    {"answer", "answers", "gold", "gold_answer", "reference_answer", "solution"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_hash(record: Mapping[str, Any]) -> str:
    return sha256_text(_canonical_json(dict(record)))


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # A crashed append may leave a partial final line.  Earlier
            # complete records remain valid and are deliberately recoverable.
            break
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _recover_partial_tail(path: Path) -> None:
    """Drop only an incomplete final line before the next append."""
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    last_newline = data.rfind(b"\n")
    path.write_bytes(data[: last_newline + 1] if last_newline >= 0 else b"")


def normalize_failure_category(category: Any) -> str:
    value = str(category or "").strip().lower()
    if value in FAILURE_CATEGORIES:
        return value
    if value in {"max_tokens", "length", "deadline_exceeded"}:
        return FAILURE_TIMEOUT
    if value in {"connectivity", "proxy", "tls", "http_status", "request", "rate_limit", "client_error"}:
        return FAILURE_TRANSPORT
    if value in {"invalid_response", "invalid", "malformed_response"}:
        return FAILURE_MALFORMED
    if value in {"budget_exhausted", "budget"}:
        return FAILURE_BUDGET_REFUSAL
    if value in {"wall_clock_limit", "deadline", "deadline_exhausted"}:
        return FAILURE_DEADLINE_REFUSAL
    if value in {"cancelled", "canceled", "cancel"}:
        return FAILURE_CANCELLED
    return FAILURE_UNKNOWN if value else FAILURE_UNKNOWN


def classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    if isinstance(exc, (TimeoutError,)) or "timeout" in name or "timeout" in detail or "deadline" in detail:
        return FAILURE_TIMEOUT
    if "cancel" in name or "cancel" in detail:
        return FAILURE_CANCELLED
    if any(token in name or token in detail for token in ("connection", "proxy", "tls", "http", "request", "rate")):
        return FAILURE_TRANSPORT
    return FAILURE_UNKNOWN


def _public_response(response: Any) -> tuple[str | None, int | None, str | None, str | None]:
    """Unpack the public string contract plus an optional test envelope."""
    if isinstance(response, str):
        return response, None, None, None
    if isinstance(response, Mapping):
        content: Any = response.get("content")
        message = response.get("message")
        if content is None and isinstance(message, Mapping):
            content = message.get("content")
        usage = response.get("usage")
        tokens: Any = usage.get("completion_tokens") if isinstance(usage, Mapping) else response.get("completion_tokens")
        if isinstance(tokens, bool):
            tokens = None
        try:
            completion_tokens = int(tokens) if tokens is not None else None
        except (TypeError, ValueError):
            completion_tokens = None
        finish = response.get("finish_reason")
        return (
            content if isinstance(content, str) else None,
            completion_tokens,
            str(finish) if finish is not None else None,
            None if isinstance(content, str) else FAILURE_MALFORMED,
        )
    return None, None, None, FAILURE_MALFORMED


def _classify_response(content: str | None, error_category: Any = None) -> str | None:
    if error_category:
        return normalize_failure_category(error_category)
    if content is None:
        return FAILURE_MALFORMED
    if not content.strip():
        return FAILURE_EMPTY
    return None


@dataclass(frozen=True)
class DeadlineCapability:
    name: str
    execution_layer: str
    status: str
    guarantee: str
    verification: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "execution_layer": self.execution_layer,
            "status": self.status,
            "guarantee": self.guarantee,
            "verification": self.verification,
        }


def deadline_capability_matrix() -> list[dict[str, str]]:
    """Return the explicit boundary audit used by the probe and report."""
    return [
        DeadlineCapability(
            "call_admission_deadline",
            "host scheduler",
            "supported",
            "No new call is admitted unless its reserved wait and finalization allowance fit the remaining item and window budget.",
            "FakeClock/BoundaryPolicy tests and runner manifest.",
        ).as_dict(),
        DeadlineCapability(
            "call_wait_deadline",
            "local bounded runner",
            "supported_local_only",
            "A local worker is observed until the configured wait deadline; a blocked public client is not force-terminated by the inline solve seam.",
            "Blocking-stub runner test; timeout remains recorded if the worker is still active.",
        ).as_dict(),
        DeadlineCapability(
            "local_work_unit_termination",
            "local runner",
            "unknown_after_block",
            "A daemon worker can be bounded and accounted for, but an arbitrary synchronous client cannot be killed safely in-process.",
            "Active-worker count, timeout event, and late completion event.",
        ).as_dict(),
        DeadlineCapability(
            "remote_cancellation",
            "official client/platform",
            "unsupported",
            "The public chat contract exposes no cancellation handle; stopping local waiting does not claim remote cancellation.",
            "No cancellation API is assumed; reports use remote_cancellation=unknown.",
        ).as_dict(),
        DeadlineCapability(
            "solve_return_deadline",
            "official runner/platform",
            "platform_owned",
            "The host can refuse later work, but cannot force a synchronous injected client to return before it returns.",
            "Platform runner timeout and local post-return timing only.",
        ).as_dict(),
        DeadlineCapability(
            "window_stop",
            "probe runner",
            "supported_for_dispatch",
            "The runner stops dispatching new tasks at the window deadline or on an unresolved active call; pending tasks are marked skipped.",
            "Planned/dispatched/skipped counts and stop_reason in report.",
        ).as_dict(),
    ]


@dataclass(frozen=True)
class BoundaryPolicy:
    per_item_seconds: float = float(MAX_ITEM_SECONDS)
    window_seconds: float = float(MAX_WINDOW_SECONDS)
    call_wait_seconds: float = 900.0
    finalization_allowance_seconds: float = 30.0
    max_workers: int = MAX_WORKERS
    max_calls_per_item: int = 1
    max_requested_tokens_per_item: int = MAX_REQUESTED_TOKENS_PER_ITEM

    def validate(self) -> None:
        values = (
            self.per_item_seconds,
            self.window_seconds,
            self.call_wait_seconds,
            self.finalization_allowance_seconds,
        )
        if any(
            not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
            for value in values
        ):
            raise ValueError("deadline_values_must_be_positive")
        if self.per_item_seconds > MAX_ITEM_SECONDS:
            raise ValueError("per_item_seconds_exceeds_official_limit")
        if self.window_seconds > MAX_WINDOW_SECONDS:
            raise ValueError("window_seconds_exceeds_official_limit")
        if self.call_wait_seconds + self.finalization_allowance_seconds > self.per_item_seconds:
            raise ValueError("call_wait_plus_finalization_exceeds_item_window")
        if not 1 <= int(self.max_workers) <= MAX_WORKERS:
            raise ValueError("max_workers_exceeds_official_concurrency")
        if not 1 <= int(self.max_calls_per_item) <= MAX_CALLS_PER_ITEM:
            raise ValueError("max_calls_per_item_out_of_bounds")
        if not 1 <= int(self.max_requested_tokens_per_item) <= MAX_REQUESTED_TOKENS_PER_ITEM:
            raise ValueError("max_requested_tokens_per_item_out_of_bounds")

    def admit(
        self,
        *,
        item_elapsed_seconds: float,
        calls_used: int,
        requested_tokens: int,
        requested_this_call: int,
        window_elapsed_seconds: float | None = None,
    ) -> tuple[bool, str]:
        self.validate()
        if calls_used >= self.max_calls_per_item or requested_tokens + requested_this_call > self.max_requested_tokens_per_item:
            return False, FAILURE_BUDGET_REFUSAL
        remaining = self.per_item_seconds - max(0.0, float(item_elapsed_seconds))
        if remaining < self.call_wait_seconds + self.finalization_allowance_seconds:
            return False, FAILURE_DEADLINE_REFUSAL
        if window_elapsed_seconds is not None:
            window_remaining = self.window_seconds - max(0.0, float(window_elapsed_seconds))
            if window_remaining < self.call_wait_seconds + self.finalization_allowance_seconds:
                return False, FAILURE_DEADLINE_REFUSAL
        return True, "admitted"


class ArtifactPersistenceError(RuntimeError):
    pass


class ArtifactStore:
    """Thread-safe append-only diagnostic streams with crash recovery."""

    _STREAM_FILES = {
        "events": "events.jsonl",
        "artifacts": "artifacts.jsonl",
        "assessments": "assessments.jsonl",
    }

    def __init__(
        self,
        root: Path | str,
        *,
        max_record_bytes: int = 512 * 1024,
        max_response_chars: int = 24_000,
    ) -> None:
        self.root = Path(root)
        self.max_record_bytes = max(1024, int(max_record_bytes))
        self.max_response_chars = max(1, int(max_response_chars))
        self._lock = threading.RLock()
        self.failure_reason: str | None = None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None

    def prepare(self) -> None:
        if self.failed:
            raise ArtifactPersistenceError(self.failure_reason or "artifact_store_failed")
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for filename in self._STREAM_FILES.values():
                (self.root / filename).touch(exist_ok=True)
        except OSError as exc:
            self.failure_reason = "prepare_failed"
            raise ArtifactPersistenceError("prepare_failed") from exc

    def append(self, stream: str, record: Mapping[str, Any]) -> str:
        if stream not in self._STREAM_FILES:
            raise ValueError("unknown_artifact_stream")
        if self.failed:
            raise ArtifactPersistenceError(self.failure_reason or "artifact_store_failed")
        payload = dict(record)
        payload.setdefault("schema_version", "bcomp.artifact.v1")
        line = _canonical_json(payload) + "\n"
        if len(line.encode("utf-8")) > self.max_record_bytes:
            self.failure_reason = "record_size_limit"
            raise ArtifactPersistenceError("record_size_limit")
        path = self.root / self._STREAM_FILES[stream]
        try:
            self.prepare()
            with self._lock:
                _recover_partial_tail(path)
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
        except ArtifactPersistenceError:
            raise
        except OSError as exc:
            self.failure_reason = "append_failed"
            raise ArtifactPersistenceError("append_failed") from exc
        return _record_hash(payload)

    def append_event(self, record: Mapping[str, Any]) -> str:
        return self.append("events", record)

    def append_artifact(self, record: Mapping[str, Any]) -> str:
        return self.append("artifacts", record)

    def append_assessment(self, record: Mapping[str, Any]) -> str:
        return self.append("assessments", record)

    def read(self, stream: str) -> list[dict[str, Any]]:
        if stream not in self._STREAM_FILES:
            raise ValueError("unknown_artifact_stream")
        return _read_jsonl(self.root / self._STREAM_FILES[stream])

    def write_response(
        self,
        handle: "CallHandle",
        *,
        problem: str,
        response: str | None,
        finish_reason: str | None,
        completion_tokens: int | None,
        support_source: str = "model",
        recovery_source: str = "none",
    ) -> tuple[str, str]:
        if response is not None and len(response) > self.max_response_chars:
            self.failure_reason = "response_size_limit"
            raise ArtifactPersistenceError("response_size_limit")
        record: dict[str, Any] = {
            "artifact_type": "response",
            "artifact_id": handle.event_id + ":response",
            "event_id": handle.event_id,
            "run_id": handle.run_id,
            "item_id": handle.item_id,
            "arm_id": handle.arm_id,
            "attempt": handle.attempt,
            "stage": handle.stage,
            "problem": _clip(problem, self.max_response_chars),
            "problem_sha256": sha256_text(problem),
            "response": response,
            "response_present": bool(response and response.strip()),
            "response_sha256": sha256_text(response) if isinstance(response, str) else None,
            "finish_reason": _clip(finish_reason, 32) if finish_reason else None,
            "completion_tokens": completion_tokens if isinstance(completion_tokens, int) and completion_tokens >= 0 else None,
            "support_source": _clip(support_source, 64),
            "recovery_source": _clip(recovery_source, 64),
            "stored_at_utc": _utc_now(),
        }
        artifact_hash = self.append_artifact(record)
        return record["artifact_id"], artifact_hash


@dataclass(frozen=True)
class CallHandle:
    event_id: str
    run_id: str
    item_id: str
    arm_id: str
    attempt: int
    sequence: int
    stage: str
    requested_tokens: int
    started_monotonic: float
    started_at_utc: str
    problem: str = field(repr=False, default="")


class NullCompletionObserver:
    """No-op observer used when diagnostics are not explicitly enabled."""

    failed = False

    def should_stop(self) -> bool:
        return False

    def start_call(self, **_kwargs: Any) -> None:
        return None

    def finish_call(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_refusal(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class BoundedCompletionObserver:
    """Persist solve call lifecycle without leaking raw responses into trace."""

    def __init__(
        self,
        store: ArtifactStore,
        *,
        run_id: str,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.store = store
        self.run_id = _clip(run_id, 96) or "run"
        self.clock = clock or time.monotonic
        self._sequence = 0
        self._open: dict[str, CallHandle] = {}
        self._timed_out: dict[str, CallHandle] = {}
        self._lock = threading.RLock()
        self.failure_reason: str | None = None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None or self.store.failed

    def should_stop(self) -> bool:
        return self.failed

    def _fail(self, reason: str) -> None:
        if self.failure_reason is None:
            self.failure_reason = reason

    def _common_event(self, handle: CallHandle) -> dict[str, Any]:
        return {
            "event_id": handle.event_id,
            "run_id": handle.run_id,
            "item_id": handle.item_id,
            "arm_id": handle.arm_id,
            "attempt": handle.attempt,
            "sequence": handle.sequence,
            "stage": handle.stage,
            "requested_tokens": handle.requested_tokens,
        }

    def start_call(
        self,
        *,
        stage: str,
        requested_tokens: int,
        context: Mapping[str, Any] | None = None,
        attempt: int | None = None,
    ) -> CallHandle:
        with self._lock:
            if self.failed:
                raise ArtifactPersistenceError(self.failure_reason or self.store.failure_reason or "observer_failed")
            self._sequence += 1
            context = dict(context or {})
            item_id = _clip(context.get("item_id", "unknown"), 96) or "unknown"
            arm_id = _clip(context.get("arm_id", "default"), 96) or "default"
            call_attempt = max(1, int(attempt or context.get("attempt", 1)))
            event_id = f"{self.run_id}:{item_id}:{arm_id}:{call_attempt}:{self._sequence}"
            handle = CallHandle(
                event_id,
                self.run_id,
                item_id,
                arm_id,
                call_attempt,
                self._sequence,
                _clip(stage, 96) or "call",
                max(0, int(requested_tokens)),
                self.clock(),
                _utc_now(),
                _clip(context.get("problem", ""), self.store.max_response_chars),
            )
            try:
                self.store.append_event(
                    {
                        **self._common_event(handle),
                        "event_type": "start",
                        "status": "started",
                        "started_at_utc": handle.started_at_utc,
                    }
                )
            except ArtifactPersistenceError as exc:
                self._fail(str(exc))
                raise
            self._open[handle.event_id] = handle
            return handle

    def record_refusal(
        self,
        *,
        stage: str,
        requested_tokens: int,
        category: str,
        reason: str,
        context: Mapping[str, Any] | None = None,
        attempt: int = 0,
    ) -> None:
        with self._lock:
            if self.failed:
                return
            self._sequence += 1
            context = dict(context or {})
            run_id = _clip(context.get("run_id", self.run_id), 96) or self.run_id
            item_id = _clip(context.get("item_id", "unknown"), 96) or "unknown"
            arm_id = _clip(context.get("arm_id", "default"), 96) or "default"
            event_id = f"{run_id}:{item_id}:{arm_id}:{max(0, int(attempt))}:{self._sequence}"
            try:
                self.store.append_event(
                    {
                        "event_id": event_id,
                        "run_id": run_id,
                        "item_id": item_id,
                        "arm_id": arm_id,
                        "attempt": max(0, int(attempt)),
                        "sequence": self._sequence,
                        "stage": _clip(stage, 96) or "call",
                        "event_type": "refusal",
                        "status": "refused",
                        "requested_tokens": max(0, int(requested_tokens)),
                        "error_category": normalize_failure_category(category),
                        "reason": _clip(reason, 160),
                        "recorded_at_utc": _utc_now(),
                    }
                )
            except ArtifactPersistenceError as exc:
                self._fail(str(exc))

    def _write_assessment(self, handle: CallHandle, assessment: Mapping[str, Any] | None) -> str | None:
        if not assessment:
            return None
        return self.store.append_assessment(
            {
                "assessment_id": handle.event_id + ":assessment",
                "event_id": handle.event_id,
                "run_id": handle.run_id,
                "item_id": handle.item_id,
                "arm_id": handle.arm_id,
                "parser_version": _clip(assessment.get("parser_version", PARSER_VERSION), 96),
                **{key: value for key, value in assessment.items() if key != "parser_version"},
                "derived_at_utc": _utc_now(),
            }
        )

    def finish_call(
        self,
        handle: CallHandle,
        *,
        response: Any = None,
        error_category: str | None = None,
        finish_reason: str | None = None,
        completion_tokens: int | None = None,
        duration_ms: int | None = None,
        assessment: Mapping[str, Any] | None = None,
        support_source: str = "model",
        recovery_source: str = "none",
    ) -> None:
        content, envelope_tokens, envelope_finish, unpack_error = _public_response(response)
        if completion_tokens is None:
            completion_tokens = envelope_tokens
        if finish_reason is None:
            finish_reason = envelope_finish
        category = _classify_response(content, error_category or unpack_error)
        with self._lock:
            late = handle.event_id in self._timed_out
            if not late and handle.event_id not in self._open:
                try:
                    self.store.append_event(
                        {
                            **self._common_event(handle),
                            "event_type": "duplicate",
                            "status": "ignored",
                            "error_category": FAILURE_UNKNOWN,
                            "reason": "terminal_event_already_recorded",
                            "recorded_at_utc": _utc_now(),
                        }
                    )
                except ArtifactPersistenceError as exc:
                    self._fail(str(exc))
                return
            self._open.pop(handle.event_id, None)
            self._timed_out.pop(handle.event_id, None)
            try:
                if assessment is None and handle.problem:
                    assessment = assess_formation(
                        handle.problem,
                        content,
                        finish_reason,
                        parser_version=PARSER_VERSION,
                    )
                artifact_id, artifact_hash = self.store.write_response(
                    handle,
                    problem=handle.problem,
                    response=content,
                    finish_reason=finish_reason,
                    completion_tokens=completion_tokens,
                    support_source=support_source,
                    recovery_source=recovery_source,
                )
                assessment_id = self._write_assessment(handle, assessment)
                self.store.append_event(
                    {
                        **self._common_event(handle),
                        "event_type": "late_completion" if late else "terminal",
                        "status": "late" if late else "completed" if category is None else "failed",
                        "error_category": category,
                        "finish_reason": _clip(finish_reason, 32) if finish_reason else None,
                        "completion_tokens": completion_tokens if isinstance(completion_tokens, int) and completion_tokens >= 0 else None,
                        "duration_ms": max(0, int(duration_ms if duration_ms is not None else (self.clock() - handle.started_monotonic) * 1000)),
                        "artifact_id": artifact_id,
                        "artifact_sha256": artifact_hash,
                        "assessment_id": assessment_id,
                        "remote_cancellation": "unknown" if late else None,
                        "local_work_unit": "returned",
                        "ended_at_utc": _utc_now(),
                    }
                )
            except ArtifactPersistenceError as exc:
                self._fail(str(exc))

    def record_timeout(self, handle: CallHandle, *, reason: str = "call_wait_deadline") -> None:
        with self._lock:
            if handle.event_id in self._timed_out:
                try:
                    self.store.append_event(
                        {
                            **self._common_event(handle),
                            "event_type": "duplicate",
                            "status": "ignored",
                            "error_category": FAILURE_UNKNOWN,
                            "reason": "timeout_event_already_recorded",
                            "recorded_at_utc": _utc_now(),
                        }
                    )
                except ArtifactPersistenceError as exc:
                    self._fail(str(exc))
                return
            self._open.pop(handle.event_id, None)
            self._timed_out[handle.event_id] = handle
            try:
                self.store.append_event(
                    {
                        **self._common_event(handle),
                        "event_type": "terminal",
                        "status": "timed_out",
                        "error_category": FAILURE_TIMEOUT,
                        "reason": _clip(reason, 160),
                        "duration_ms": max(0, int((self.clock() - handle.started_monotonic) * 1000)),
                        "remote_cancellation": "unknown",
                        "local_work_unit": "unresolved_or_unknown",
                        "ended_at_utc": _utc_now(),
                    }
                )
            except ArtifactPersistenceError as exc:
                self._fail(str(exc))

    def open_call_count(self) -> int:
        with self._lock:
            return len(self._open) + len(self._timed_out)


def assess_formation(
    problem: str,
    response: str | None,
    finish_reason: str | None = None,
    *,
    parser_version: str = PARSER_VERSION,
    support_source: str = "model",
    recovery_source: str = "none",
) -> dict[str, Any]:
    """Derive formation state from a response without changing the source."""
    if not isinstance(response, str) or not response.strip():
        return {
            "parser_version": parser_version,
            "formation_status": "no_response",
            "candidate_formed": False,
            "complete_candidate": False,
            "candidate_count": 0,
            "parser_status": "missing",
            "truncated": False,
            "support_source": support_source,
            "recovery_source": recovery_source,
        }
    from reasoning_agent.math_harness import HostParser

    parsed = HostParser().parse(
        response,
        problem=problem,
        source="formation_assessment",
        finish_reason=finish_reason,
    )
    candidate_count = len(parsed.candidates)
    candidate_formed = candidate_count > 0
    if parsed.status == "parsed" and candidate_count == 1 and not parsed.truncated:
        formation_status = "complete_candidate"
        complete_candidate = True
    elif parsed.status == "truncated_with_candidate" or candidate_formed:
        formation_status = "candidate_incomplete_or_ambiguous"
        complete_candidate = False
    elif parsed.status in {"truncated_without_candidate", "rejected"}:
        formation_status = "incomplete_response"
        complete_candidate = False
    else:
        formation_status = "no_candidate"
        complete_candidate = False
    return {
        "parser_version": parser_version,
        "formation_status": formation_status,
        "candidate_formed": candidate_formed,
        "complete_candidate": complete_candidate,
        "candidate_count": candidate_count,
        "parser_status": parsed.status,
        "answer_type": parsed.answer_type,
        "truncated": bool(parsed.truncated),
        "support_source": _clip(support_source, 64),
        "recovery_source": _clip(recovery_source, 64),
    }


def replay_formations(
    source: ArtifactStore | Path | str | Iterable[Mapping[str, Any]],
    *,
    parser_version: str = PARSER_VERSION,
    derived_store: ArtifactStore | None = None,
) -> list[dict[str, Any]]:
    """Replay immutable response artifacts into new derived assessments."""
    if isinstance(source, ArtifactStore):
        records = source.read("artifacts")
    elif isinstance(source, (Path, str)):
        records = _read_jsonl(Path(source))
    else:
        records = [dict(record) for record in source]
    assessments: list[dict[str, Any]] = []
    for record in records:
        if record.get("artifact_type") != "response":
            continue
        response = record.get("response")
        problem = record.get("problem") if isinstance(record.get("problem"), str) else ""
        derived = assess_formation(
            problem,
            response if isinstance(response, str) else None,
            record.get("finish_reason"),
            parser_version=parser_version,
            support_source=str(record.get("support_source", "model")),
            recovery_source=str(record.get("recovery_source", "none")),
        )
        assessments.append(
            {
                "assessment_id": str(record.get("artifact_id", "artifact")) + ":replay:" + parser_version,
                "artifact_id": record.get("artifact_id"),
                "artifact_sha256": _record_hash(record),
                "source_artifact_sha256": _record_hash(record),
                **derived,
            }
        )
        if derived_store is not None:
            derived_store.append_assessment(assessments[-1])
    return assessments


@dataclass(frozen=True)
class ProbeArm:
    arm_id: str
    max_tokens: int
    prompt_scope: str
    prompt_suffix: str = ""

    def validate(self) -> None:
        if not _clip(self.arm_id, 96) or self.arm_id.lower() in _PLACEHOLDER_VALUES:
            raise ValueError("arm_id_missing")
        if not 1 <= int(self.max_tokens) <= MAX_REQUESTED_TOKENS_PER_ITEM:
            raise ValueError("arm_max_tokens_out_of_bounds")
        if not _clip(self.prompt_scope, 4000):
            raise ValueError("arm_prompt_scope_missing")

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "max_tokens": int(self.max_tokens),
            "prompt_scope": self.prompt_scope,
            "prompt_suffix": self.prompt_suffix,
        }


@dataclass(frozen=True)
class ProbeItem:
    item_id: str
    problem: str
    source_family: str = ""
    domain: str = ""
    language: str = ""
    answer_type: str = ""

    def validate(self) -> None:
        if not _clip(self.item_id, 96) or self.item_id.lower() in _PLACEHOLDER_VALUES:
            raise ValueError("item_id_missing")
        if not isinstance(self.problem, str) or not self.problem.strip():
            raise ValueError("problem_missing")

    def prompt_safe(self) -> dict[str, str]:
        self.validate()
        return {
            "item_id": _clip(self.item_id, 96),
            "source_family": _clip(self.source_family, 96),
            "domain": _clip(self.domain, 96),
            "language": _clip(self.language, 32),
            "answer_type": _clip(self.answer_type, 64),
            "problem": self.problem,
        }


@dataclass(frozen=True)
class ProbeConfig:
    run_id: str
    method_id: str
    code_sha256: str
    protocol_sha256: str
    model_id: str
    endpoint_id: str
    dataset_path: str
    dataset_sha256: str
    seed: int
    prompt_id: str
    system_prompt: str
    user_prompt_prefix: str
    parser_version: str
    scorer_version: str
    actual_route: str
    bank_mode: str = "off"
    temperature: float = 0.6
    boundary: BoundaryPolicy = BoundaryPolicy()
    arms: tuple[ProbeArm, ...] = ()
    planned_items: int = 0
    arm_order_policy: str = "rotating_balanced"
    gold_location: str = "host_only"
    isolation_verified: bool = True
    max_retries: int = 0
    stop_rules: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        errors: list[str] = []
        required_text = {
            "run_id": self.run_id,
            "method_id": self.method_id,
            "code_sha256": self.code_sha256,
            "protocol_sha256": self.protocol_sha256,
            "model_id": self.model_id,
            "endpoint_id": self.endpoint_id,
            "dataset_path": self.dataset_path,
            "dataset_sha256": self.dataset_sha256,
            "prompt_id": self.prompt_id,
            "system_prompt": self.system_prompt,
            "user_prompt_prefix": self.user_prompt_prefix,
            "parser_version": self.parser_version,
            "scorer_version": self.scorer_version,
            "actual_route": self.actual_route,
        }
        for name, value in required_text.items():
            if not isinstance(value, str) or not value.strip() or value.strip().lower() in _PLACEHOLDER_VALUES:
                errors.append(name + "_missing")
        if isinstance(self.dataset_path, str):
            dataset_path = Path(self.dataset_path)
            if dataset_path.is_absolute() or ".." in dataset_path.parts:
                errors.append("dataset_path_must_be_repo_relative")
        prompt_text = (str(self.system_prompt) + "\n" + str(self.user_prompt_prefix)).lower()
        if any(token in prompt_text for token in ("eval_112", "answer_bank", "gold_answer", "reference_answer")):
            errors.append("prompt_must_not_reference_answer_data")
        for name, value in (("code_sha256", self.code_sha256), ("protocol_sha256", self.protocol_sha256), ("dataset_sha256", self.dataset_sha256)):
            if isinstance(value, str) and not _HEX64_RE.fullmatch(value):
                errors.append(name + "_invalid")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            errors.append("seed_missing")
        if not isinstance(self.temperature, (int, float)) or not math.isfinite(float(self.temperature)):
            errors.append("temperature_invalid")
        if self.bank_mode != "off":
            errors.append("bank_must_be_off")
        if self.gold_location != "host_only":
            errors.append("gold_must_remain_host_only")
        if not self.isolation_verified:
            errors.append("dataset_isolation_not_verified")
        try:
            retries = int(self.max_retries)
        except (TypeError, ValueError):
            retries = -1
        if retries != 0:
            errors.append("retries_must_be_zero")
        if not isinstance(self.planned_items, int) or self.planned_items <= 0:
            errors.append("planned_items_missing")
        try:
            self.boundary.validate()
        except ValueError as exc:
            errors.append(str(exc))
        if not self.arms:
            errors.append("arms_missing")
        for arm in self.arms:
            try:
                arm.validate()
            except ValueError as exc:
                errors.append(str(exc))
        if len({arm.arm_id for arm in self.arms}) != len(self.arms):
            errors.append("duplicate_arm_id")
        if self.arm_order_policy not in {"rotating_balanced", "fixed"}:
            errors.append("arm_order_policy_invalid")
        if len(self.arms) > 1 and self.arm_order_policy != "rotating_balanced":
            errors.append("multi_arm_order_must_rotate")
        required_stop_rules = {
            "void_on_incomplete_records",
            "void_on_unstable_endpoint",
            "first_three_formed_zero",
            "max_model_error_rate",
        }
        if not isinstance(self.stop_rules, Mapping) or not required_stop_rules.issubset(self.stop_rules):
            errors.append("stop_rules_incomplete")
        else:
            if not isinstance(self.stop_rules["max_model_error_rate"], (int, float)):
                errors.append("max_model_error_rate_missing")
            elif not 0 <= float(self.stop_rules["max_model_error_rate"]) <= 1:
                errors.append("max_model_error_rate_out_of_bounds")
        if self.arms and len(self.arms) > self.boundary.max_calls_per_item:
            errors.append("arms_exceed_per_item_call_cap")
        if self.arms and sum(int(arm.max_tokens) for arm in self.arms) > self.boundary.max_requested_tokens_per_item:
            errors.append("arms_exceed_per_item_token_cap")
        if self.arms and len(self.arms) * (
            self.boundary.call_wait_seconds + self.boundary.finalization_allowance_seconds
        ) > self.boundary.per_item_seconds:
            errors.append("arms_time_budget_exceeds_item_window")
        if errors:
            raise ValueError("invalid_preregistration:" + ",".join(dict.fromkeys(errors)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "method_id": self.method_id,
            "bcomp_version": BCOMP_VERSION,
            "code_sha256": self.code_sha256,
            "protocol_sha256": self.protocol_sha256,
            "model_id": self.model_id,
            "endpoint_id": self.endpoint_id,
            "dataset_path": self.dataset_path,
            "dataset_sha256": self.dataset_sha256,
            "seed": self.seed,
            "prompt_id": self.prompt_id,
            "system_prompt": self.system_prompt,
            "user_prompt_prefix": self.user_prompt_prefix,
            "parser_version": self.parser_version,
            "scorer_version": self.scorer_version,
            "actual_route": self.actual_route,
            "bank_mode": self.bank_mode,
            "temperature": self.temperature,
            "boundary": {
                "per_item_seconds": self.boundary.per_item_seconds,
                "window_seconds": self.boundary.window_seconds,
                "call_wait_seconds": self.boundary.call_wait_seconds,
                "finalization_allowance_seconds": self.boundary.finalization_allowance_seconds,
                "max_workers": self.boundary.max_workers,
                "max_calls_per_item": self.boundary.max_calls_per_item,
                "max_requested_tokens_per_item": self.boundary.max_requested_tokens_per_item,
            },
            "arms": [arm.as_dict() for arm in self.arms],
            "planned_items": self.planned_items,
            "planned_requests_per_item": len(self.arms),
            "arm_order_policy": self.arm_order_policy,
            "gold_location": self.gold_location,
            "isolation_verified": self.isolation_verified,
            "max_retries": self.max_retries,
            "stop_rules": dict(self.stop_rules),
        }


@dataclass(frozen=True)
class ProbeTask:
    task_id: str
    item_id: str
    problem: str
    arm_id: str
    order_index: int
    max_tokens: int
    prompt_scope: str
    prompt_suffix: str

    def messages(self, config: ProbeConfig) -> list[dict[str, str]]:
        system = config.system_prompt
        if self.prompt_suffix:
            system += "\n\n" + self.prompt_suffix
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": config.user_prompt_prefix + self.problem},
        ]


def build_probe_plan(config: ProbeConfig, items: Sequence[ProbeItem]) -> list[ProbeTask]:
    config.validate()
    if len(items) != config.planned_items:
        raise ValueError("planned_item_count_mismatch")
    seen: set[str] = set()
    for item in items:
        item.validate()
        if item.item_id in seen:
            raise ValueError("duplicate_item_id")
        seen.add(item.item_id)
    tasks: list[ProbeTask] = []
    order_index = 0
    for item_index, item in enumerate(items):
        start = item_index % len(config.arms) if config.arm_order_policy == "rotating_balanced" else 0
        for offset in range(len(config.arms)):
            arm = config.arms[(start + offset) % len(config.arms)]
            tasks.append(
                ProbeTask(
                    task_id=f"{item.item_id}:{arm.arm_id}",
                    item_id=item.item_id,
                    problem=item.problem,
                    arm_id=arm.arm_id,
                    order_index=order_index,
                    max_tokens=arm.max_tokens,
                    prompt_scope=arm.prompt_scope,
                    prompt_suffix=arm.prompt_suffix,
                )
            )
            order_index += 1
    if len(config.arms) > 1:
        first_arm_counts = Counter(task.arm_id for index, task in enumerate(tasks) if index % len(config.arms) == 0)
        if first_arm_counts and max(first_arm_counts.values()) - min(first_arm_counts.values()) > 1:
            raise ValueError("arm_order_not_balanced")
    return tasks


def _p95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return round(ordered[index], 3)


def build_probe_report(
    config: ProbeConfig,
    rows: Sequence[Mapping[str, Any]],
    *,
    planned_requests: int,
    elapsed_seconds: float,
    dry_run: bool = False,
    stop_reason: str | None = None,
    resumed_completed: int = 0,
    max_active_workers_observed: int = 0,
    active_unresolved_calls: int = 0,
) -> dict[str, Any]:
    row_list = [dict(row) for row in rows]
    dispatched = sum(bool(row.get("dispatched")) for row in row_list)
    completed = sum(bool(row.get("completed")) for row in row_list)
    skipped = sum(row.get("status") == "skipped" for row in row_list)
    timed_out = sum(bool(row.get("timed_out")) for row in row_list)
    late = sum(row.get("status") == "late" for row in row_list)
    errors = Counter(
        normalize_failure_category(row.get("error_category"))
        for row in row_list
        if row.get("error_category")
    )
    formation = Counter(
        (row.get("formation") or {}).get("formation_status", "not_assessed")
        for row in row_list
        if row.get("dispatched")
    )
    latencies = [float(row["latency_seconds"]) for row in row_list if isinstance(row.get("latency_seconds"), (int, float))]
    timeout_latencies = [float(row["latency_seconds"]) for row in row_list if row.get("timed_out") and isinstance(row.get("latency_seconds"), (int, float))]
    actual_tokens = [row["completion_tokens"] for row in row_list if isinstance(row.get("completion_tokens"), int) and row["completion_tokens"] >= 0]
    requested_tokens = [int(row.get("requested_tokens", 0) or 0) for row in row_list if row.get("dispatched")]
    finish_reasons = Counter(str(row.get("finish_reason") or "missing") for row in row_list if row.get("dispatched"))
    scores = Counter(str(row["score"]) for row in row_list if row.get("score") in {"correct", "incorrect", "invalid"})
    unrequested = sum(not bool(row.get("dispatched")) for row in row_list)
    scored = sum(scores.values())
    full_cohort = {
        "planned": int(planned_requests),
        "scored": int(scored),
        "correct": int(scores.get("correct", 0)),
        "incorrect": int(scores.get("incorrect", 0)),
        "invalid": int(scores.get("invalid", 0)),
        "unrequested": int(unrequested),
        "accuracy_over_planned": scores.get("correct", 0) / planned_requests if planned_requests else None,
        "accuracy_over_scored": scores.get("correct", 0) / scored if scored else None,
    }
    ordered_dispatched = sorted(
        (row for row in row_list if row.get("dispatched")),
        key=lambda row: int(row.get("order_index", 0)),
    )[:3]
    first_three_formed_count = sum(
        bool((row.get("formation") or {}).get("complete_candidate"))
        for row in ordered_dispatched
    )
    first_three_gate_triggered = bool(
        config.stop_rules.get("first_three_formed_zero")
        and len(ordered_dispatched) == 3
        and first_three_formed_count == 0
    )
    planned_per_item_tokens = sum(int(arm.max_tokens) for arm in config.arms)
    planned_token_upper_bound = planned_per_item_tokens * int(config.planned_items)
    item_slots = max(
        1,
        int(config.boundary.window_seconds // config.boundary.per_item_seconds),
    )
    capacity_checks = {
        "configuration_validated": True,
        "planned_per_item_tokens": planned_per_item_tokens,
        "planned_token_upper_bound": planned_token_upper_bound,
        "per_item_token_budget_ok": planned_per_item_tokens <= config.boundary.max_requested_tokens_per_item,
        "per_item_time_budget_ok": len(config.arms)
        * (config.boundary.call_wait_seconds + config.boundary.finalization_allowance_seconds)
        <= config.boundary.per_item_seconds,
        "window_item_capacity_estimate": config.boundary.max_workers * item_slots,
        "window_capacity_ok": config.planned_items <= config.boundary.max_workers * item_slots,
        "stop_rules_frozen": bool(config.stop_rules),
    }
    void_reasons: list[str] = []
    if len(row_list) < planned_requests:
        void_reasons.append("incomplete_records")
    if any(row.get("artifact_persistence_error") for row in row_list):
        void_reasons.append("artifact_persistence_failure")
    max_error_rate = float(config.stop_rules.get("max_model_error_rate", 1.0))
    error_rate_denominator = dispatched
    if error_rate_denominator and sum(errors.values()) / error_rate_denominator > max_error_rate:
        void_reasons.append("model_error_rate_above_stop_rule")
    if timed_out and not dry_run:
        void_reasons.append("timeout_present")
    if first_three_gate_triggered and not dry_run:
        void_reasons.append("first_three_formed_zero")
    if stop_reason and stop_reason not in {"dry_run_no_dispatch", "completed"}:
        void_reasons.append(stop_reason)
    return {
        "bcomp_version": BCOMP_VERSION,
        "run_id": config.run_id,
        "method_id": config.method_id,
        "status": "completed",
        "dry_run": bool(dry_run),
        "zero_model_calls": bool(dry_run),
        "capability_conclusion": "NONE",
        "planned_requests": int(planned_requests),
        "dispatched_requests": int(dispatched),
        "completed_requests": int(completed),
        "skipped_requests": int(skipped),
        "timed_out_requests": int(timed_out),
        "late_completions": int(late),
        "unrequested_not_model_errors": int(unrequested),
        "resumed_completed": int(resumed_completed),
        "max_active_workers_observed": int(max_active_workers_observed),
        "active_unresolved_calls": int(active_unresolved_calls),
        "requested_tokens": sum(requested_tokens),
        "planned_requested_tokens": planned_token_upper_bound,
        "planned_per_item_tokens": planned_per_item_tokens,
        "capacity_checks": capacity_checks,
        "actual_completion_tokens": sum(actual_tokens) if actual_tokens else None,
        "actual_token_records": len(actual_tokens),
        "actual_token_coverage": (len(actual_tokens) / completed) if completed else None,
        "finish_reason_counts": dict(finish_reasons),
        "failure_category_counts": dict(errors),
        "formation_status_counts": dict(formation),
        "score_counts": dict(scores),
        "full_cohort": full_cohort,
        "first_three_formation_gate": {
            "enabled": bool(config.stop_rules.get("first_three_formed_zero")),
            "observed": len(ordered_dispatched),
            "formed_count": first_three_formed_count,
            "triggered": first_three_gate_triggered,
        },
        "average_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "p95_latency_seconds": _p95(latencies),
        "p95_includes_timeouts": bool(timeout_latencies),
        "timeout_censored_latency_count": len(timeout_latencies),
        "max_latency_seconds": round(max(latencies), 3) if latencies else None,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "stop_reason": stop_reason,
        "void": bool(void_reasons) if not dry_run else False,
        "void_reasons": void_reasons,
        "temporary_answer_bank": config.bank_mode,
        "actual_route": config.actual_route,
        "protocol": {
            "parser_version": config.parser_version,
            "scorer_version": config.scorer_version,
            "arm_order_policy": config.arm_order_policy,
        },
        "deadline_capability_matrix": deadline_capability_matrix(),
        "disposition": "ZERO_MODEL_DRY_RUN_VALIDATED" if dry_run else "RUN_COMPLETE_NO_CAPABILITY_CONCLUSION",
    }


class BoundedProbeRunner:
    """A capped, single-call-per-task runner with no implicit retry."""

    def __init__(
        self,
        config: ProbeConfig,
        *,
        output_dir: Path | str | None = None,
        observer: BoundedCompletionObserver | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.clock = clock or time.monotonic
        self.store = observer.store if observer is not None else ArtifactStore(self.output_dir) if self.output_dir is not None else None
        self.observer = observer or (
            BoundedCompletionObserver(self.store, run_id=config.run_id, clock=self.clock)
            if self.store is not None
            else NullCompletionObserver()
        )
        self._write_lock = threading.RLock()

    def _write_manifest(self, payload: Mapping[str, Any]) -> None:
        if self.output_dir is None:
            return
        _atomic_write(self.output_dir / "run_manifest.json", json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n")

    def _write_report(self, report: Mapping[str, Any]) -> None:
        if self.output_dir is None:
            return
        _atomic_write(self.output_dir / "report.json", json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n")

    def _append_row(self, row: Mapping[str, Any]) -> None:
        if self.output_dir is None:
            return
        path = self.output_dir / "answers.jsonl"
        line = _canonical_json(dict(row)) + "\n"
        with self._write_lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            _recover_partial_tail(path)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def _existing_rows(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.output_dir / "answers.jsonl") if self.output_dir is not None else []

    def _skip_row(self, task: ProbeTask, reason: str) -> dict[str, Any]:
        refusal_category = (
            FAILURE_BUDGET_REFUSAL
            if reason == FAILURE_BUDGET_REFUSAL
            else FAILURE_DEADLINE_REFUSAL
            if reason == FAILURE_DEADLINE_REFUSAL
            else None
        )
        return {
            "task_id": task.task_id,
            "item_id": task.item_id,
            "arm_id": task.arm_id,
            "order_index": task.order_index,
            "status": "skipped",
            "dispatched": False,
            "completed": False,
            "timed_out": False,
            "requested_tokens": task.max_tokens,
            "error_category": refusal_category,
            "skip_reason": reason,
        }

    def _first_three_formed_zero(self, rows: Sequence[Mapping[str, Any]]) -> bool:
        if not self.config.stop_rules.get("first_three_formed_zero"):
            return False
        dispatched = sorted(
            (row for row in rows if row.get("dispatched")),
            key=lambda row: int(row.get("order_index", 0)),
        )[:3]
        return len(dispatched) == 3 and not any(
            bool((row.get("formation") or {}).get("complete_candidate"))
            for row in dispatched
        )

    def _mark_pending_skipped(self, pending: Sequence[ProbeTask], rows: list[dict[str, Any]], reason: str) -> None:
        for task in pending:
            row = self._skip_row(task, reason)
            rows.append(row)
            self._append_row(row)

    def run(
        self,
        items: Sequence[ProbeItem],
        *,
        client_factory: Callable[[], Any] | None = None,
        dry_run: bool = False,
        allow_real_model_calls: bool = False,
        scorer: Callable[[ProbeTask, Mapping[str, Any]], str] | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        if not dry_run and not allow_real_model_calls:
            raise ValueError("real_model_calls_require_explicit_opt_in")
        if not dry_run and client_factory is None:
            raise ValueError("client_factory_required_for_live_run")
        if not dry_run and not isinstance(self.observer, BoundedCompletionObserver):
            raise ValueError("live_run_requires_diagnostic_store")
        if self.output_dir is not None:
            manifest_path = self.output_dir / "run_manifest.json"
            if manifest_path.exists():
                try:
                    previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ValueError("existing_manifest_unreadable") from exc
                if previous_manifest.get("run_id") != self.config.run_id:
                    raise ValueError("output_dir_belongs_to_another_run")
                if not resume and (self.output_dir / "answers.jsonl").exists():
                    raise ValueError("existing_run_requires_resume")
        plan = build_probe_plan(self.config, items)
        started = self.clock()
        if self.store is not None:
            self.store.prepare()
        existing = self._existing_rows() if resume else []
        existing_by_id = {str(row.get("task_id")): row for row in existing if row.get("task_id")}
        rows: list[dict[str, Any]] = list(existing)
        pending = [task for task in plan if task.task_id not in existing_by_id]
        manifest = {
            "bcomp_version": BCOMP_VERSION,
            "run_id": self.config.run_id,
            "method_id": self.config.method_id,
            "status": "running",
            "started_at_utc": _utc_now(),
            "zero_model_calls": bool(dry_run),
            "planned_requests": len(plan),
            "config": self.config.as_dict(),
            "deadline_capability_matrix": deadline_capability_matrix(),
            "answers": "answers.jsonl",
            "events": "events.jsonl",
            "artifacts": "artifacts.jsonl",
            "assessments": "assessments.jsonl",
        }
        self._write_manifest(manifest)
        if dry_run:
            for task in pending:
                row = self._skip_row(task, "dry_run_no_dispatch")
                rows.append(row)
                self._append_row(row)
            report = build_probe_report(
                self.config,
                rows,
                planned_requests=len(plan),
                elapsed_seconds=self.clock() - started,
                dry_run=True,
                stop_reason="dry_run_no_dispatch",
                resumed_completed=len(existing),
            )
            self._write_report(report)
            manifest.update({"status": "completed", "ended_at_utc": _utc_now(), "report": report})
            self._write_manifest(manifest)
            return report

        started_items: dict[str, float] = {}
        active: dict[str, tuple[ProbeTask, CallHandle, threading.Thread]] = {}
        result_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        stop_reason: str | None = None
        item_active: set[str] = set()
        max_active_workers_observed = 0
        active_unresolved_calls = 0

        def launch(task: ProbeTask) -> None:
            nonlocal max_active_workers_observed
            context = {
                "run_id": self.config.run_id,
                "item_id": task.item_id,
                "arm_id": task.arm_id,
                "problem": task.problem,
            }
            handle = self.observer.start_call(
                stage="probe",
                requested_tokens=task.max_tokens,
                context=context,
                attempt=1,
            )
            started_items.setdefault(task.item_id, self.clock())

            def worker() -> None:
                response: Any = None
                completion_tokens: int | None = None
                finish_reason: str | None = None
                error_category: str | None = None
                try:
                    client = client_factory()  # type: ignore[misc]
                    response = client.chat(task.messages(self.config), self.config.temperature, task.max_tokens)
                    content, completion_tokens, finish_reason, unpack_error = _public_response(response)
                    error_category = unpack_error
                    assessment = assess_formation(
                        task.problem,
                        content,
                        finish_reason,
                        parser_version=self.config.parser_version,
                    )
                except BaseException as exc:  # one task failure is durable and bounded
                    error_category = classify_exception(exc)
                    assessment = None
                self.observer.finish_call(
                    handle,
                    response=response,
                    error_category=error_category,
                    finish_reason=finish_reason,
                    completion_tokens=completion_tokens,
                    duration_ms=int(max(0.0, self.clock() - handle.started_monotonic) * 1000),
                    assessment=assessment,
                )
                result_queue.put(
                    {
                        "task": task,
                        "handle": handle,
                        "response": response,
                        "completion_tokens": completion_tokens,
                        "finish_reason": finish_reason,
                        "error_category": error_category,
                        "assessment": assessment,
                        "artifact_persistence_error": getattr(self.observer, "failure_reason", None),
                        "latency_seconds": max(0.0, self.clock() - handle.started_monotonic),
                    }
                )

            thread = threading.Thread(target=worker, name="bcomp-call", daemon=True)
            active[task.task_id] = (task, handle, thread)
            item_active.add(task.item_id)
            max_active_workers_observed = max(max_active_workers_observed, len(active))
            thread.start()

        while pending or active:
            if stop_reason is None:
                while pending and len(active) < self.config.boundary.max_workers:
                    if self.clock() - started >= self.config.boundary.window_seconds:
                        stop_reason = "window_hard_stop"
                        break
                    candidate_index = next(
                        (index for index, task in enumerate(pending) if task.item_id not in item_active),
                        None,
                    )
                    if candidate_index is None:
                        break
                    task = pending.pop(candidate_index)
                    item_started = started_items.setdefault(task.item_id, self.clock())
                    elapsed = self.clock() - item_started
                    allowed, reason = self.config.boundary.admit(
                        item_elapsed_seconds=elapsed,
                        calls_used=sum(row.get("item_id") == task.item_id and row.get("dispatched") for row in rows),
                        requested_tokens=sum(int(row.get("requested_tokens", 0) or 0) for row in rows if row.get("item_id") == task.item_id and row.get("dispatched")),
                        requested_this_call=task.max_tokens,
                        window_elapsed_seconds=self.clock() - started,
                    )
                    if not allowed:
                        row = self._skip_row(task, reason)
                        if reason in {FAILURE_BUDGET_REFUSAL, FAILURE_DEADLINE_REFUSAL}:
                            self.observer.record_refusal(
                                stage="probe",
                                requested_tokens=task.max_tokens,
                                category=reason,
                                reason=reason,
                                context={
                                    "run_id": self.config.run_id,
                                    "item_id": task.item_id,
                                    "arm_id": task.arm_id,
                                },
                                attempt=1,
                            )
                        rows.append(row)
                        self._append_row(row)
                        continue
                    try:
                        launch(task)
                    except (ArtifactPersistenceError, OSError) as exc:
                        row = self._skip_row(task, "artifact_persistence_failure")
                        row["artifact_persistence_error"] = type(exc).__name__
                        rows.append(row)
                        self._append_row(row)
                        stop_reason = "artifact_persistence_failure"
                        break
            if not active:
                if pending and stop_reason is None:
                    stop_reason = "item_serialization_deadlock"
                if pending:
                    self._mark_pending_skipped(pending, rows, stop_reason or "window_hard_stop")
                    pending = []
                break
            remaining_window = self.config.boundary.window_seconds - (self.clock() - started)
            next_item_deadline = min(
                (
                    min(
                        started_items.get(task.item_id, started) + self.config.boundary.per_item_seconds,
                        handle.started_monotonic + self.config.boundary.call_wait_seconds,
                    )
                    for task, handle, _ in active.values()
                ),
                default=started + self.config.boundary.window_seconds,
            ) - self.clock()
            wait_seconds = max(0.0, min(0.05, remaining_window, next_item_deadline))
            try:
                result = result_queue.get(timeout=wait_seconds)
            except queue.Empty:
                now = self.clock()
                if now - started >= self.config.boundary.window_seconds:
                    stop_reason = "window_hard_stop"
                elif any(
                    now - handle.started_monotonic >= self.config.boundary.call_wait_seconds
                    for _task, handle, _thread in active.values()
                ):
                    stop_reason = "call_wait_deadline"
                elif any(
                    now - started_items.get(task.item_id, now) >= self.config.boundary.per_item_seconds
                    for task, _handle, _thread in active.values()
                ):
                    stop_reason = "active_call_unresolved"
                if stop_reason:
                    active_unresolved_calls = len(active)
                    for task, handle, _thread in list(active.values()):
                        self.observer.record_timeout(handle, reason=stop_reason)
                        row = {
                            "task_id": task.task_id,
                            "item_id": task.item_id,
                            "arm_id": task.arm_id,
                            "order_index": task.order_index,
                            "status": "timed_out",
                            "dispatched": True,
                            "completed": False,
                            "timed_out": True,
                            "requested_tokens": task.max_tokens,
                            "completion_tokens": None,
                            "finish_reason": None,
                            "error_category": FAILURE_TIMEOUT,
                            "latency_seconds": max(0.0, now - handle.started_monotonic),
                            "remote_cancellation": "unknown",
                            "local_work_unit": "unresolved_or_unknown",
                        }
                        rows.append(row)
                        self._append_row(row)
                    active.clear()
                    item_active.clear()
                    if pending:
                        self._mark_pending_skipped(pending, rows, stop_reason)
                        pending = []
                continue
            task = result["task"]
            active.pop(task.task_id, None)
            item_active.discard(task.item_id)
            category = _classify_response(
                _public_response(result.get("response"))[0],
                result.get("error_category"),
            )
            row = {
                "task_id": task.task_id,
                "item_id": task.item_id,
                "arm_id": task.arm_id,
                "order_index": task.order_index,
                "status": "completed" if category is None else "failed",
                "dispatched": True,
                "completed": True,
                "timed_out": False,
                "requested_tokens": task.max_tokens,
                "completion_tokens": result.get("completion_tokens"),
                "finish_reason": result.get("finish_reason"),
                "error_category": category,
                "latency_seconds": round(float(result.get("latency_seconds", 0.0)), 3),
                "formation": result.get("assessment"),
            }
            if result.get("artifact_persistence_error"):
                row["artifact_persistence_error"] = result["artifact_persistence_error"]
                stop_reason = "artifact_persistence_failure"
            if scorer is not None and result.get("assessment") is not None:
                row["score"] = scorer(task, result["assessment"])
            rows.append(row)
            try:
                self._append_row(row)
            except OSError:
                row["artifact_persistence_error"] = "answers_append_failed"
                stop_reason = "artifact_persistence_failure"
                if pending:
                    self._mark_pending_skipped(pending, rows, stop_reason)
                    pending = []
            if stop_reason is None and self._first_three_formed_zero(rows):
                stop_reason = "first_three_formed_zero"
        if stop_reason is None:
            stop_reason = "completed"
        report = build_probe_report(
            self.config,
            rows,
            planned_requests=len(plan),
            elapsed_seconds=self.clock() - started,
            dry_run=False,
            stop_reason=stop_reason,
            resumed_completed=len(existing),
            max_active_workers_observed=max_active_workers_observed,
            active_unresolved_calls=active_unresolved_calls,
        )
        self._write_report(report)
        manifest.update({"status": "completed", "ended_at_utc": _utc_now(), "report": report})
        self._write_manifest(manifest)
        return report


def default_candidate_protocol() -> dict[str, Any]:
    return {
        "protocol_id": CANDIDATE_PROTOCOL_ID,
        "parser_version": PARSER_VERSION,
        "request_shape": "ordinary_free_format",
        "candidate_boundary": "existing HostParser/TypedParser contract",
        "formation_states": [
            "no_response",
            "incomplete_response",
            "candidate_incomplete_or_ambiguous",
            "complete_candidate",
        ],
        "support_source": "independent field; model, bank, host, or unknown",
        "recovery_source": "independent field; none or bounded recovery",
        "terminal_rules": [
            "A complete-looking intermediate expression is not terminal when its answer shape does not fit.",
            "A truncated response with a candidate remains a candidate, not a verified answer.",
            "A missing response or malformed response is not a mathematical incorrect answer.",
        ],
        "forbidden": [
            "parser relaxation to inflate formation",
            "hidden answer lookup",
            "model-generated arbitrary code",
            "implicit retry after timeout",
        ],
    }


__all__ = [
    "ArtifactPersistenceError",
    "ArtifactStore",
    "BCOMP_VERSION",
    "BoundaryPolicy",
    "BoundedCompletionObserver",
    "BoundedProbeRunner",
    "CANDIDATE_PROTOCOL_ID",
    "CallHandle",
    "DeadlineCapability",
    "FAILURE_BUDGET_REFUSAL",
    "FAILURE_CANCELLED",
    "FAILURE_CATEGORIES",
    "FAILURE_DEADLINE_REFUSAL",
    "FAILURE_EMPTY",
    "FAILURE_MALFORMED",
    "FAILURE_TIMEOUT",
    "FAILURE_TRANSPORT",
    "FAILURE_UNKNOWN",
    "METHOD_ID",
    "NullCompletionObserver",
    "PARSER_VERSION",
    "ProbeArm",
    "ProbeConfig",
    "ProbeItem",
    "ProbeTask",
    "assess_formation",
    "build_probe_plan",
    "build_probe_report",
    "classify_exception",
    "deadline_capability_matrix",
    "default_candidate_protocol",
    "normalize_failure_category",
    "replay_formations",
    "sha256_file",
    "sha256_text",
]
