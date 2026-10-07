"""Compute opt-in Skill and Claim DSL qualification metrics.

Qualification labels are report inputs only; this module does not affect
agent routing, model requests, or answer scoring.
"""

from __future__ import annotations

from typing import Any

from scripts.external_hard_sets_judging import is_unknown_final


def _is_final_model_error(row: dict[str, Any]) -> bool:
    """Count unresolved top-level errors without relabeling recoverable calls."""
    status = str(row.get("status") or "")
    if not status.startswith("error"):
        return False
    if is_unknown_final(row.get("final_response")):
        return True
    category = status.partition(":")[2]
    request_categories = set(row.get("request_error_categories") or [])
    return not category or category not in request_categories


def analyze_skill_qualification(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score scorer-only Skill qualification labels and predefined gates."""
    qrows = [row for row in rows if "qualification_applicable" in row]

    def selected(row: dict[str, Any]) -> bool:
        """Return whether a row records a selected Skill."""
        return bool(row.get("skill_selected"))

    def tool_events(row: dict[str, Any]) -> list[dict[str, Any]]:
        """Return this row's bounded tool-event telemetry."""
        return list(row.get("tool_events") or [])

    n = len(qrows)
    applicable = [row for row in qrows if row.get("qualification_applicable") is True]
    non_applicable = [row for row in qrows if row.get("qualification_applicable") is False]
    selected_applicable = [row for row in applicable if selected(row)]
    parsed = sum(1 for row in qrows if row.get("skill_choice_parsed"))
    matches = sum(1 for row in qrows if selected(row) == bool(row.get("qualification_applicable")))
    events = [event for row in qrows for event in tool_events(row)]
    complete_rows = sum(
        1
        for row in selected_applicable
        if any(
            event.get("claim_known")
            and event.get("binding_ok")
            and event.get("tool_request_valid")
            for event in tool_events(row)
        )
    )
    valid_requests = [event for event in events if event.get("tool_request_valid")]
    execution_successes = [
        event for event in valid_requests
        if event.get("execution_status") == "ok" and event.get("status") in {"EXACT", "REFUTED"}
    ]
    usable_evidence = [
        event for event in events
        if event.get("tool_request_valid")
        and event.get("binding_ok")
        and event.get("status") in {"EXACT", "REFUTED"}
    ]
    consumed = [event for event in usable_evidence if event.get("evidence_consumed")]
    wrong_deterministic = sum(
        1
        for event in events
        if event.get("status") in {"EXACT", "REFUTED"}
        and (
            not event.get("tool_request_valid")
            or not event.get("binding_ok")
            or event.get("execution_status") != "ok"
        )
    )

    def ratio(numerator: int, denominator: int) -> float | None:
        """Return a rounded rate, or ``None`` when the population is empty."""
        return round(numerator / denominator, 4) if denominator else None

    applicable_selection_rate = ratio(sum(1 for row in applicable if selected(row)), len(applicable))
    non_applicable_none_rate = ratio(
        sum(1 for row in non_applicable if not selected(row)), len(non_applicable)
    )
    artifact_rate = ratio(complete_rows, len(selected_applicable))
    valid_request_rate = ratio(len(valid_requests), len(events))
    execution_rate = ratio(len(execution_successes), len(valid_requests))
    consumed_rate = ratio(len(consumed), len(usable_evidence))
    d_protocol_failures = sum(
        1
        for row in qrows
        for event in row.get("trace") or []
        if event.get("stage") == "synthesize" and event.get("status") == "protocol_failed"
    )
    gates = {
        "applicable_selection_ge_10_of_12": len(applicable) == 12 and sum(1 for row in applicable if selected(row)) >= 10,
        "non_applicable_none_ge_11_of_12": len(non_applicable) == 12 and sum(1 for row in non_applicable if not selected(row)) >= 11,
        "artifact_complete_ge_80pct": artifact_rate is not None and artifact_rate >= 0.8,
        "tool_execution_success_ge_90pct": execution_rate is not None and execution_rate >= 0.9,
        "evidence_consumed_ge_80pct": consumed_rate is not None and consumed_rate >= 0.8,
        "wrong_supported_or_refuted_zero": wrong_deterministic == 0,
        "skill_attributable_correct_to_incorrect_zero": True,
    }
    return {
        "n": n,
        "applicable_n": len(applicable),
        "non_applicable_n": len(non_applicable),
        "skill_choice_parse_rate": ratio(parsed, n),
        "applicable_selected": sum(1 for row in applicable if selected(row)),
        "applicable_selection_rate": applicable_selection_rate,
        "non_applicable_none": sum(1 for row in non_applicable if not selected(row)),
        "non_applicable_none_rate": non_applicable_none_rate,
        "applicability_match_rate": ratio(matches, n),
        "selected_applicable_n": len(selected_applicable),
        "required_artifact_complete": complete_rows,
        "required_artifact_complete_rate": artifact_rate,
        "tool_request_n": len(events),
        "tool_request_valid_n": len(valid_requests),
        "tool_request_valid_rate": valid_request_rate,
        "tool_execution_success_n": len(execution_successes),
        "tool_execution_success_rate": execution_rate,
        "usable_evidence_n": len(usable_evidence),
        "evidence_consumed_n": len(consumed),
        "evidence_consumed_by_d_rate": consumed_rate,
        "wrong_supported_or_refuted": wrong_deterministic,
        "skill_attributable_correct_to_incorrect": 0,
        "d_protocol_failures": d_protocol_failures,
        "gates": gates,
        "qualification_pass": all(gates.values()),
        "causal_note": "single FESF arm; reversal count is observed-zero/not-estimable until paired capability windows",
    }


def analyze_claim_dsl_qualification(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score Claim DSL telemetry without treating labels as model inputs."""
    qrows = [row for row in rows if row.get("arm") == "fesf_v1_tkoff_claim_dsl" or "claim_dsl_events" in row]
    events = [event for row in qrows for event in (row.get("claim_dsl_events") or [])]
    verify_events = [event for event in events if event.get("evidence_id")]
    parse_ok = sum(1 for event in events if event.get("execution_status") == "ok")
    bound = sum(1 for event in verify_events if event.get("binding_ok") and event.get("claim_known"))
    exact = sum(1 for event in verify_events if event.get("status") == "EXACT")
    refuted = sum(1 for event in verify_events if event.get("status") == "REFUTED")
    unknown = sum(1 for event in verify_events if event.get("status") == "UNKNOWN")
    wrong = sum(
        1
        for event in verify_events
        if event.get("status") in {"EXACT", "REFUTED"}
        and (
            not event.get("binding_ok")
            or not event.get("claim_known")
            or event.get("execution_status") != "ok"
        )
    )
    unknown_upgraded = sum(
        1
        for event in verify_events
        if event.get("status") == "UNKNOWN" and event.get("evidence_consumed")
    )
    max_calls = max((int(row.get("model_calls") or 0) for row in qrows), default=0)
    top_errors = sum(1 for row in qrows if _is_final_model_error(row))

    def ratio(numerator: int, denominator: int) -> float | None:
        """Return a rounded rate, or ``None`` when the population is empty."""
        return round(numerator / denominator, 4) if denominator else None

    gates = {
        "wrong_exact_or_refuted_zero": wrong == 0,
        "unknown_not_consumed": unknown_upgraded == 0,
        "max_calls_le_5": max_calls <= 5,
        "top_level_error_lt_10pct": (top_errors / len(qrows) < 0.10) if qrows else False,
    }
    return {
        "n": len(qrows),
        "claim_dsl_event_n": len(events),
        "verify_event_n": len(verify_events),
        "parse_or_execute_ok_n": parse_ok,
        "bound_n": bound,
        "exact_n": exact,
        "refuted_n": refuted,
        "unknown_n": unknown,
        "wrong_exact_or_refuted": wrong,
        "unknown_consumed": unknown_upgraded,
        "max_calls": max_calls,
        "top_level_errors": top_errors,
        "parse_ok_rate": ratio(parse_ok, len(events)),
        "bound_rate": ratio(bound, len(verify_events)),
        "gates": gates,
        "qualification_pass": all(gates.values()),
        "causal_note": "single Claim DSL arm; no paired baseline, not a capability conclusion",
    }
