"""Run the preregistered CAR-001 F1 health probe.

This runner is deliberately small: six paired items, FSDF v1 versus CAR-001,
three workers, official-default thinking (``None``), and a window hard stop.
It reports endpoint and protocol health only; it is not a capability scorer.
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import ChatClientError, InternChatClient  # noqa: E402
from user_agent import ReasoningAgent, SUBMISSION_CONFIG  # noqa: E402


METHOD_ID = "adaptive_candidate_first_v1"
BASELINE_ID = "fsdf_v1"
CAR_ID = "car_001"
DEFAULT_ITEMS = ROOT / "sample_data" / "medium_capability_freeze_60.jsonl"


def load_items(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            if raw.strip():
                rows.append(json.loads(raw))
            if len(rows) >= limit:
                break
    if len(rows) != limit:
        raise ValueError(f"expected {limit} items, found {len(rows)}")
    return rows


def config_for(arm: str):
    if arm == BASELINE_ID:
        return dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_adaptive_candidate_first=False,
            enable_fork_select_deepen_finish=True,
        )
    if arm == CAR_ID:
        return dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_adaptive_candidate_first=True,
            enable_fork_select_deepen_finish=False,
            enable_fesf_v1=False,
            enable_fesf_exact_eval=False,
            enable_fesf_claim_dsl=False,
        )
    raise ValueError(f"unknown arm: {arm}")


def paired_jobs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        first = CAR_ID if index % 2 else BASELINE_ID
        second = BASELINE_ID if first == CAR_ID else CAR_ID
        jobs.extend(
            [
                {"item": item, "arm": first, "pair_order": 0, "item_seq": index},
                {"item": item, "arm": second, "pair_order": 1, "item_seq": index},
            ]
        )
    return jobs


class ProbeFailFastClient:
    """Stop later stages after the first transport error for one F1 task."""

    def __init__(self, client: InternChatClient) -> None:
        self._client = client
        self.failure_category: str | None = None

    def chat(self, messages, temperature, max_tokens):
        if self.failure_category:
            raise ChatClientError(self.failure_category)
        try:
            return self._client.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            self.failure_category = str(getattr(exc, "category", "client_error"))
            raise

    def __getattr__(self, name: str):
        return getattr(self._client, name)

    def diagnostic_snapshot(self) -> dict[str, Any]:
        snapshot = dict(self._client.diagnostic_snapshot())
        snapshot["probe_fail_fast_category"] = self.failure_category
        return snapshot


def solve_one(job: dict[str, Any], timeout: int, retry: int) -> dict[str, Any]:
    item = job["item"]
    arm = job["arm"]
    client = ProbeFailFastClient(InternChatClient(timeout=timeout, retry=retry, thinking_mode=None))
    config = config_for(arm)
    started = time.perf_counter()
    status = "ok"
    try:
        result = ReasoningAgent(client=client, config=config).solve(
            item["problem"], {"idx": item.get("idx", job["item_seq"])}
        )
    except Exception as exc:  # report only a sanitized class/category
        status = f"error:{getattr(exc, 'category', type(exc).__name__)}"
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
    duration = round(time.perf_counter() - started, 3)
    trace = result.get("trace") if isinstance(result, dict) else []
    trace = trace if isinstance(trace, list) else []
    calls = int(trace[-1].get("model_calls") or 0) if trace else 0
    stages = [
        {
            "stage": event.get("stage"),
            "status": event.get("status"),
            "error_category": event.get("error_category"),
            "max_tokens": event.get("max_tokens"),
            "model_calls": event.get("model_calls"),
            "reason": event.get("reason"),
            "source": event.get("source"),
        }
        for event in trace
        if isinstance(event, dict)
    ]
    stage_failures = [
        event for event in stages
        if event.get("status") == "failed" or event.get("error_category")
    ]
    if status == "ok" and stage_failures:
        # A relay can fail closed to UNKNOWN while still returning a normal
        # dictionary.  Health probes must count failed model stages, not only
        # top-level Python exceptions.
        status = f"stage_error:{stage_failures[0].get('error_category') or 'unknown'}"
    return {
        "item_id": item.get("idx", job["item_seq"]),
        "arm": arm,
        "pair_order": job["pair_order"],
        "item_seq": job["item_seq"],
        "status": status,
        "final_response_present": bool(str(result.get("final_response") or "").strip()),
        "extracted_answer_present": bool(str(result.get("extracted_answer") or "").strip()),
        "model_calls": calls,
        "duration_seconds": duration,
        "stage_events": stages,
        "finish_reasons": list(client.finish_reasons),
        "completion_tokens": list(client.completion_tokens),
        "latencies_seconds": [round(value, 3) for value in client.latencies],
        "client_diagnostic": client.diagnostic_snapshot(),
    }


def summarize(records: list[dict[str, Any]], expected: int) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {BASELINE_ID: [], CAR_ID: []}
    for record in records:
        by_arm.setdefault(record["arm"], []).append(record)
    arm_reports: dict[str, Any] = {}
    for arm, rows in by_arm.items():
        model_errors = sum(row["status"] != "ok" for row in rows)
        calls = [row["model_calls"] for row in rows]
        durations = [row["duration_seconds"] for row in rows]
        arm_reports[arm] = {
            "n": len(rows),
            "expected": expected,
            "model_error_count": model_errors,
            "model_error_rate": model_errors / expected if expected else 0.0,
            "missing_results": sum(not row["final_response_present"] for row in rows),
            "stage_error_count": sum(row["status"] != "ok" for row in rows),
            "average_model_calls": sum(calls) / len(calls) if calls else 0.0,
            "max_model_calls": max(calls, default=0),
            "average_duration_seconds": sum(durations) / len(durations) if durations else 0.0,
            "max_duration_seconds": max(durations, default=0.0),
            "finish_reason_counts": _finish_reason_counts(rows),
            "completion_tokens_total": sum(sum(row["completion_tokens"]) for row in rows),
        }
    complete = len(records) == expected * 2
    void_reasons: list[str] = []
    if not complete:
        void_reasons.append("missing_jobs")
    for arm, report in arm_reports.items():
        if report["model_error_count"] >= 2:
            void_reasons.append(f"{arm}_model_error_rate")
    return {
        "method_id": METHOD_ID,
        "phase": "F1_health_probe",
        "baseline_id": BASELINE_ID,
        "records": len(records),
        "expected_records": expected * 2,
        "arm_reports": arm_reports,
        "void": bool(void_reasons),
        "void_reasons": void_reasons,
        "capability_conclusion": "NONE",
    }


def _finish_reason_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for reason in record["finish_reasons"]:
            key = reason or "empty"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _atomic_write(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report(
    records: list[dict[str, Any]],
    limit: int,
    items_path: Path,
    items_sha256: str,
    workers: int,
    timeout: int,
    retry: int,
    started_wall: float,
    started_utc: str,
    hard_stop_seconds: float,
    status: str,
    extra_void_reasons: list[str] | None = None,
) -> dict[str, Any]:
    report = summarize(records, limit)
    reasons = list(report.get("void_reasons") or [])
    for reason in extra_void_reasons or []:
        if reason not in reasons:
            reasons.append(reason)
    report.update(
        {
            "status": status,
            "void": bool(reasons),
            "void_reasons": reasons,
            "unfinished_jobs": max(0, limit * 2 - len(records)),
            "items_path": str(items_path.relative_to(ROOT)),
            "items_sha256": items_sha256,
            "workers": workers,
            "request_timeout_seconds": timeout,
            "retry": retry,
            "thinking_mode": "default",
            "started_at_utc": started_utc,
            "elapsed_seconds": round(time.time() - started_wall, 3),
            "hard_stop_seconds": hard_stop_seconds,
        }
    )
    return report


def _write_checkpoint(
    output_dir: Path,
    records: list[dict[str, Any]],
    limit: int,
    items_path: Path,
    items_sha256: str,
    workers: int,
    timeout: int,
    retry: int,
    started_wall: float,
    started_utc: str,
    hard_stop_seconds: float,
    status: str,
    extra_void_reasons: list[str] | None = None,
) -> dict[str, Any]:
    records.sort(key=lambda row: (row["item_seq"], row["pair_order"]))
    report = _report(
        records, limit, items_path, items_sha256, workers, timeout, retry,
        started_wall, started_utc, hard_stop_seconds, status, extra_void_reasons,
    )
    answers = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
    _atomic_write(output_dir / "answers.jsonl", answers)
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _manifest(
    items_path: Path,
    items_sha256: str,
    limit: int,
    workers: int,
    timeout: int,
    retry: int,
    hard_stop_seconds: float,
    started_utc: str,
    status: str,
    records: int = 0,
    unfinished_jobs: int | None = None,
) -> dict[str, Any]:
    return {
        "method_id": METHOD_ID,
        "phase": "F1_health_probe",
        "status": status,
        "protocol": {
            "baseline": BASELINE_ID,
            "candidate": CAR_ID,
            "items": limit,
            "expected_records": limit * 2,
            "workers": workers,
            "thinking_mode": "official_default",
            "single_question_internal_parallelism": False,
            "health_void_rule": "any arm with >=2 model errors, missing job, or runner exception",
            "window_hard_stop_seconds": hard_stop_seconds,
        },
        "configuration": {
            "baseline": dataclasses.asdict(config_for(BASELINE_ID)),
            "candidate": dataclasses.asdict(config_for(CAR_ID)),
        },
        "items_path": str(items_path.relative_to(ROOT)),
        "items_sha256": items_sha256,
        "started_at_utc": started_utc,
        "records": records,
        "unfinished_jobs": unfinished_jobs if unfinished_jobs is not None else limit * 2 - records,
        "report": "report.json",
        "answers": "answers.jsonl",
        "zero_model_calls": False,
        "capability_conclusion": "NONE",
    }


def run(
    output_dir: Path,
    items_path: Path,
    limit: int,
    timeout: int,
    retry: int,
    workers: int,
    hard_stop_seconds: float = 1200.0,
    solve_fn=solve_one,
) -> dict[str, Any]:
    items_path = items_path.resolve()
    if os.environ.get("INTERN_THINKING_MODE") is not None:
        raise RuntimeError("F1 requires INTERN_THINKING_MODE to be unset for official-default thinking")
    if hard_stop_seconds <= 0:
        raise ValueError("hard_stop_seconds must be positive")
    items = load_items(items_path, limit)
    jobs = paired_jobs(items)
    output_dir.mkdir(parents=True, exist_ok=True)
    items_sha256 = hashlib.sha256(items_path.read_bytes()).hexdigest()
    started_wall = time.time()
    started_mono = time.monotonic()
    started_utc = _now_utc()
    records: list[dict[str, Any]] = []
    _atomic_write(output_dir / "answers.jsonl", "")
    _atomic_write(output_dir / "report.json", json.dumps(_report(
        records, limit, items_path, items_sha256, workers, timeout, retry,
        started_wall, started_utc, hard_stop_seconds, "running",
    ), ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "run_manifest.json", json.dumps(_manifest(
        items_path, items_sha256, limit, workers, timeout, retry,
        hard_stop_seconds, started_utc, "running",
    ), ensure_ascii=False, indent=2) + "\n")

    pool = ThreadPoolExecutor(max_workers=workers)
    active: dict[Any, dict[str, Any]] = {}
    next_index = 0
    stopped = False

    def submit_available() -> None:
        nonlocal next_index
        while next_index < len(jobs) and len(active) < workers:
            if time.monotonic() - started_mono >= hard_stop_seconds:
                return
            job = jobs[next_index]
            next_index += 1
            active[pool.submit(solve_fn, job, timeout, retry)] = job

    def collect(done: set[Any], status: str) -> None:
        for future in done:
            job = active.pop(future, {})
            try:
                records.append(future.result())
            except Exception as exc:
                records.append({
                    "item_id": job.get("item", {}).get("idx", ""),
                    "arm": job.get("arm", "unknown"),
                    "pair_order": job.get("pair_order", 0),
                    "item_seq": job.get("item_seq", -1),
                    "status": f"runner_error:{type(exc).__name__}",
                    "final_response_present": False,
                    "extracted_answer_present": False,
                    "model_calls": 0,
                    "duration_seconds": 0.0,
                    "finish_reasons": [],
                    "completion_tokens": [],
                })
        _write_checkpoint(
            output_dir, records, limit, items_path, items_sha256, workers,
            timeout, retry, started_wall, started_utc, hard_stop_seconds, status,
        )

    try:
        submit_available()
        while active:
            remaining = hard_stop_seconds - (time.monotonic() - started_mono)
            if remaining <= 0:
                stopped = True
                break
            done, _ = wait(set(active), timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                stopped = True
                break
            collect(done, "running")
            submit_available()
            if not active and next_index < len(jobs):
                stopped = True
                break
        if next_index < len(jobs) or active:
            stopped = True
        if stopped:
            for future in list(active):
                future.cancel()
            # Running requests are allowed to drain to their own request
            # timeout; queued futures were never submitted under the bounded
            # active-future policy.
            grace_deadline = time.monotonic() + max(0.0, float(timeout) * max(1, retry))
            while active and time.monotonic() < grace_deadline:
                remaining = grace_deadline - time.monotonic()
                done, _ = wait(set(active), timeout=remaining, return_when=FIRST_COMPLETED)
                if not done:
                    break
                collect(done, "partial_hard_stop")
            report = _write_checkpoint(
                output_dir, records, limit, items_path, items_sha256, workers,
                timeout, retry, started_wall, started_utc, hard_stop_seconds,
                "partial_hard_stop", ["window_hard_stop"],
            )
            unfinished = max(0, len(jobs) - len(records))
            _atomic_write(output_dir / "run_manifest.json", json.dumps(_manifest(
                items_path, items_sha256, limit, workers, timeout, retry,
                hard_stop_seconds, started_utc, "partial_hard_stop",
                records=len(records), unfinished_jobs=unfinished,
            ), ensure_ascii=False, indent=2) + "\n")
            pool.shutdown(wait=False, cancel_futures=True)
            return report
        pool.shutdown(wait=True)
        report = _write_checkpoint(
            output_dir, records, limit, items_path, items_sha256, workers,
            timeout, retry, started_wall, started_utc, hard_stop_seconds, "completed",
        )
        _atomic_write(output_dir / "run_manifest.json", json.dumps(_manifest(
            items_path, items_sha256, limit, workers, timeout, retry,
            hard_stop_seconds, started_utc, "completed", records=len(records), unfinished_jobs=0,
        ), ensure_ascii=False, indent=2) + "\n")
        return report
    except BaseException:
        for future in list(active):
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retry", type=int, default=1)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--hard-stop-seconds", type=float, default=1200.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers < 1 or args.workers > 3:
        raise SystemExit("--workers must be between 1 and 3")
    report = run(
        Path(args.output_dir), Path(args.items), args.limit, args.timeout, args.retry,
        args.workers, hard_stop_seconds=args.hard_stop_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
