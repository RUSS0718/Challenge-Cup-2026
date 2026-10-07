"""Aggregate hard-set verdicts, stage health, costs, and experiment metrics.

This module consumes completed answer rows only. It has no model-call or
artifact-persistence responsibilities.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.external_hard_sets_judging import (
    contract_check,
    extract_contract_answer,
    is_unknown_final,
)
from scripts.external_hard_sets_qualification import (
    _is_final_model_error,
    analyze_claim_dsl_qualification,
    analyze_skill_qualification,
)

_STAGE_CLIENT_ERROR_CATEGORIES = frozenset({
    "model_error", "timeout", "rate_limit", "http_status", "request",
    "connectivity", "proxy", "tls", "configuration",
})


def stage_health(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count attributable stage failures retained in compacted traces."""
    counters = {
        "stage_client_errors": 0,
        "stage_invalid_responses": 0,
        "stage_protocol_failures": 0,
        "stage_skipped": 0,
        "legacy_client_errors": 0,
        "legacy_timeouts": 0,
        "legacy_invalid_responses": 0,
        "legacy_skipped": 0,
        "handoff_missing": 0,
        "handoff_clipped": 0,
    }
    for row in rows:
        for event in row.get("trace") or []:
            status = event.get("status")
            category = event.get("error_category")
            if status == "failed":
                if category == "invalid_response":
                    counters["stage_invalid_responses"] += 1
                elif category in _STAGE_CLIENT_ERROR_CATEGORIES:
                    counters["stage_client_errors"] += 1
            elif status == "protocol_failed":
                counters["stage_protocol_failures"] += 1
            elif status == "skipped":
                counters["stage_skipped"] += 1
            if event.get("step") == "generate_candidate" and status == "skipped":
                reason = str(event.get("reason") or "").lower()
                if "timeout" in reason:
                    counters["legacy_timeouts"] += 1
                elif "invalid_response" in reason:
                    counters["legacy_invalid_responses"] += 1
                elif "model_call_failed" in reason or "model_error" in reason:
                    counters["legacy_client_errors"] += 1
                else:
                    counters["legacy_skipped"] += 1
            if event.get("handoff_missing_fields"):
                counters["handoff_missing"] += 1
            if event.get("handoff_clipped"):
                counters["handoff_clipped"] += 1
    return counters


def arm_v2_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize v2 trust, sampling, conflict, and resolver outcomes."""
    v2_rows = [
        row for row in rows
        if row.get("arm_v2_summary") or str(row.get("arm", "")).startswith("arm-v2-")
    ]
    trusted_rows = [
        row for row in v2_rows
        if bool(row.get("early_stop")) and row.get("candidate_a_trust") == "high"
    ]
    early_stop_rows = [row for row in v2_rows if bool(row.get("early_stop"))]
    second_sample_rows = [row for row in v2_rows if bool(row.get("second_sample_triggered"))]
    agreement_rows = [row for row in v2_rows if bool(row.get("agreement"))]
    conflict_rows = [
        row for row in v2_rows
        if bool(row.get("conflict"))
        or (bool(row.get("resolver_triggered")) and not bool(row.get("agreement")))
    ]
    resolver_rows = [row for row in v2_rows if bool(row.get("resolver_triggered"))]

    def ratio(numerator: int, denominator: int) -> float:
        """Return a rounded rate, using zero for an empty population."""
        return round(numerator / denominator, 4) if denominator else 0.0

    trusted_correct = sum(row.get("native", {}).get("verdict") == "correct" for row in trusted_rows)
    early_stop_wrong = sum(row.get("native", {}).get("verdict") == "incorrect" for row in early_stop_rows)
    agreement_correct = sum(row.get("native", {}).get("verdict") == "correct" for row in agreement_rows)
    resolver_correct = sum(row.get("native", {}).get("verdict") == "correct" for row in resolver_rows)
    return {
        "v2_n": len(v2_rows),
        "trusted_candidate_n": len(trusted_rows),
        "trusted_candidate_correct_n": trusted_correct,
        "trusted_candidate_precision": ratio(trusted_correct, len(trusted_rows)),
        "early_stop_n": len(early_stop_rows),
        "wrong_early_stop_n": early_stop_wrong,
        "wrong_early_stop_rate": ratio(early_stop_wrong, len(early_stop_rows)),
        "second_sample_n": len(second_sample_rows),
        "second_sample_rate": ratio(len(second_sample_rows), len(v2_rows)),
        "agreement_n": len(agreement_rows),
        "agreement_correct_n": agreement_correct,
        "conflict_n": len(conflict_rows),
        "resolver_n": len(resolver_rows),
        "resolver_correct_n": resolver_correct,
    }


def _nearest_rank_p95(values: list[float | int]) -> float | None:
    """Return the nearest-rank 95th percentile used by experiment reports."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, int(len(ordered) * 0.95 + 0.999)) - 1]


