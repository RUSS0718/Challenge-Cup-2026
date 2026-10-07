"""Run one bounded retry of the MATH-HARNESS endpoint preflight.

The first preflight is immutable evidence.  This retry is a new window: a
short endpoint-availability gate is followed by the same ten-item ordinary
free-form extraction probe only when the gate is clean.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from scripts.run_math_harness_endpoint_preflight import (  # noqa: E402
    EXTRACTABLE_GATE,
    SELECTION_IDS,
    SOURCE_DATASET,
    SYSTEM_PROMPT,
    USER_PROMPT_PREFIX,
    _load_items,
    _safe_error_category,
    _sha256,
    _atomic_write,
    _now_utc,
    classify_response,
)


EXPERIMENT_ID = "MATH-HARNESS-ENDPOINT-PREFLIGHT-002"
PARENT_EXPERIMENT_ID = "MATH-HARNESS-ENDPOINT-PREFLIGHT-001"
METHOD_ID = "bounded_evidence_trajectory_selection_v1"
HARNESS_VERSION = "MATH-HARNESS-V1"
PRECHECK_REQUESTS = 3
PRECHECK_MAX_TOKENS = 256
PRECHECK_TIMEOUT_SECONDS = 180
PRECHECK_WINDOW_SECONDS = 600
MAX_TOKENS = 4_096
TEMPERATURE = 0.6
REQUEST_TIMEOUT_SECONDS = 600
WINDOW_HARD_STOP_SECONDS = 7_200

PRECHECK_SYSTEM_PROMPT = (
    "You are checking endpoint availability. Answer 1+1 in ordinary prose, "
    "without special markers, and keep the response short."
)
PRECHECK_USER_PROMPT = "Return a short response."


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return ordered[index]


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _precheck(output_dir: Path, started: float) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    for request_index in range(PRECHECK_REQUESTS):
        if time.monotonic() - started >= PRECHECK_WINDOW_SECONDS:
            break
        request_started = time.perf_counter()
        row: dict[str, Any] = {
            "request_index": request_index,
            "status": "model_error",
            "error_category": None,
            "response_present": False,
            "response_chars": 0,
            "finish_reason": "",
            "completion_tokens": 0,
            "latency_seconds": 0.0,
        }
        try:
            client = InternChatClient(
                timeout=PRECHECK_TIMEOUT_SECONDS,
                retry=1,
                thinking_mode=None,
            )
            response = client.chat(
                messages=[
                    {"role": "system", "content": PRECHECK_SYSTEM_PROMPT},
                    {"role": "user", "content": PRECHECK_USER_PROMPT},
                ],
                temperature=TEMPERATURE,
                max_tokens=PRECHECK_MAX_TOKENS,
            )
            row["response_present"] = isinstance(response, str) and bool(response.strip())
            row["response_chars"] = len(response) if isinstance(response, str) else 0
            row["finish_reason"] = client.finish_reasons[-1] if client.finish_reasons else ""
            row["completion_tokens"] = client.completion_tokens[-1] if client.completion_tokens else 0
            row["status"] = "ok" if row["response_present"] else "model_error"
            if row["status"] != "ok":
                row["error_category"] = "invalid_response"
        except Exception as exc:  # persist only a stable category
            row["error_category"] = _safe_error_category(exc)
        row["latency_seconds"] = round(time.perf_counter() - request_started, 3)
        rows.append(row)
        _atomic_write(
            output_dir / "precheck.jsonl",
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
        )
        if row["status"] != "ok":
            break
    passed = (
        len(rows) == PRECHECK_REQUESTS
        and all(row["status"] == "ok" for row in rows)
    )
    return rows, passed


def _build_report(
    precheck: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    elapsed_seconds: float,
    stopped_after_error: bool,
    full_run_started: bool,
) -> dict[str, Any]:
    precheck_errors = [row for row in precheck if row["status"] != "ok"]
    errors = [row for row in rows if row["status"] != "ok"]
    unique_count = sum(
        bool(row.get("diagnostic", {}).get("unique_extractable_candidate"))
        for row in rows
    )
    parser_status_counts = Counter(
        row.get("diagnostic", {}).get("parser_status", "model_error")
        for row in rows
    )
    finish_reason_counts = Counter(
        row.get("diagnostic", {}).get("finish_reason", "") or "missing"
        for row in rows
    )
    latencies = [float(row.get("latency_seconds", 0.0)) for row in rows]
    void_reasons: list[str] = []
    if len(precheck) != PRECHECK_REQUESTS or precheck_errors:
        void_reasons.append("endpoint_availability_precheck_failed")
    if not full_run_started:
        void_reasons.append("full_extraction_probe_not_started")
    if len(rows) != len(SELECTION_IDS):
        void_reasons.append("incomplete_records")
    if errors:
        void_reasons.append("model_error_present")
    if unique_count < EXTRACTABLE_GATE:
        void_reasons.append("unique_extractable_candidate_below_gate")
    if stopped_after_error:
        void_reasons.append("stopped_after_irrecoverable_failure")
    passed = not void_reasons
    return {
        "experiment_id": EXPERIMENT_ID,
        "parent_experiment_id": PARENT_EXPERIMENT_ID,
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "completed",
        "void": not passed,
        "void_reasons": void_reasons,
        "precheck": {
            "records": len(precheck),
            "expected_records": PRECHECK_REQUESTS,
            "model_error_count": len(precheck_errors),
            "response_present_count": sum(row.get("response_present", False) for row in precheck),
            "finish_reason_counts": dict(Counter(row.get("finish_reason", "") or "missing" for row in precheck)),
            "max_latency_seconds": max((row.get("latency_seconds", 0.0) for row in precheck), default=0.0),
            "passed": len(precheck) == PRECHECK_REQUESTS and not precheck_errors,
        },
        "records": len(rows),
        "expected_records": len(SELECTION_IDS),
        "model_error_count": len(errors),
        "timeout_count": sum(row.get("error_category") == "timeout" for row in rows),
        "response_present_count": sum(row.get("diagnostic", {}).get("response_present", False) for row in rows),
        "unique_extractable_candidate_count": unique_count,
        "unique_extractable_candidate_rate": unique_count / len(SELECTION_IDS),
        "extractable_gate": EXTRACTABLE_GATE,
        "parser_status_counts": dict(parser_status_counts),
        "finish_reason_counts": dict(finish_reason_counts),
        "average_latency_seconds": sum(latencies) / len(latencies) if latencies else 0.0,
        "p95_latency_seconds": _p95(latencies),
        "max_latency_seconds": max(latencies, default=0.0),
        "remote_model_calls": len(precheck) + len(rows),
        "temporary_answer_bank": "off",
        "capability_conclusion": "NONE",
        "elapsed_seconds": round(elapsed_seconds, 3),
        "disposition": "PASS_FORMAT_PREFLIGHT" if passed else "ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION",
    }


def run(output_dir: Path) -> dict[str, Any]:
    if os.environ.get("INTERN_THINKING_MODE") is not None:
        raise RuntimeError("endpoint_preflight_retry_requires_unset_INTERN_THINKING_MODE")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = ROOT / SOURCE_DATASET
    spec_path = ROOT / "docs" / "experiments" / "MATH-HARNESS-V1-SPEC" / "spec.md"
    items = _load_items()
    started = time.monotonic()
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "parent_experiment_id": PARENT_EXPERIMENT_ID,
        "phase": "endpoint_preflight_retry",
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "running",
        "started_at_utc": _now_utc(),
        "source_dataset": str(SOURCE_DATASET),
        "source_dataset_sha256": _sha256(source_path),
        "selection_ids": list(SELECTION_IDS),
        "evaluation_mode": "format_health_only",
        "temporary_answer_bank": "off",
        "thinking_mode": "official_default / client thinking_mode=None",
        "temperature": TEMPERATURE,
        "precheck_requests": PRECHECK_REQUESTS,
        "precheck_max_tokens": PRECHECK_MAX_TOKENS,
        "precheck_timeout_seconds": PRECHECK_TIMEOUT_SECONDS,
        "precheck_window_seconds": PRECHECK_WINDOW_SECONDS,
        "logical_calls_per_item": 1,
        "max_tokens": MAX_TOKENS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "window_hard_stop_seconds": WINDOW_HARD_STOP_SECONDS,
        "retry_count": 1,
        "extractable_gate": EXTRACTABLE_GATE,
        "prompt_id": "math_harness_ordinary_free_form_v1",
        "prompt_sha256": hashlib.sha256(
            (SYSTEM_PROMPT + "\n" + USER_PROMPT_PREFIX + "<problem>").encode("utf-8")
        ).hexdigest(),
        "spec_sha256": _sha256(spec_path),
        "precheck": "precheck.jsonl",
        "answers": "answers.jsonl",
        "report": "report.json",
        "result": "result.md",
        "zero_model_calls": False,
        "capability_conclusion": "NONE",
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    precheck, precheck_passed = _precheck(output_dir, started)
    rows: list[dict[str, Any]] = []
    stopped_after_error = bool(precheck and not precheck_passed)
    full_run_started = False
    if precheck_passed:
        full_run_started = True
        for item in items:
            if time.monotonic() - started >= WINDOW_HARD_STOP_SECONDS:
                stopped_after_error = True
                break
            request_started = time.perf_counter()
            row: dict[str, Any] = {
                "item_id": item["item_id"],
                "source_family": item["source_family"],
                "domain": item["domain"],
                "language": item["language"],
                "answer_type": item["answer_type"],
                "status": "model_error",
                "error_category": None,
                "latency_seconds": 0.0,
            }
            try:
                client = InternChatClient(
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    retry=1,
                    thinking_mode=None,
                )
                response = client.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT_PREFIX + item["problem"]},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                finish_reason = client.finish_reasons[-1] if client.finish_reasons else ""
                completion_tokens = client.completion_tokens[-1] if client.completion_tokens else 0
                row["diagnostic"] = classify_response(
                    item["problem"], response, finish_reason, completion_tokens
                )
                row["status"] = "ok"
            except Exception as exc:
                row["error_category"] = _safe_error_category(exc)
                row["diagnostic"] = classify_response(item["problem"], None, "", 0)
            row["latency_seconds"] = round(time.perf_counter() - request_started, 3)
            rows.append(row)
            _atomic_write(
                output_dir / "answers.jsonl",
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in rows),
            )
            if row["status"] != "ok":
                stopped_after_error = True
                break

    report = _build_report(
        precheck,
        rows,
        elapsed_seconds=time.monotonic() - started,
        stopped_after_error=stopped_after_error,
        full_run_started=full_run_started,
    )
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now_utc(),
            "precheck_records": len(precheck),
            "records": len(rows),
            "remote_model_calls": len(precheck) + len(rows),
            "final_void": bool(report["void"]),
            "stopped_after_error": stopped_after_error,
            "capability_conclusion": "NONE",
        }
    )
    _write_json(output_dir / "report.json", report)
    _write_json(output_dir / "run_manifest.json", manifest)
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {EXPERIMENT_ID}\n\n"
            f"结论：`{report['disposition']}`\n\n"
            f"端点短预检：{report['precheck']['records']}/{PRECHECK_REQUESTS}；"
            f"完整预检记录：{report['records']}/{len(SELECTION_IDS)}；"
            f"model error：{report['model_error_count']}；"
            f"唯一可抽取候选：{report['unique_extractable_candidate_count']}/{len(SELECTION_IDS)}。\n\n"
            "本窗是 001 的一次独立、有限重试；不修改 001，不产生数学能力结论，"
            "不启动 HEALTH 或 A/B。\n"
        ),
    )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="docs/experiments/MATH-HARNESS-ENDPOINT-PREFLIGHT-002",
    )
    args = parser.parse_args()
    print(json.dumps(run(Path(args.output_dir)), ensure_ascii=False, indent=2))
