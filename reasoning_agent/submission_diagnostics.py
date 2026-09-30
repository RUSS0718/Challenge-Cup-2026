"""Project per-item submission traces into promotion-safe metrics.

The projection keeps route, mode, candidate-formation, recovery, source, and
cost signals while excluding final responses and all model text.
"""

from __future__ import annotations

from collections import Counter
import statistics
from typing import Any, Mapping


def legacy_model_calls(trace: Any) -> int:
    """Recover the bounded FSDF call count from its sanitized sub-trace."""
    if not isinstance(trace, list):
        return 0
    return max(
        (
            int(event.get("model_calls", 0) or 0)
            for event in trace
            if isinstance(event, Mapping)
        ),
        default=0,
    )


def check_record_integrity(
    records: list[Mapping[str, Any]],
    expected_ids: set[Any],
) -> dict[str, Any]:
    """Require exactly one record for every expected item id."""
    ids = [record.get("idx") for record in records]
    counts = Counter(ids)
    duplicate_ids = sorted(
        (item for item, count in counts.items() if count > 1),
        key=str,
    )
    actual_ids = set(ids)
    missing_ids = sorted(expected_ids - actual_ids, key=str)
    extra_ids = sorted(actual_ids - expected_ids, key=str)
    passed = (
        len(records) == len(expected_ids)
        and len(ids) == len(actual_ids)
        and not duplicate_ids
        and not missing_ids
        and not extra_ids
    )
    return {
        "integrity_passed": passed,
        "integrity_record_count": len(records),
        "integrity_expected_count": len(expected_ids),
        "integrity_duplicate_ids": duplicate_ids,
        "integrity_missing_ids": missing_ids,
        "integrity_extra_ids": extra_ids,
    }


def _profile_lane(profile: str) -> str:
    """Map a runner profile to the compact lane label used in reports."""
    normalized = profile.strip().lower()
    if normalized == "submission":
        return "fsdf_baseline"
    if normalized.endswith("-forced-ab"):
        return "forced_ab"
    if normalized.endswith("-adaptive"):
        return "adaptive"
    if normalized.endswith("-on"):
        return "on"
    if normalized.endswith("-off"):
        return "off"
    return normalized


