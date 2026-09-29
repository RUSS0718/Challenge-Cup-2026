"""Sanitize agent traces into stage-level evidence for local diagnostics.

This module keeps routing, typed-evidence, budget, and model-call states while
dropping prompts, candidate values, response text, and free-form errors.
"""

import re
from typing import Any


_SAFE_SCALAR_FIELDS = frozenset({
    "method", "stage", "status", "reason", "target", "answer_type",
    "complexity", "lane", "model_calls", "generation_calls",
    "max_model_calls", "harness_version", "fallback_source",
    "selected_branch", "finish_reason", "error_category", "error_type",
    "max_tokens", "duration_seconds", "duration_ms", "candidate_id",
    "schema_valid", "typed_complete", "truncated", "answer_shape",
    "state", "route_confidence", "reasoning_risk", "source",
    "reason_summary", "call_number", "requested_tokens", "completion_tokens",
    "call_limit", "requested_tokens", "token_limit",
    "remaining_requested_tokens", "actual_completion_tokens",
    "actual_token_records", "budget_violated", "prefill_status",
    "prefill_used", "prefill_fallback", "physical_calls", "call_index",
    "logical_call_index", "attempt_index", "request_sequence",
    "http_status", "request_model_id", "response_model_id", "response_id",
    "prompt_tokens", "total_tokens", "response_content_chars", "content_chars",
    "has_reasoning_content", "reasoning_content_chars",
    "attempts_configured", "timeout_seconds", "temperature", "message_count",
    "started_at_utc", "messages_sha256", "api_host", "thinking_mode",
    "selected_skill", "harness_route_id", "harness_steps_expected",
    "harness_steps_completed", "packet_present", "candidate_present",
    "final_present", "handoff_missing_fields", "handoff_conflict_fields",
    "handoff_clipped", "finish_context_clipped", "protocol_error",
})
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_CONTRACT_FIELDS = ("answer_shape", "reasoning_risk", "route_confidence")
_STATE_FIELDS = (
    "state", "reason", "reason_summary", "answer_shape", "status",
    "typed_complete", "truncated", "candidate_id", "schema_valid", "source",
)
_CALL_FIELDS = (
    "stage", "status", "call_number", "call_index", "logical_call_index",
    "attempt_index", "requested_tokens", "completion_tokens", "finish_reason",
    "duration_ms", "duration_seconds", "error_category", "error_type",
    "http_status", "prefill_status", "prefill_used", "prefill_fallback",
    "physical_calls", "has_reasoning_content", "reasoning_content_chars", "content_chars",
)
_BUDGET_FIELDS = (
    "calls", "call_limit", "requested_tokens", "token_limit",
    "remaining_requested_tokens", "actual_completion_tokens",
    "actual_token_records", "budget_violated",
)


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    """Keep short enum-like strings and primitive telemetry values only."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    return None


def _project_fields(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Project a trace object onto allowlisted scalar fields."""
    if not isinstance(row, dict):
        return {}
    return {
        key: safe_value
        for key in fields
        if (safe_value := _safe_scalar(row.get(key))) is not None
    }


def summarize_agent_trace(trace: Any, _depth: int = 0) -> list[dict[str, Any]]:
    """Return ordered route, evidence, call, and final states without content.

    Legacy fallback sub-traces are recursively sanitized so their stages stay
    attributable without serializing candidate values or model responses.
    """
    if not isinstance(trace, list) or _depth > 2:
        return []

    summaries = []
    for event_index, event in enumerate(trace):
        if not isinstance(event, dict):
            continue
        summary = {"event_index": event_index}
        for key in sorted(_SAFE_SCALAR_FIELDS):
            safe_value = _safe_scalar(event.get(key))
            if safe_value is not None:
                summary[key] = safe_value

        contract = _project_fields(event.get("problem_contract"), _CONTRACT_FIELDS)
        if contract:
            summary["problem_contract"] = contract

        route = _project_fields(
            event.get("route"),
            ("target", "answer_type", "complexity", "reason", "lane"),
        )
        if route:
            nested_contract = _project_fields(
                event["route"].get("problem_contract"), _CONTRACT_FIELDS
            )
            if nested_contract:
                route["problem_contract"] = nested_contract
            summary["route"] = route

        for source_key, summary_key in (
            ("states", "states"),
            ("typed_parses", "typed_parses"),
            ("candidates", "candidate_states"),
        ):
            rows = event.get(source_key)
            if isinstance(rows, list):
                projected = [_project_fields(row, _STATE_FIELDS) for row in rows[:16]]
                summary[summary_key] = [row for row in projected if row]

        calls = event.get("calls")
        if isinstance(calls, list):
            projected_calls = [_project_fields(row, _CALL_FIELDS) for row in calls[:32]]
            summary["calls"] = [row for row in projected_calls if row]

        budget = event.get("budget")
        if isinstance(budget, dict):
            budget_summary = _project_fields(budget, _BUDGET_FIELDS)
            records = budget.get("records")
            if isinstance(records, list):
                projected_records = [_project_fields(row, _CALL_FIELDS) for row in records[:32]]
                budget_summary["records"] = [row for row in projected_records if row]
            summary["budget"] = budget_summary

        legacy_trace = event.get("legacy_trace")
        if isinstance(legacy_trace, list):
            summary["legacy_trace"] = summarize_agent_trace(legacy_trace, _depth + 1)

        summaries.append(summary)
    return summaries
