"""Run a small submission-profile smoke with request- and stage-level records.

The runner stores no request messages, raw model responses, or credentials.
It records hashes and sanitized status fields needed to attribute UNKNOWNs.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from scripts import run_external_hard_sets_smoke as evaluator
from reasoning_agent.diagnostic_trace import summarize_agent_trace
from user_agent import SUBMISSION_CONFIG, ReasoningAgent

WRITE_LOCK = threading.Lock()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL records without exposing their contents in logs."""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _duration_summary(values: list[float]) -> dict[str, float | None]:
    """Summarize latency samples using the nearest-rank P95 convention."""
    if not values:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(float(value) for value in values)
    p50_index = max(0, int(0.50 * len(ordered) + 0.999999) - 1)
    p95_index = max(0, int(0.95 * len(ordered) + 0.999999) - 1)
    return {
        "mean": round(sum(ordered) / len(ordered), 3),
        "p50": round(ordered[p50_index], 3),
        "p95": round(ordered[p95_index], 3),
        "max": round(ordered[-1], 3),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Write a JSON artifact atomically so interrupted runs keep prior data."""
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _score(result: dict[str, Any], item: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Score only after solve(), using the external-hard runner's frozen judges."""
    gold = item.get("answer")
    set_id = str(item.get("set_id", ""))
    family = item.get("source_family") or evaluator.FAMILIES.get(set_id)
    if gold is None or family not in evaluator.FAMILIES.values():
        return None, None
    pred = evaluator.extract_for_judge(result)
    native = evaluator.judge(pred, str(gold), str(family))
    contract = evaluator.contract_check(str(result.get("final_response") or ""), str(gold), str(family))
    return native, contract


def _request_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-attempt telemetry without collapsing distinct failures."""
    successes = [event for event in events if event.get("status") == "success"]
    failures = [event for event in events if event.get("status") == "error"]
    return {
        "attempts": len(events),
        "successful_responses": len(successes),
        "failed_attempts": len(failures),
        "error_categories": dict(Counter(event.get("error_category", "unknown") for event in failures)),
        "http_statuses": dict(Counter(str(event.get("http_status")) for event in events if event.get("http_status") is not None)),
        "finish_reasons": dict(Counter(event.get("finish_reason", "") for event in successes)),
        "request_model_ids": dict(Counter(event.get("request_model_id", "") for event in events)),
        "response_model_ids": dict(Counter(event.get("response_model_id", "") for event in successes)),
        "prompt_tokens": sum(int(event.get("prompt_tokens") or 0) for event in successes),
        "completion_tokens": sum(int(event.get("completion_tokens") or 0) for event in successes),
        "total_tokens": sum(int(event.get("total_tokens") or 0) for event in successes),
        "latency_seconds": _duration_summary([event.get("duration_seconds", 0) for event in events]),
        "response_model_mismatches": sum(
            isinstance(event.get("response_model_id"), str)
            and isinstance(event.get("request_model_id"), str)
            and event["response_model_id"].casefold() != event["request_model_id"].casefold()
            for event in successes
        ),
    }


def attach_agent_stages_to_requests(
    requests: list[dict[str, Any]], trace: Any
) -> list[dict[str, Any]]:
    """Join request call indices to ordered Harness or legacy stage events."""
    stages_by_call: dict[int, str] = {}

    def collect(events: Any) -> None:
        """Index request stages across Harness and nested legacy traces."""
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            calls = event.get("calls")
            if isinstance(calls, list):
                for call in calls:
                    if isinstance(call, dict):
                        try:
                            call_index = int(call["call_number"]) - 1
                        except (KeyError, TypeError, ValueError):
                            continue
                        stage = call.get("stage")
                        if isinstance(stage, str):
                            stages_by_call.setdefault(call_index, stage)
            stage = event.get("stage")
            status = event.get("status")
            if stage not in {None, "route", "evidence_ledger", "finalize", "legacy_backend"} and status in {"ok", "failed", "error"}:
                try:
                    call_index = int(event.get("model_calls", 0)) - 1
                except (TypeError, ValueError):
                    call_index = -1
                if call_index >= 0 and isinstance(stage, str):
                    stages_by_call.setdefault(call_index, stage)
            collect(event.get("legacy_trace"))

    collect(trace)
    mapped = []
    for request in requests:
        event = dict(request)
        try:
            call_index = int(event.get("logical_call_index"))
        except (TypeError, ValueError):
            call_index = -1
        event["agent_stage"] = stages_by_call.get(call_index, "unmapped")
        mapped.append(event)
    return mapped


def _run_item(
    index: int,
    item: dict[str, Any],
    timeout: int,
    retry: int,
) -> dict[str, Any]:
    """Run one isolated solve and return sanitized client and Agent evidence."""
    item_id = str(item.get("item_id", item.get("idx", index)))
    client = InternChatClient(timeout=timeout, retry=retry)
    agent = ReasoningAgent(client=client, config=dataclasses.replace(SUBMISSION_CONFIG))
    started = time.perf_counter()
    status = "ok"
    error_category = None
    try:
        result = agent.solve(str(item["problem"]), {"idx": item.get("idx", item_id)})
    except Exception as exc:
        status = "solve_error"
        error_category = getattr(exc, "category", type(exc).__name__)
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
    duration = round(time.perf_counter() - started, 3)

    final_response = result.get("final_response", "")
    if not isinstance(final_response, str):
        final_response = ""
    extracted_answer = result.get("extracted_answer", "")
    if not isinstance(extracted_answer, str):
        extracted_answer = ""
    raw_trace = result.get("trace")
    trace = summarize_agent_trace(raw_trace)
    requests = attach_agent_stages_to_requests(list(client.request_diagnostics), raw_trace)
    native, contract = _score(result, item)
    route = next((event for event in trace if event.get("stage") == "route"), {})
    finalize = next((event for event in reversed(trace) if event.get("stage") == "finalize"), {})
    return {
        "idx": item.get("idx", index),
        "item_id": item_id,
        "set_id": item.get("set_id"),
        "domain": item.get("domain"),
        "language": item.get("language"),
        "status": status,
        "error_category": error_category,
        "duration_seconds": duration,
        "final_response_class": "unknown" if final_response.strip().upper() == "UNKNOWN" else "nonempty" if final_response.strip() else "empty",
        "final_response_chars": len(final_response),
        "final_response_sha256": hashlib.sha256(final_response.encode("utf-8")).hexdigest(),
        "extracted_answer_sha256": hashlib.sha256(extracted_answer.encode("utf-8")).hexdigest(),
        "native": native,
        "contract": contract,
        "route_summary": {
            "reason": route.get("reason"),
            "target": route.get("target"),
            "lane": route.get("lane"),
            "answer_type": route.get("answer_type"),
            "complexity": route.get("complexity"),
        },
        "finalize_summary": {
            "status": finalize.get("status"),
            "reason": finalize.get("reason"),
            "model_calls": finalize.get("model_calls"),
        },
        "request_summary": _request_summary(requests),
        "request_diagnostics": requests,
        "agent_trace": trace,
        "client_snapshot": client.diagnostic_snapshot(),
    }


def _build_report(records: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    """Summarize solve outcomes, route states, request failures, and token use."""
    requests = [event for row in records for event in row.get("request_diagnostics", [])]
    routes = Counter(row.get("route_summary", {}).get("reason") or "unclassified" for row in records)
    final_states = Counter(row.get("finalize_summary", {}).get("status") or "unclassified" for row in records)
    native = Counter((row.get("native") or {}).get("verdict", "not_scored") for row in records)
    contract = Counter((row.get("contract") or {}).get("verdict", "not_scored") for row in records)
    by_set = {}
    for set_id in sorted({str(row.get("set_id", "local")) for row in records}):
        group = [row for row in records if str(row.get("set_id", "local")) == set_id]
        set_events = [event for row in group for event in row.get("request_diagnostics", [])]
        by_set[set_id] = {
            "items": len(group),
            "native_verdicts": dict(Counter((row.get("native") or {}).get("verdict", "not_scored") for row in group)),
            "contract_verdicts": dict(Counter((row.get("contract") or {}).get("verdict", "not_scored") for row in group)),
            "route_reasons": dict(Counter(row.get("route_summary", {}).get("reason") or "unclassified" for row in group)),
            "finalize_statuses": dict(Counter(row.get("finalize_summary", {}).get("status") or "unclassified" for row in group)),
            "request_metrics": _request_summary(set_events),
            "item_latency_seconds": _duration_summary([row.get("duration_seconds", 0) for row in group]),
        }
    report = {
        "schema_version": "instrumented-diagnostic-report-v1",
        "run_id": manifest["run_id"],
        "model_id": manifest["model_id"],
        "profile": manifest["profile"],
        "items": len(records),
        "item_statuses": dict(Counter(row.get("status", "unknown") for row in records)),
        "native_verdicts": dict(native),
        "contract_verdicts": dict(contract),
        "unknown_final": sum(row.get("final_response_class") == "unknown" for row in records),
        "route_reasons": dict(routes),
        "finalize_statuses": dict(final_states),
        "requests": _request_summary(requests),
        "requests_by_agent_stage": dict(
            Counter(f"{event.get('agent_stage', 'unmapped')}:{event.get('status', 'unknown')}" for event in requests)
        ),
        "request_errors_by_agent_stage": dict(
            Counter(
                f"{event.get('agent_stage', 'unmapped')}:{event.get('error_category', 'unknown')}"
                for event in requests
                if event.get("status") == "error"
            )
        ),
        "logical_model_calls": sum(
            len({event.get("logical_call_index") for event in row.get("request_diagnostics", [])})
            for row in records
        ),
        "item_latency_seconds": _duration_summary([row.get("duration_seconds", 0) for row in records]),
        "by_set": by_set,
        "items_without_successful_response": sum(
            (row.get("request_summary") or {}).get("successful_responses", 0) == 0
            for row in records
        ),
        "items_with_recorded_failure_category": sum(
            (row.get("request_summary") or {}).get("failed_attempts", 0) > 0
            for row in records
        ),
        "diagnostic_boundary": "All attempted requests are recorded; no request body, response body, or credential is stored.",
    }
    return report


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute a bounded local smoke and persist manifest, records, and report."""
    input_path = Path(args.input_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    answers_path = output_dir / "answers.jsonl"
    if answers_path.exists():
        raise FileExistsError(f"refusing to overwrite {answers_path}")

    items = _load_jsonl(input_path)
    profile = dataclasses.asdict(SUBMISSION_CONFIG)
    profile_json = json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str)
    client_probe = InternChatClient(timeout=args.timeout, retry=args.retry)
    client_info = client_probe.diagnostic_snapshot()
    manifest = {
        "schema_version": "instrumented-diagnostic-run-v1",
        "run_id": args.run_id,
        "profile": "submission",
        "model_id": client_probe.model,
        "api_host": client_info["api_host"],
        "dataset_path": str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else input_path.name,
        "dataset_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "item_ids": [str(item.get("item_id", item.get("idx", i))) for i, item in enumerate(items)],
        "item_count": len(items),
        "workers": args.workers,
        "request_timeout_seconds": args.timeout,
        "retry_count": args.retry,
        "thinking_mode": client_info["thinking_mode"],
        "python_io_encoding": os.environ.get("PYTHONIOENCODING"),
        "agent_config_sha256": hashlib.sha256(profile_json.encode("utf-8")).hexdigest(),
        "agent_config": profile,
        "stores_prompt_text": False,
        "stores_raw_response_text": False,
        "stores_api_key": False,
    }
    _write_json(output_dir / "run_manifest.json", manifest)

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_run_item, index, item, args.timeout, args.retry): (index, item)
            for index, item in enumerate(items)
        }
        for future in as_completed(futures):
            index, item = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {
                    "idx": item.get("idx", index),
                    "item_id": str(item.get("item_id", item.get("idx", index))),
                    "status": "runner_error",
                    "error_category": type(exc).__name__,
                    "request_diagnostics": [],
                    "agent_trace": [],
                }
            encoded = json.dumps(record, ensure_ascii=False, allow_nan=False)
            with WRITE_LOCK, answers_path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            records.append(record)
            print(
                f"[{record.get('item_id')}] status={record.get('status')} "
                f"requests={record.get('request_summary', {}).get('attempts', 0)} "
                f"verdict={(record.get('native') or {}).get('verdict', 'not_scored')}",
                flush=True,
            )

    report = _build_report(records, manifest)
    _write_json(output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def main() -> None:
    """Parse local smoke settings and run the current submission profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retry", type=int, default=1)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout < 1 or args.retry < 1:
        parser.error("workers, timeout, and retry must be positive")
    run(args)


if __name__ == "__main__":
    main()