def compact_submission_diagnostics(
    record: Mapping[str, Any],
    profile: str,
) -> dict[str, Any]:
    """Return one response-free diagnostic record for a scored item."""
    summary = record.get("arm_v2_summary")
    arm_active = isinstance(summary, Mapping) and bool(summary)
    summary = summary if isinstance(summary, Mapping) else {}
    modes = record.get("reasoning_modes")
    wire_requests = record.get("wire_requests")
    if not isinstance(wire_requests, list):
        wire_requests = []
    primary_mode = (
        modes[0]
        if arm_active and isinstance(modes, list) and modes and isinstance(modes[0], str)
        else summary.get("solver_reasoning_mode") if arm_active else "n/a"
    )
    verdict = record.get("verdict")
    primary_verdict = record.get("baseline_verdict") if arm_active else None
    failure_reason = record.get("final_failure_reason") or summary.get("final_failure_reason")
    if verdict == "invalid" and not failure_reason:
        failure_reason = "judge_invalid"
    wire_reasoning_modes = [
        request.get("reasoning_mode")
        for request in wire_requests
        if isinstance(request, Mapping) and request.get("reasoning_mode") is not None
    ]
    wire_thinking_modes = [
        request.get("thinking_mode")
        for request in wire_requests
        if isinstance(request, Mapping) and "thinking_mode" in request
    ]
    if not wire_reasoning_modes and isinstance(modes, list):
        wire_reasoning_modes = [mode for mode in modes if isinstance(mode, str)]
    if not wire_thinking_modes:
        wire_thinking_modes = [
            {"off": False, "on": True}.get(mode)
            for mode in wire_reasoning_modes
            if mode in {"off", "on"}
        ]
    second_called = bool(record.get("second_sample_triggered")) if arm_active else False
    resolver_called = bool(record.get("resolver_triggered")) if arm_active else False
    early_stop = bool(summary.get("early_stop")) if arm_active else False
    recovery_action = str(summary.get("on_recovery_action", "")) if arm_active else ""
    recovery_transition = "not_applicable"
    if recovery_action:
        if verdict == "correct":
            recovery_transition = "incomplete_to_correct"
        elif verdict == "incorrect":
            recovery_transition = "incomplete_to_incorrect"
        elif verdict == "invalid":
            recovery_transition = "incomplete_to_incomplete"
    return {
        "harness": (
            "arm_v2.1.3"
            if arm_active and str(profile).startswith("arm-v2.1.3")
            else "arm_v2.1.2"
            if arm_active
            else "fsdf_legacy"
        ),
        "lane": _profile_lane(profile),
        "primary_mode": primary_mode,
        "primary_complete": (
            bool(record.get("primary_candidate_complete")) if arm_active else None
        ),
        "candidate_formation": (
            bool(record.get("primary_candidate_complete")) if arm_active else None
        ),
        "second_called": second_called,
        "resolver_called": resolver_called,
        "final_source": record.get("final_source") or summary.get("final_source") or "unknown",
        "primary_source": record.get("primary_source") or summary.get("primary_source") or "primary",
        "challenger_status": record.get("challenger_status") or summary.get("challenger_status") or "none",
        "replacement_reason": record.get("replacement_reason") or summary.get("replacement_reason") or "",
        "model_calls": int(record.get("model_calls", 0) or 0),
        "wire_reasoning_modes": wire_reasoning_modes,
        "wire_thinking_modes": wire_thinking_modes,
        "primary_thinking_mode": wire_thinking_modes[0] if wire_thinking_modes else None,
        "invalid_reason": failure_reason,
        "verdict": verdict,
        "primary_verdict": primary_verdict,
        "primary_math_status": (
            "correct_local_eval" if primary_verdict == "correct"
            else "incorrect_local_eval" if primary_verdict == "incorrect"
            else "unknown"
        ),
        "trust_decision": dict(summary.get("trust_decision", {})) if arm_active else {},
        "false_trusted_primary": bool(
            arm_active
            and primary_verdict == "incorrect"
            and early_stop
            and not second_called
            and not resolver_called
        ),
        "recovery_transition": recovery_transition,
        "candidate_generation": dict(summary.get("candidate_generation", {})) if arm_active else {},
    }


