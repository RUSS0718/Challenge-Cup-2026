"""Run the preregistered typed-answer formation probe for the Deep lane."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dataclasses import replace
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from reasoning_agent.math_harness import HostRouter  # noqa: E402
from user_agent import ReasoningAgent, SUBMISSION_CONFIG  # noqa: E402


RUN_ID = "MATH-DEEP-FORMATION-PROBE-001"
PHASE = "deep_typed_answer_formation_probe"
METHOD_ID = "typed_contract_adaptive_deep_v1"
HARNESS_VERSION = "MATH-HARNESS-V1"
SOURCE_DATASET = Path("sample_data/external_hard_sets/set_a_olymmath_hard.jsonl")
SELECTION_IDS = (
    "OlymMATH-HARD-34-EN",
    "OlymMATH-HARD-47-EN",
    "OlymMATH-HARD-53-EN",
    "OlymMATH-HARD-57-EN",
    "OlymMATH-HARD-90-EN",
    "OlymMATH-HARD-95-EN",
)
EXPECTED_ITEMS = len(SELECTION_IDS)
WORKERS = 3
REQUEST_TIMEOUT_SECONDS = 1_200
PER_ITEM_WALL_SECONDS = 1_200.0
WINDOW_HARD_STOP_SECONDS = 7_200.0
MAX_CALLS = 3
MAX_REQUESTED_TOKENS = 16_384
DEEP_PRIMARY_TOKENS = 8_192
DEEP_REVIEW_TOKENS = 4_096
DEEP_CONTINUATION_TOKENS = 4_096
DEEP_CRITIC_TOKENS = 4_096
TEMPERATURE = 0.6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def formation_config():
    """Return the explicit bank-off Deep profile without changing defaults."""
    return replace(
        SUBMISSION_CONFIG,
        enable_constraint_fit_harness=True,
        enable_constraint_fit_deep_lane=True,
        enable_constraint_fit_hybrid_router=False,
        enable_temporary_answer_bank=False,
        harness_bank_mode="off",
        harness_max_model_calls=MAX_CALLS,
        harness_total_token_budget=MAX_REQUESTED_TOKENS,
        harness_max_wall_seconds=PER_ITEM_WALL_SECONDS,
        harness_deep_primary_max_tokens=DEEP_PRIMARY_TOKENS,
        harness_deep_review_max_tokens=DEEP_REVIEW_TOKENS,
        harness_deep_continuation_max_tokens=DEEP_CONTINUATION_TOKENS,
        harness_deep_critic_max_tokens=DEEP_CRITIC_TOKENS,
        harness_deep_max_model_calls=MAX_CALLS,
    )


def _load_items(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {str(row.get("item_id")): row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("source_dataset_contains_duplicate_item_ids")
    router = HostRouter(deep_enabled=True, hybrid_enabled=False)
    selected: list[dict[str, Any]] = []
    for item_id in SELECTION_IDS:
        row = by_id.get(item_id)
        if row is None or not isinstance(row.get("problem"), str) or not row["problem"].strip():
            raise ValueError(f"formation_selection_missing:{item_id}")
        decision = router.route(row["problem"])
        if decision.target != "harness" or decision.lane != "deep":
            raise ValueError(f"formation_item_not_deep:{item_id}")
        # Keep only prompt-safe fields. The source contains public gold, but
        # the answer is deliberately not copied into the request item.
        selected.append(
            {
                "item_id": item_id,
                "source_family": str(row.get("source_family", "")),
                "problem_group_id": str(row.get("problem_group_id", "")),
                "language": str(row.get("language", "")),
                "domain": str(row.get("domain", "")),
                "problem": row["problem"],
                "contract": decision.contract.as_dict(),
            }
        )
    return selected


def _safe_error(exc: BaseException) -> str:
    category = getattr(exc, "category", None)
    allowed = {
        "timeout", "rate_limit", "configuration", "connectivity", "proxy",
        "tls", "http_status", "invalid_response", "request", "client_error",
    }
    return str(category) if category in allowed else "client_error"


def _strip_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_sensitive(item)
            for key, item in value.items()
            if key not in {"prompt", "content", "response", "problem", "gold", "answer"}
        }
    if isinstance(value, list):
        return [_strip_sensitive(item) for item in value]
    return value


def _compact_trace(trace: Any) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    return [
        _strip_sensitive(entry)
        for entry in trace
        if isinstance(entry, dict)
    ]


def _trace_entry(trace: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    return next((entry for entry in reversed(trace) if entry.get("stage") == stage), {})


def solve_one(item: dict[str, Any], timeout: int = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    started = time.perf_counter()
    top_level_error: str | None = None
    runtime: dict[str, Any] = {}
    try:
        # One client and one agent belong to one solve; no state crosses items.
        client = InternChatClient(timeout=timeout, retry=1, thinking_mode=None)
        runtime = {
            key: value
            for key, value in client.diagnostic_snapshot().items()
            if key in {"model", "api_host", "thinking_mode"}
        }
        result = ReasoningAgent(client=client, config=formation_config()).solve(
            item["problem"], {"source_id": item["item_id"]}
        )
    except BaseException as exc:
        top_level_error = _safe_error(exc)
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}

    final_response = result.get("final_response") if isinstance(result, dict) else None
    trace = _compact_trace(result.get("trace", []) if isinstance(result, dict) else [])
    ledger = _trace_entry(trace, "evidence_ledger")
    route = _trace_entry(trace, "route")
    gateway = _trace_entry(trace, "submission_gateway")
    budget = ledger.get("budget") if isinstance(ledger.get("budget"), dict) else {}
    calls = budget.get("records") if isinstance(budget.get("records"), list) else []
    typed_parses = ledger.get("typed_parses") if isinstance(ledger.get("typed_parses"), list) else []
    typed_complete = any(
        isinstance(parse, dict) and bool(parse.get("typed_complete"))
        for parse in typed_parses
    )
    call_errors = [
        call for call in calls
        if isinstance(call, dict) and call.get("status") == "error"
    ]
    timeout_seen = any(
        isinstance(call, dict) and call.get("error_category") == "timeout"
        for call in call_errors
    )
    model_error = bool(top_level_error) or bool(call_errors)
    output_contract_ok = isinstance(final_response, str) and bool(final_response.strip())
    bank_violation = gateway.get("bank_mode") != "off" or gateway.get("status") != "disabled"
    route_ok = route.get("target") == "harness" and route.get("lane") == "deep"
    return {
        "item_id": item["item_id"],
        "problem_group_id": item["problem_group_id"],
        "domain": item["domain"],
        "language": item["language"],
        "status": "model_error" if model_error else "ok",
        "top_level_error": top_level_error,
        "runtime": runtime,
        "route_ok": route_ok,
        "problem_contract": route.get("problem_contract", item["contract"]),
        "typed_complete": typed_complete,
        "typed_parse_statuses": [
            str(parse.get("status", "unknown"))
            for parse in typed_parses
            if isinstance(parse, dict)
        ],
        "typed_parse_reasons": [
            str(parse.get("reason", "unknown"))[:160]
            for parse in typed_parses
            if isinstance(parse, dict)
        ],
        "model_error": model_error,
        "timeout": timeout_seen,
        "output_contract_ok": output_contract_ok,
        "bank_mode": gateway.get("bank_mode"),
        "bank_status": gateway.get("status"),
        "bank_violation": bank_violation,
        "model_calls": int(budget.get("calls", 0) or 0),
        "requested_tokens": int(budget.get("requested_tokens", 0) or 0),
        "actual_completion_tokens": budget.get("actual_completion_tokens"),
        "actual_token_records": int(budget.get("actual_token_records", 0) or 0),
        "budget_violated": bool(budget.get("budget_violated", False)),
        "finish_reasons": [
            str(call.get("finish_reason") or "missing")[:32]
            for call in calls
            if isinstance(call, dict)
        ],
        "call_error_categories": [
            str(call.get("error_category"))
            for call in call_errors
            if isinstance(call, dict)
        ],
        "duration_seconds": round(time.perf_counter() - started, 3),
        "trace": trace,
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return ordered[index]


def build_report(
    rows: list[dict[str, Any]],
    elapsed_seconds: float,
    *,
    final: bool,
    stopped_early: bool = False,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    ordered = [
        row for item_id in SELECTION_IDS
        for row in rows
        if row.get("item_id") == item_id
    ]
    typed_count = sum(bool(row.get("typed_complete")) for row in ordered)
    errors = sum(bool(row.get("model_error")) for row in ordered)
    timeouts = sum(bool(row.get("timeout")) for row in ordered)
    first_three = ordered[:3]
    first_three_typed = sum(bool(row.get("typed_complete")) for row in first_three)
    first_three_stop = len(first_three) == 3 and first_three_typed == 0
    health_violations: list[str] = []
    if len(ordered) != EXPECTED_ITEMS:
        health_violations.append("incomplete_records")
    if errors:
        health_violations.append("model_error_present")
    if timeouts:
        health_violations.append("timeout_present")
    if any(not row.get("route_ok") for row in ordered):
        health_violations.append("route_violation")
    if any(row.get("bank_violation") for row in ordered):
        health_violations.append("bank_mode_violation")
    if any(not row.get("output_contract_ok") for row in ordered):
        health_violations.append("output_contract_violation")
    if any(row.get("budget_violated") for row in ordered):
        health_violations.append("budget_violation")
    if any(int(row.get("model_calls", 0)) > MAX_CALLS for row in ordered):
        health_violations.append("call_cap_violation")
    if any(int(row.get("requested_tokens", 0)) > MAX_REQUESTED_TOKENS for row in ordered):
        health_violations.append("token_cap_violation")
    if first_three_stop:
        health_violations.append("first_three_typed_complete_zero")
    if stopped_early:
        health_violations.append("stopped_early")
    if stop_reason and stop_reason not in health_violations:
        health_violations.append(stop_reason)
    durations = [float(row.get("duration_seconds", 0.0)) for row in ordered]
    calls = [int(row.get("model_calls", 0)) for row in ordered]
    requested = [int(row.get("requested_tokens", 0)) for row in ordered]
    actual = [
        int(row["actual_completion_tokens"])
        for row in ordered
        if isinstance(row.get("actual_completion_tokens"), int)
    ]
    passed = (
        len(ordered) == EXPECTED_ITEMS
        and not health_violations
        and typed_count >= 5
    )
    return {
        "run_id": RUN_ID,
        "phase": PHASE,
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "completed" if final else "running",
        "diagnostic_only": True,
        "dataset_role": "external_public_hard_fresh_formation_probe",
        "temporary_answer_bank": "off",
        "records": len(ordered),
        "expected_records": EXPECTED_ITEMS,
        "typed_complete_rows": typed_count,
        "typed_complete_rate": typed_count / EXPECTED_ITEMS,
        "first_three_records": len(first_three),
        "first_three_typed_complete": first_three_typed,
        "first_three_stop_triggered": first_three_stop,
        "model_errors": errors,
        "timeout_count": timeouts,
        "route_violation_count": sum(not row.get("route_ok") for row in ordered),
        "output_contract_failure_count": sum(not row.get("output_contract_ok") for row in ordered),
        "total_model_calls": sum(calls),
        "average_model_calls": sum(calls) / len(ordered) if ordered else 0.0,
        "p95_model_calls": _p95([float(value) for value in calls]),
        "total_requested_tokens": sum(requested),
        "average_requested_tokens": sum(requested) / len(ordered) if ordered else 0.0,
        "actual_completion_tokens_known": sum(actual) if actual else None,
        "actual_token_record_count": len(actual),
        "finish_reason_counts": dict(Counter(
            reason for row in ordered for reason in row.get("finish_reasons", [])
        )),
        "average_duration_seconds": sum(durations) / len(ordered) if ordered else 0.0,
        "p95_duration_seconds": _p95(durations),
        "max_duration_seconds": max(durations, default=0.0),
        "health_violations": health_violations,
        "health_pass": not health_violations,
        "formation_gate": {
            "required_typed_complete_rows": 5,
            "actual_typed_complete_rows": typed_count,
            "required_model_errors": 0,
            "actual_model_errors": errors,
            "required_timeouts": 0,
            "actual_timeouts": timeouts,
            "pass": passed,
        },
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "capability_conclusion": "NONE",
        "disposition": "FORMATION_PASS_NO_CAPABILITY_CONCLUSION" if passed else "NO_GO / NO_CAPABILITY_CONCLUSION",
    }


def _write_progress(
    output_dir: Path,
    rows_by_id: dict[str, dict[str, Any]],
    started: float,
    *,
    final: bool = False,
    stopped_early: bool = False,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    rows = [
        rows_by_id[item_id]
        for item_id in SELECTION_IDS
        if item_id in rows_by_id
    ]
    _atomic_write(
        output_dir / "answers.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    report = build_report(
        rows,
        time.perf_counter() - started,
        final=final,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def run(
    output_dir: Path,
    *,
    workers: int = WORKERS,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    hard_stop: float = WINDOW_HARD_STOP_SECONDS,
) -> dict[str, Any]:
    if not 1 <= workers <= 3:
        raise ValueError("workers must be between 1 and 3")
    if output_dir.exists():
        allowed_frozen_files = {"protocol_snapshot.md", "dataset_manifest.json"}
        existing_names = {path.name for path in output_dir.iterdir()}
        if existing_names - allowed_frozen_files:
            raise RuntimeError("formation_output_dir_already_has_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = ROOT / SOURCE_DATASET
    spec_path = ROOT / "docs" / "experiments" / "MATH-HARNESS-V1-SPEC" / "spec.md"
    items = _load_items(source)
    started = time.perf_counter()
    manifest: dict[str, Any] = {
        "run_id": RUN_ID,
        "phase": PHASE,
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "running",
        "started_at_utc": _now(),
        "source_dataset": str(SOURCE_DATASET),
        "source_dataset_sha256": _sha256(source),
        "spec_sha256": _sha256(spec_path),
        "selection_ids": list(SELECTION_IDS),
        "records_expected": EXPECTED_ITEMS,
        "freshness": {
            "relative_to": [
                "MATH-HARNESS-EVAL112-SMOKE-001",
                "CAR-002C-ENDPOINT-COMPATIBILITY-PROBE-001",
                "FSDF archived hard windows",
            ],
            "selection_is_prompt_safe_only": True,
            "gold_passed_to_agent": False,
        },
        "workers": workers,
        "batch_plan": "first_three_then_remaining_three; stop if first_three_typed_complete_zero",
        "request_timeout_seconds": timeout,
        "per_item_wall_seconds": PER_ITEM_WALL_SECONDS,
        "window_hard_stop_seconds": hard_stop,
        "temporary_answer_bank": "off",
        "thinking_mode": "client_default / thinking_mode=None",
        "temperature": TEMPERATURE,
        "deep_primary_max_tokens": DEEP_PRIMARY_TOKENS,
        "deep_review_max_tokens": DEEP_REVIEW_TOKENS,
        "deep_continuation_max_tokens": DEEP_CONTINUATION_TOKENS,
        "deep_critic_max_tokens": DEEP_CRITIC_TOKENS,
        "logical_calls_per_item_max": MAX_CALLS,
        "total_requested_tokens_per_item_max": MAX_REQUESTED_TOKENS,
        "formation_gate": {
            "typed_complete_minimum": 5,
            "model_errors_maximum": 0,
            "timeouts_maximum": 0,
            "first_three_typed_complete_zero_stop": True,
        },
        "answers": "answers.jsonl",
        "report": "report.json",
        "result": "result.md",
        "zero_model_calls": False,
        "capability_conclusion": "NONE",
    }
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    rows_by_id: dict[str, dict[str, Any]] = {}
    stop_reason: str | None = None
    stopped_early = False
    for batch_index, batch in enumerate((items[:3], items[3:]), start=1):
        if time.perf_counter() - started >= hard_stop:
            stopped_early = True
            stop_reason = "window_hard_stop"
            break
        with ThreadPoolExecutor(max_workers=min(workers, len(batch))) as pool:
            futures = {
                pool.submit(solve_one, item, timeout): item
                for item in batch
            }
            for future in as_completed(futures):
                item = futures[future]
                row = future.result()
                rows_by_id[item["item_id"]] = row
                print(
                    f"[{item['item_id']}] typed_complete={row['typed_complete']} "
                    f"error={row['model_error']} calls={row['model_calls']} "
                    f"duration={row['duration_seconds']:.1f}s",
                    flush=True,
                )
                _write_progress(output_dir, rows_by_id, started)
        if batch_index == 1:
            first_three = [
                rows_by_id[item["item_id"]]
                for item in items[:3]
                if item["item_id"] in rows_by_id
            ]
            if len(first_three) == 3 and not any(row["typed_complete"] for row in first_three):
                stopped_early = True
                stop_reason = "first_three_typed_complete_zero"
                break

    rows = [
        rows_by_id[item_id]
        for item_id in SELECTION_IDS
        if item_id in rows_by_id
    ]
    report = _write_progress(
        output_dir,
        rows_by_id,
        started,
        final=True,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
    )
    runtime_values = [
        row.get("runtime") for row in rows
        if isinstance(row.get("runtime"), dict) and row.get("runtime")
    ]
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now(),
            "records": len(rows),
            "remote_model_calls": report["total_model_calls"],
            "final_void": not report["formation_gate"]["pass"],
            "stopped_early": stopped_early,
            "stop_reason": stop_reason,
            "runtime": runtime_values[0] if runtime_values else {},
            "capability_conclusion": "NONE",
        }
    )
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {RUN_ID}\n\n"
            f"结论：`{report['disposition']}`\n\n"
            f"记录：{report['records']}/{EXPECTED_ITEMS}；typed-complete："
            f"{report['typed_complete_rows']}/{EXPECTED_ITEMS}；model error：{report['model_errors']}；"
            f"timeout：{report['timeout_count']}；前三题 typed-complete："
            f"{report['first_three_typed_complete']}/3。\n\n"
            "本窗使用全新冻结的公开 hard 题，仅验证 Deep lane 的 typed-answer formation；"
            "bank-off，gold 未传给 Agent，不产生数学能力或官方成绩结论。\n"
            + (f"停止原因：`{stop_reason}`。\n" if stop_reason else "")
        ),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/experiments/MATH-DEEP-FORMATION-PROBE-001")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--hard-stop-seconds", type=float, default=WINDOW_HARD_STOP_SECONDS)
    args = parser.parse_args()
    report = run(
        Path(args.output_dir),
        workers=args.workers,
        timeout=args.timeout,
        hard_stop=args.hard_stop_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
