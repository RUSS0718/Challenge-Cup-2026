"""Run the user-authorized, diagnostic-only 112-question Harness evaluation."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from scripts.evaluate_dev import (  # noqa: E402
    classify_problem_type,
    judge_correct,
    load_items,
    validate_regression_items,
)
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG  # noqa: E402


RUN_ID = "MATH-HARNESS-112-DIAGNOSTIC-001"
METHOD_ID = "bounded_evidence_trajectory_selection_v1"
HARNESS_VERSION = "MATH-HARNESS-V1"
DATASET_PATH = Path("sample_data/public_regression_112.jsonl")
EXPECTED_ITEMS = 112
WORKERS = 3
REQUEST_TIMEOUT_SECONDS = 600
HARD_STOP_SECONDS = 21_600
MAX_CALLS = 5
MAX_REQUESTED_TOKENS = 16_384


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _safe_error(exc: BaseException) -> str:
    category = getattr(exc, "category", None)
    allowed = {
        "timeout", "rate_limit", "configuration", "connectivity", "proxy",
        "tls", "http_status", "invalid_response", "request", "client_error",
    }
    return str(category) if category in allowed else "client_error"


def diagnostic_config() -> AgentConfig:
    """Create the explicit bank-off Harness profile without changing defaults."""
    return replace(
        SUBMISSION_CONFIG,
        enable_constraint_fit_harness=True,
        enable_constraint_fit_hybrid_router=False,
        enable_temporary_answer_bank=False,
        harness_bank_mode="off",
        harness_attempt_a_max_tokens=4_096,
        harness_attempt_b_max_tokens=4_096,
        harness_critic_max_tokens=2_048,
        harness_repair_max_tokens=4_096,
        harness_continuation_max_tokens=2_048,
        harness_max_model_calls=MAX_CALLS,
        harness_total_token_budget=MAX_REQUESTED_TOKENS,
        harness_max_wall_seconds=1_200.0,
    )


def _strip_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_sensitive(item)
            for key, item in value.items()
            if key not in {"prompt", "content", "response", "problem"}
        }
    if isinstance(value, list):
        return [_strip_sensitive(item) for item in value]
    return value


def compact_trace(trace: Any) -> list[dict[str, Any]]:
    """Keep decision/evidence metadata while excluding prompt and raw output text."""
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
    result: dict[str, Any]
    top_level_status = "ok"
    top_level_error = None
    try:
        # One client and one agent belong to one solve; no state crosses items.
        client = InternChatClient(timeout=timeout, retry=1, thinking_mode=None)
        agent = ReasoningAgent(client=client, config=diagnostic_config())
        result = agent.solve(item["problem"], {"idx": item.get("idx")})
    except BaseException as exc:
        top_level_status = "model_error"
        top_level_error = _safe_error(exc)
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}

    final_response = result.get("final_response")
    if not isinstance(final_response, str) or not final_response.strip():
        final_response = "UNKNOWN"
    extracted = result.get("extracted_answer", "")
    if not isinstance(extracted, str):
        extracted = ""
    trace = compact_trace(result.get("trace", []))
    ledger = _trace_entry(trace, "evidence_ledger")
    gateway = _trace_entry(trace, "submission_gateway")
    budget = ledger.get("budget") if isinstance(ledger.get("budget"), dict) else {}
    call_records = budget.get("records") if isinstance(budget.get("records"), list) else []
    if not call_records:
        call_records = ledger.get("calls") if isinstance(ledger.get("calls"), list) else []
    call_errors = [
        record for record in call_records
        if isinstance(record, dict) and record.get("status") == "error"
    ]
    timeout_seen = any(record.get("error_category") == "timeout" for record in call_errors)
    model_error = top_level_status == "model_error" or bool(call_errors)
    problem_type = classify_problem_type(item["problem"])
    verdict = judge_correct(extracted, str(item.get("answer", "")), problem_type)
    invalid = not extracted.strip() or final_response.strip().upper() == "UNKNOWN" or verdict == "unknown"
    if model_error:
        outcome = "error"
    elif invalid:
        outcome = "invalid"
    else:
        outcome = verdict
    candidates = ledger.get("candidates") if isinstance(ledger.get("candidates"), list) else []
    candidate_statuses = Counter(
        str(candidate.get("extraction_status", "unknown"))
        for candidate in candidates
        if isinstance(candidate, dict)
    )
    return {
        "idx": item.get("idx"),
        "item_id": str(item.get("idx")),
        "subject": item.get("subject"),
        "problem_type": problem_type,
        "status": top_level_status,
        "top_level_error": top_level_error,
        "final_response": final_response,
        "extracted_answer": extracted,
        "gold": str(item.get("answer", "")),
        "verdict": verdict,
        "outcome": outcome,
        "invalid": invalid,
        "model_error": model_error,
        "timeout": timeout_seen,
        "bank_mode": gateway.get("bank_mode"),
        "bank_status": gateway.get("status"),
        "bank_violation": gateway.get("bank_mode") != "off" or gateway.get("status") != "disabled",
        "model_calls": int(budget.get("calls", 0) or 0),
        "requested_tokens": int(budget.get("requested_tokens", 0) or 0),
        "actual_completion_tokens": budget.get("actual_completion_tokens"),
        "actual_token_records": int(budget.get("actual_token_records", 0) or 0),
        "budget_violated": bool(budget.get("budget_violated", False)),
        "finish_reasons": [
            str(record.get("finish_reason") or "missing")[:32]
            for record in call_records
            if isinstance(record, dict)
        ],
        "call_error_categories": [
            str(record.get("error_category"))
            for record in call_errors
        ],
        "candidate_count": len(candidates),
        "candidate_status_counts": dict(candidate_statuses),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "trace": trace,
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = max(0, min(len(values) - 1, int(len(values) * 0.95 + 0.999) - 1))
    return values[index]


def build_report(rows: list[dict[str, Any]], elapsed_seconds: float, *, final: bool) -> dict[str, Any]:
    total = len(rows)
    outcome_counts = Counter(row.get("outcome", "invalid") for row in rows)
    verdict_counts = Counter(row.get("verdict", "unknown") for row in rows)
    finish_reasons = Counter(
        reason
        for row in rows
        for reason in row.get("finish_reasons", [])
    )
    parser_statuses = Counter(
        status
        for row in rows
        for status, count in row.get("candidate_status_counts", {}).items()
        for _ in range(int(count))
    )
    durations = [float(row.get("duration_seconds", 0.0)) for row in rows]
    calls = [int(row.get("model_calls", 0)) for row in rows]
    requested = [int(row.get("requested_tokens", 0)) for row in rows]
    actual_values = [
        int(row["actual_completion_tokens"])
        for row in rows
        if isinstance(row.get("actual_completion_tokens"), int)
    ]
    complete = total == EXPECTED_ITEMS
    health_violations: list[str] = []
    if not complete:
        health_violations.append("incomplete_records")
    if any(row.get("model_error") for row in rows):
        health_violations.append("model_error_present")
    if any(row.get("bank_violation") for row in rows):
        health_violations.append("bank_mode_violation")
    if any(row.get("budget_violated") for row in rows):
        health_violations.append("budget_violation")
    if any(call > MAX_CALLS for call in calls):
        health_violations.append("call_cap_violation")
    if any(token > MAX_REQUESTED_TOKENS for token in requested):
        health_violations.append("token_cap_violation")
    return {
        "run_id": RUN_ID,
        "phase": "user_authorized_112_diagnostic",
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "completed" if final else "running",
        "diagnostic_only": True,
        "capability_conclusion": "NONE",
        "temporary_answer_bank": "off",
        "records": total,
        "expected_records": EXPECTED_ITEMS,
        "outcome_counts": dict(outcome_counts),
        "verdict_counts": dict(verdict_counts),
        "correct": outcome_counts.get("correct", 0),
        "incorrect": outcome_counts.get("incorrect", 0),
        "invalid": outcome_counts.get("invalid", 0),
        "model_errors": outcome_counts.get("error", 0),
        "timeout_count": sum(bool(row.get("timeout")) for row in rows),
        "accuracy_over_expected": outcome_counts.get("correct", 0) / EXPECTED_ITEMS,
        "decided_accuracy": (
            outcome_counts.get("correct", 0)
            / (outcome_counts.get("correct", 0) + outcome_counts.get("incorrect", 0))
            if outcome_counts.get("correct", 0) + outcome_counts.get("incorrect", 0)
            else None
        ),
        "candidate_status_counts": dict(parser_statuses),
        "candidate_formed_rows": sum(row.get("candidate_count", 0) > 0 for row in rows),
        "total_model_calls": sum(calls),
        "average_model_calls": sum(calls) / total if total else 0.0,
        "p95_model_calls": _p95([float(call) for call in calls]),
        "total_requested_tokens": sum(requested),
        "average_requested_tokens": sum(requested) / total if total else 0.0,
        "actual_completion_tokens_known": sum(actual_values) if actual_values else None,
        "actual_token_record_count": len(actual_values),
        "finish_reason_counts": dict(finish_reasons),
        "average_duration_seconds": sum(durations) / total if total else 0.0,
        "p95_duration_seconds": _p95(durations),
        "max_duration_seconds": max(durations, default=0.0),
        "health_violations": health_violations,
        "health_pass": not health_violations,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "disposition": "DIAGNOSTIC_COMPLETE_NO_CAPABILITY_CONCLUSION" if complete else "DIAGNOSTIC_INCOMPLETE_NO_CAPABILITY_CONCLUSION",
    }


def _write_progress(output_dir: Path, items: list[dict[str, Any]], rows_by_id: dict[str, dict[str, Any]], started: float, *, final: bool = False) -> dict[str, Any]:
    rows = [rows_by_id[str(item.get("idx"))] for item in items if str(item.get("idx")) in rows_by_id]
    _atomic_write(
        output_dir / "answers.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    report = build_report(rows, time.perf_counter() - started, final=final)
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def run(output_dir: Path, *, workers: int = WORKERS, timeout: int = REQUEST_TIMEOUT_SECONDS, hard_stop: float = HARD_STOP_SECONDS) -> dict[str, Any]:
    if not 1 <= workers <= 3:
        raise ValueError("workers must be between 1 and 3")
    if os.environ.get("INTERN_THINKING_MODE") is not None:
        raise RuntimeError("diagnostic_run_requires_unset_INTERN_THINKING_MODE")
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = ROOT / DATASET_PATH
    items = load_items(dataset_path)
    validation_errors = validate_regression_items(items)
    if validation_errors:
        raise ValueError(",".join(validation_errors))
    if len(items) != EXPECTED_ITEMS:
        raise ValueError(f"expected_{EXPECTED_ITEMS}_items")
    spec_path = ROOT / "docs" / "experiments" / "MATH-HARNESS-V1-SPEC" / "spec.md"
    started = time.perf_counter()
    manifest = {
        "run_id": RUN_ID,
        "phase": "user_authorized_112_diagnostic",
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "running",
        "started_at_utc": _now(),
        "dataset_path": str(DATASET_PATH),
        "dataset_sha256": _sha256(dataset_path),
        "dataset_items": EXPECTED_ITEMS,
        "workers": workers,
        "request_timeout_seconds": timeout,
        "hard_stop_seconds": hard_stop,
        "per_question_hard_seconds": 1_200,
        "max_model_calls_per_question": MAX_CALLS,
        "max_requested_tokens_per_question": MAX_REQUESTED_TOKENS,
        "temporary_answer_bank": "off",
        "thinking_mode": "official_default / client thinking_mode=None",
        "client_retry": 1,
        "gold_passed_to_agent": False,
        "spec_sha256": _sha256(spec_path),
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip(),
        "answers": "answers.jsonl",
        "report": "report.json",
        "summary": "summary.json",
        "result": "result.md",
        "diagnostic_only": True,
        "capability_conclusion": "NONE",
    }
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rows_by_id: dict[str, dict[str, Any]] = {}
    answers_path = output_dir / "answers.jsonl"
    if answers_path.exists():
        for line in answers_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows_by_id[str(row["item_id"])] = row
    pending = [item for item in items if str(item.get("idx")) not in rows_by_id]
    print(f"[{RUN_ID}] pending={len(pending)} workers={workers} timeout={timeout}s", flush=True)
    next_index = 0
    active: dict[Any, dict[str, Any]] = {}
    hard_stop_reached = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while active or next_index < len(pending):
            while (
                next_index < len(pending)
                and len(active) < workers
                and time.perf_counter() - started < hard_stop
            ):
                item = pending[next_index]
                next_index += 1
                active[pool.submit(solve_one, item, timeout)] = item
            if not active:
                hard_stop_reached = next_index < len(pending)
                break
            done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                row = future.result()
                rows_by_id[str(item.get("idx"))] = row
                print(
                    f"[{row['idx']}] outcome={row['outcome']} calls={row['model_calls']} "
                    f"tokens={row['requested_tokens']} duration={row['duration_seconds']:.0f}s",
                    flush=True,
                )
                _write_progress(output_dir, items, rows_by_id, started)
        if next_index < len(pending):
            hard_stop_reached = True

    rows = [rows_by_id[str(item.get("idx"))] for item in items if str(item.get("idx")) in rows_by_id]
    report = build_report(rows, time.perf_counter() - started, final=True)
    if hard_stop_reached:
        report["health_violations"].append("window_hard_stop")
        report["health_pass"] = False
        report["disposition"] = "DIAGNOSTIC_INCOMPLETE_NO_CAPABILITY_CONCLUSION"
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now(),
            "records": len(rows),
            "remote_model_calls": report["total_model_calls"],
            "hard_stop_reached": hard_stop_reached,
            "final_void": False,
            "capability_conclusion": "NONE",
        }
    )
    _write_progress(output_dir, items, rows_by_id, started, final=True)
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "summary.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {RUN_ID}\n\n"
            f"结论：`{report['disposition']}`\n\n"
            f"记录：{report['records']}/{EXPECTED_ITEMS}；correct={report['correct']}；"
            f"incorrect={report['incorrect']}；invalid={report['invalid']}；"
            f"model_error={report['model_errors']}；timeout={report['timeout_count']}。\n\n"
            "本窗是用户授权的 112 题完整诊断，答案库关闭，Agent 未接收标准答案。"
            "它不解除 endpoint preflight NO_GO，不产生能力晋升结论，也不修改默认提交路径。\n"
        ),
    )
    return report


def finalize_existing(output_dir: Path, stop_reason: str) -> dict[str, Any]:
    """Close an intentionally interrupted diagnostic without new model calls."""
    dataset_path = ROOT / DATASET_PATH
    items = load_items(dataset_path)
    answers_path = output_dir / "answers.jsonl"
    manifest_path = output_dir / "run_manifest.json"
    rows_by_id = {}
    for line in answers_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows_by_id[str(row["idx"])] = row
    rows = [
        rows_by_id[str(item.get("idx"))]
        for item in items
        if str(item.get("idx")) in rows_by_id
    ]
    previous_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    report = build_report(rows, float(previous_report.get("elapsed_seconds", 0.0)), final=True)
    report["health_violations"].append(stop_reason)
    report["health_pass"] = False
    report["disposition"] = "DIAGNOSTIC_STOPPED_EARLY_NO_CAPABILITY_CONCLUSION"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now(),
            "records": len(rows),
            "remote_model_calls": report["total_model_calls"],
            "stopped_early": True,
            "stop_reason": stop_reason,
            "capability_conclusion": "NONE",
        }
    )
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "summary.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {RUN_ID}\n\n"
            f"结论：`{report['disposition']}`\n\n"
            f"记录：{report['records']}/{EXPECTED_ITEMS}；correct={report['correct']}；"
            f"incorrect={report['incorrect']}；invalid={report['invalid']}；"
            f"model_error={report['model_errors']}；timeout={report['timeout_count']}。\n\n"
            f"窗口因 `{stop_reason}` 提前停止；已完成记录保留，未启动新请求。\n"
            "本窗仅用于定位 Harness 的候选抽取/判分边界，不产生能力结论，不修改默认提交路径。\n"
        ),
    )
    return report


def main() -> int:
    global RUN_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/experiments/MATH-HARNESS-112-DIAGNOSTIC-001")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--hard-stop-seconds", type=float, default=HARD_STOP_SECONDS)
    parser.add_argument("--finalize-existing", action="store_true")
    parser.add_argument("--stop-reason", default="stopped_for_actionable_parser_issue")
    args = parser.parse_args()
    RUN_ID = args.run_id
    output_dir = Path(args.output_dir)
    report = (
        finalize_existing(output_dir, args.stop_reason)
        if args.finalize_existing
        else run(output_dir, workers=args.workers, timeout=args.timeout, hard_stop=args.hard_stop_seconds)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