def summarize_submission_diagnostics(
    records: list[Mapping[str, Any]],
    *,
    profile: str,
    expected_records: int | None = None,
) -> dict[str, Any]:
    """Summarize formation, routing, source, validity, and cost metrics."""
    diagnostics = [compact_submission_diagnostics(record, profile) for record in records]
    calls = [int(item["model_calls"]) for item in diagnostics]
    arm_records = [
        item for item in diagnostics
        if item["harness"] in {"arm_v2.1.2", "arm_v2.1.3"}
    ]
    formed = sum(item["candidate_formation"] is True for item in arm_records)
    second_called = sum(item["second_called"] for item in arm_records)
    resolver_called = sum(item["resolver_called"] for item in arm_records)
    false_trusted = sum(item["false_trusted_primary"] for item in arm_records)
    recovery_transitions = Counter(
        item["recovery_transition"]
        for item in arm_records
        if item["recovery_transition"] != "not_applicable"
    )
    primary_correct = sum(item["primary_verdict"] == "correct" for item in arm_records)
    final_correct = sum(item["verdict"] == "correct" for item in diagnostics)
    rescue_count = sum(
        item["primary_verdict"] != "correct" and item["verdict"] == "correct"
        for item in arm_records
    )
    damage_count = sum(
        item["primary_verdict"] == "correct" and item["verdict"] != "correct"
        for item in arm_records
    )
    final_source_verdicts: dict[str, dict[str, int]] = {}
    for item in diagnostics:
        source = str(item["final_source"])
        bucket = final_source_verdicts.setdefault(
            source,
            {"correct": 0, "incorrect": 0, "invalid": 0, "unknown": 0},
        )
        verdict = item["verdict"] if item["verdict"] in bucket else "unknown"
        bucket[verdict] += 1
    invalid_reasons = Counter(
        str(item["invalid_reason"])
        for item in diagnostics
        if item["invalid_reason"]
    )
    report = {
        "profile": profile,
        "records": len(records),
        "expected_records": expected_records,
        "arm_coverage": len(arm_records),
        "arm_coverage_rate": round(len(arm_records) / len(records), 6) if records else 0.0,
        "candidate_formation_count": formed,
        "candidate_formation_rate": round(formed / len(arm_records), 6) if arm_records else None,
        "primary_correct_count": primary_correct,
        "primary_formed_accuracy": round(primary_correct / formed, 6) if formed else None,
        "primary_accuracy": round(primary_correct / len(records), 6) if records else 0.0,
        "second_sample_count": second_called,
        "second_sample_rate": round(second_called / len(arm_records), 6) if arm_records else 0.0,
        "second_rescue_count": rescue_count,
        "second_rescue_rate": round(rescue_count / second_called, 6) if second_called else 0.0,
        "rescue_count": rescue_count,
        "damage_count": damage_count,
        "final_correct_from_decomposition": primary_correct + rescue_count - damage_count,
        "resolver_count": resolver_called,
        "resolver_rate": round(resolver_called / len(arm_records), 6) if arm_records else 0.0,
        "false_trusted_primary_count": false_trusted,
        "recovery_transition_distribution": dict(recovery_transitions),
        "correct": final_correct,
        "incorrect": sum(item["verdict"] == "incorrect" for item in diagnostics),
        "invalid": sum(item["verdict"] == "invalid" for item in diagnostics),
        "errors": sum(item["verdict"] is None for item in diagnostics),
        "mean_calls_per_problem": round(statistics.mean(calls), 6) if calls else 0.0,
        "final_source_distribution": dict(Counter(str(item["final_source"]) for item in diagnostics)),
        "final_source_verdicts": final_source_verdicts,
        "primary_mode_distribution": dict(Counter(str(item["primary_mode"]) for item in arm_records)),
        "invalid_reason_distribution": dict(invalid_reasons),
    }
    report["accuracy"] = round(report["correct"] / len(records), 6) if records else 0.0
    return report


def promotion_gate(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    max_mean_calls: float = 3.0,
    accuracy_noise_margin: float = 0.0,
) -> dict[str, Any]:
    """Evaluate the conservative Full-30 promotion gate without mutating config."""
    checks = {
        "baseline_complete": bool(baseline.get("integrity_passed", True)),
        "candidate_complete": bool(candidate.get("integrity_passed", True)),
        "correct_not_below_baseline": float(candidate.get("correct", 0))
        >= float(baseline.get("correct", 0))
        - float(accuracy_noise_margin) * float(candidate.get("records", 0) or 0),
        "invalid_not_above_baseline": int(candidate.get("invalid", 0) or 0)
        <= int(baseline.get("invalid", 0) or 0),
        "no_new_runner_errors": int(candidate.get("errors", 0) or 0)
        <= int(baseline.get("errors", 0) or 0),
        "mean_calls_within_budget": float(candidate.get("mean_calls_per_problem", 0.0) or 0.0)
        <= float(max_mean_calls),
    }
    return {
        "status": "PASS" if all(checks.values()) else "NO_GO",
        "checks": checks,
        "baseline_profile": baseline.get("profile"),
        "candidate_profile": candidate.get("profile"),
    }


__all__ = [
    "check_record_integrity",
    "compact_submission_diagnostics",
    "legacy_model_calls",
    "promotion_gate",
    "summarize_submission_diagnostics",
]