def _row_contract_extractable(row: dict[str, Any]) -> bool:
    """Compute contract extractability, including for pre-fix answer records."""
    if "contract_extractable" in row:
        return bool(row["contract_extractable"])
    return bool(extract_contract_answer(str(row.get("final_response") or ""), str(row.get("source_family") or "")))


def _row_contract_verdict(row: dict[str, Any]) -> str:
    """Use the family-aware contract judger for legacy rows lacking new fields."""
    if "contract_extractable" in row:
        return str(row.get("contract", {}).get("verdict") or "invalid")
    final_response = row.get("final_response")
    gold = row.get("gold")
    family = row.get("source_family")
    if isinstance(final_response, str) and gold is not None and family:
        return contract_check(final_response, str(gold), str(family))["verdict"]
    return str(row.get("contract", {}).get("verdict") or "invalid")


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate verdict, format, timeout, cost, and stage-health statistics."""
    out: dict[str, Any] = {"overall": {}, "by_set": {}}
    contract_verdict_cache = {id(row): _row_contract_verdict(row) for row in rows}

    def stats(subset: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize one overall, arm, domain, set, or language subset."""
        n = len(subset)
        request_events = [
            request
            for row in subset
            for request in row.get("client_request_diagnostics", [])
        ]
        request_errors = [request for request in request_events if request.get("status") == "error"]
        request_timeouts = [
            request for request in request_errors if request.get("error_category") == "timeout"
        ]
        timeout_rows = [
            row for row in subset
            if any(
                request.get("status") == "error" and request.get("error_category") == "timeout"
                for request in row.get("client_request_diagnostics", [])
            )
        ]
        unknown_rows = [row for row in subset if is_unknown_final(row.get("final_response"))]
        recovered_rows = [row for row in timeout_rows if not is_unknown_final(row.get("final_response"))]
        request_latencies = [
            float(request["duration_seconds"])
            for request in request_events
            if isinstance(request.get("duration_seconds"), (int, float))
        ]
        completion_tokens = [
            sum(
                int(token)
                for token in row.get("client_completion_tokens", [])
                if isinstance(token, (int, float))
            )
            for row in subset
        ]
        contract_extractable = sum(1 for row in subset if _row_contract_extractable(row))
        contract_verdicts = [contract_verdict_cache[id(row)] for row in subset]
        legacy_invalid_plus_error = (
            sum(1 for row in subset if row.get("native", {}).get("verdict") == "invalid")
            + sum(1 for row in subset if str(row.get("status", "")).startswith("error"))
            + sum(1 for row in subset for event in row.get("trace") or [] if event.get("step") == "generate_candidate" and event.get("status") == "skipped" and "timeout" in str(event.get("reason") or "").lower())
        )
        failure_union = sum(
            1
            for row in subset
            if row.get("native", {}).get("verdict") == "invalid"
            or _is_final_model_error(row)
        )
        report: dict[str, Any] = {
            "n": n,
            "native_correct": sum(1 for row in subset if row.get("native", {}).get("verdict") == "correct"),
            "native_incorrect": sum(1 for row in subset if row.get("native", {}).get("verdict") == "incorrect"),
            "invalid": sum(1 for row in subset if row.get("native", {}).get("verdict") == "invalid"),
            "contract_correct": sum(verdict == "correct" for verdict in contract_verdicts),
            "contract_incorrect": sum(verdict == "incorrect" for verdict in contract_verdicts),
            "contract_invalid": sum(verdict == "invalid" for verdict in contract_verdicts),
            "verdict_mismatch": sum(
                1
                for row, verdict in zip(subset, contract_verdicts)
                if row.get("native", {}).get("verdict") != verdict
            ),
            "nonempty_final": sum(
                1 for row in subset
                if isinstance(row.get("final_response"), str) and row["final_response"].strip()
            ),
            "contract_extractable": contract_extractable,
            "format_ok": contract_extractable,
            "serializable": sum(1 for row in subset if row.get("json_serializable", False)),
            "model_error": sum(1 for row in subset if _is_final_model_error(row)),
            "unknown_final": len(unknown_rows),
            "timeout_recovered_n": len(recovered_rows),
            "timeout_recovered_correct_n": sum(
                1 for row in recovered_rows if row.get("native", {}).get("verdict") == "correct"
            ),
            "final_unknown_after_timeout_n": sum(1 for row in timeout_rows if is_unknown_final(row.get("final_response"))),
            "no_timeout_abstain_n": sum(1 for row in unknown_rows if row not in timeout_rows),
            "mean_calls": round(sum(int(row.get("model_calls") or 0) for row in subset) / n, 2) if n else 0,
            "max_calls": max((int(row.get("model_calls") or 0) for row in subset), default=0),
            "mean_duration_s": round(sum(float(row.get("duration_seconds") or 0) for row in subset) / n, 1) if n else 0,
            "p95_duration_s": _nearest_rank_p95([float(row.get("duration_seconds") or 0) for row in subset]),
            "mean_completion_tokens": round(sum(completion_tokens) / n, 1) if n else 0,
            "p95_completion_tokens": _nearest_rank_p95(completion_tokens),
            "total_completion_tokens": sum(completion_tokens),
            "request_n": len(request_events),
            "request_error_n": len(request_errors),
            "request_timeout_n": len(request_timeouts),
            "request_error_rate": round(len(request_errors) / len(request_events), 4) if request_events else 0,
            "timeout_rate": round(len(request_timeouts) / len(request_events), 4) if request_events else 0,
            "mean_request_latency_s": round(sum(request_latencies) / len(request_latencies), 2) if request_latencies else None,
            "p95_request_latency_s": _nearest_rank_p95(request_latencies),
            "arm_escalation_n": sum(
                any(event.get("status") == "triggered" for event in (row.get("arm_escalation") or []))
                for row in subset
            ),
            "arm_escalation_rate": round(
                sum(
                    any(event.get("status") == "triggered" for event in (row.get("arm_escalation") or []))
                    for row in subset
                ) / n,
                4,
            ) if n else 0,
            "candidate_formation_n": sum(bool(row.get("candidate_telemetry")) for row in subset),
            "candidate_formation_rate": round(
                sum(bool(row.get("candidate_telemetry")) for row in subset) / n, 4
            ) if n else 0,
        }
        report["native_accuracy"] = round(report["native_correct"] / n, 4) if n else 0
        report["correct_count_consistent"] = report["native_correct"] == report["contract_correct"]
        report.update(arm_v2_metrics(subset))
        report.update(stage_health(subset))
        report["failure_union_n"] = failure_union
        report["invalid_plus_error"] = failure_union
        report["legacy_invalid_plus_error"] = legacy_invalid_plus_error
        return report

    out["overall"] = stats(rows)
    out["judge_note"] = (
        "native 与 contract 均为本地近似判定；native 保留候选等价性诊断，contract 按 source_family "
        "执行格式提取（AIME 只接受整数）。format_ok 等于 contract_extractable；request_timeout_n "
        "是请求级指标，timeout_recovered_n/final_unknown_after_timeout_n 是题目级指标。"
    )
    arms = sorted({str(row.get("arm", "")) for row in rows} - {""})
    if arms:
        out["by_arm"] = {arm: stats([row for row in rows if str(row.get("arm")) == arm]) for arm in arms}
    out["by_domain"] = {
        domain: stats([row for row in rows if row.get("domain") == domain])
        for domain in sorted({row.get("domain") for row in rows if row.get("domain") is not None})
    }
    for set_id in sorted({row.get("set_id") for row in rows if row.get("set_id") is not None}):
        subset = [row for row in rows if row.get("set_id") == set_id]
        entry = stats(subset)
        entry["by_domain"] = {
            domain: stats([row for row in subset if row.get("domain") == domain])
            for domain in sorted({row.get("domain") for row in subset if row.get("domain") is not None})
        }
        entry["by_language"] = dict(Counter(row.get("language", "") for row in subset))
        out["by_set"][set_id] = entry
    if any("qualification_applicable" in row for row in rows):
        out["skill_qualification"] = analyze_skill_qualification(rows)
    if any("claim_dsl_events" in row for row in rows):
        out["claim_dsl_qualification"] = analyze_claim_dsl_qualification(rows)
    return out
