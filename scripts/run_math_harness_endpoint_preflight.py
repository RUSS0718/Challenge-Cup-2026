"""Run the preregistered MATH-HARNESS-V1 endpoint preflight.

This window tests only whether the current official-default thinking endpoint
produces ordinary free-form responses that the new HostParser can extract.
It deliberately does not score answers, use the temporary answer bank, retry
requests, or require a visible candidate marker.
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
from reasoning_agent.math_harness import (  # noqa: E402
    CANDIDATE_PARSED,
    CANDIDATE_TRUNCATED,
    HostParser,
)


EXPERIMENT_ID = "MATH-HARNESS-ENDPOINT-PREFLIGHT-001"
PHASE = "endpoint_preflight"
METHOD_ID = "bounded_evidence_trajectory_selection_v1"
HARNESS_VERSION = "MATH-HARNESS-V1"
SOURCE_DATASET = Path("sample_data/external_hard_sets/set_b_aime.jsonl")
SELECTION_IDS = (
    "aime-2024-I-4",
    "aime-2024-I-3",
    "aime-2024-I-8",
    "aime-2024-I-12",
    "aime-2024-I-11",
    "aime-2024-I-2",
    "aime-2024-II-6",
    "aime-2024-I-7",
    "aime-2024-II-3",
    "aime-2024-I-1",
)
EXPECTED_RECORDS = len(SELECTION_IDS)
MAX_TOKENS = 4_096
TEMPERATURE = 0.6
REQUEST_TIMEOUT_SECONDS = 600
WINDOW_HARD_STOP_SECONDS = 7_200
EXTRACTABLE_GATE = 8

SYSTEM_PROMPT = (
    "You are a careful mathematical problem solver. Solve the problem in "
    "ordinary free-form prose. Do not use a special output protocol or tags. "
    "Conclude clearly; for a numerical or exact-answer problem, put the final "
    "result on its own last line."
)
USER_PROMPT_PREFIX = "Solve the following problem.\n\n"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _safe_error_category(exc: BaseException) -> str:
    category = getattr(exc, "category", None)
    if category in {"timeout", "rate_limit", "configuration", "connectivity", "proxy", "tls", "http_status", "invalid_response", "request"}:
        return str(category)
    return "client_error"


def _load_items() -> list[dict[str, Any]]:
    source_path = ROOT / SOURCE_DATASET
    by_id: dict[str, dict[str, Any]] = {}
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        item_id = item.get("item_id")
        if isinstance(item_id, str):
            by_id[item_id] = item
    if len(by_id) != len([line for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]):
        raise ValueError("source_dataset_contains_duplicate_item_ids")
    missing = [item_id for item_id in SELECTION_IDS if item_id not in by_id]
    if missing:
        raise ValueError("preflight_selection_missing:" + ",".join(missing))
    # Return only prompt-safe fields.  The source file contains public gold
    # answers, but this preflight never loads them into the request path.
    return [
        {
            "item_id": item_id,
            "source_family": str(by_id[item_id].get("source_family", "")),
            "domain": str(by_id[item_id].get("domain", "")),
            "language": str(by_id[item_id].get("language", "")),
            "answer_type": str(by_id[item_id].get("answer_type", "")),
            "problem": str(by_id[item_id]["problem"]),
        }
        for item_id in SELECTION_IDS
    ]


def classify_response(
    problem: str,
    response: str | None,
    finish_reason: str | None,
    completion_tokens: int | None,
) -> dict[str, Any]:
    """Summarize parser behavior without persisting answer text."""
    text = response if isinstance(response, str) else ""
    parsed = HostParser().parse(
        text,
        problem=problem,
        source="endpoint_preflight",
        finish_reason=finish_reason,
    )
    unique_extractable = (
        len(parsed.candidates) == 1
        and parsed.status in {CANDIDATE_PARSED, CANDIDATE_TRUNCATED}
    )
    return {
        "response_present": bool(text.strip()),
        "response_chars": len(text),
        "finish_reason": str(finish_reason or "")[:32],
        "completion_tokens": int(completion_tokens or 0),
        "parser_status": parsed.status,
        "parser_answer_type": parsed.answer_type,
        "candidate_count": len(parsed.candidates),
        "unique_extractable_candidate": unique_extractable,
        "candidate_stage_sources": [
            str(candidate.source)[:32] for candidate in parsed.candidates[:4]
        ],
        "candidate_value_lengths": [
            len(candidate.value) for candidate in parsed.candidates[:4]
        ],
        "truncated": bool(parsed.truncated),
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return ordered[index]


def _build_report(
    rows: list[dict[str, Any]],
    *,
    elapsed_seconds: float,
    hard_stop_reached: bool,
    runtime: dict[str, Any],
    final: bool,
    stop_reason: str | None = None,
) -> dict[str, Any]:
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
    extraction_sources = Counter(
        source
        for row in rows
        for source in row.get("diagnostic", {}).get("candidate_stage_sources", [])
    )
    latencies = [float(row.get("latency_seconds", 0.0)) for row in rows]
    completion_tokens = [
        int(row.get("diagnostic", {}).get("completion_tokens", 0))
        for row in rows
    ]
    complete = len(rows) == EXPECTED_RECORDS
    void_reasons: list[str] = []
    if not complete:
        void_reasons.append("incomplete_records")
    if errors:
        void_reasons.append("model_error_present")
    if unique_count < EXTRACTABLE_GATE:
        void_reasons.append("unique_extractable_candidate_below_gate")
    if hard_stop_reached:
        void_reasons.append("window_hard_stop")
    if stop_reason:
        void_reasons.append(stop_reason)
    passed = not void_reasons
    return {
        "experiment_id": EXPERIMENT_ID,
        "phase": PHASE,
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "completed" if final else "running",
        "void": not passed if final else bool(void_reasons),
        "void_reasons": void_reasons,
        "records": len(rows),
        "expected_records": EXPECTED_RECORDS,
        "model_error_count": len(errors),
        "timeout_count": sum(row.get("error_category") == "timeout" for row in rows),
        "response_present_count": sum(
            bool(row.get("diagnostic", {}).get("response_present")) for row in rows
        ),
        "unique_extractable_candidate_count": unique_count,
        "unique_extractable_candidate_rate": unique_count / EXPECTED_RECORDS,
        "extractable_gate": EXTRACTABLE_GATE,
        "parser_status_counts": dict(parser_status_counts),
        "finish_reason_counts": dict(finish_reason_counts),
        "candidate_stage_source_counts": dict(extraction_sources),
        "average_latency_seconds": sum(latencies) / len(latencies) if latencies else 0.0,
        "p95_latency_seconds": _p95(latencies),
        "max_latency_seconds": max(latencies, default=0.0),
        "average_completion_tokens": sum(completion_tokens) / len(completion_tokens) if completion_tokens else 0.0,
        "max_completion_tokens": max(completion_tokens, default=0),
        "remote_model_calls": len(rows),
        "temporary_answer_bank": "off",
        "capability_conclusion": "NONE",
        "runtime": dict(runtime),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "disposition": "PASS_FORMAT_PREFLIGHT" if passed else "ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION",
    }


def run(output_dir: Path) -> dict[str, Any]:
    if os.environ.get("INTERN_THINKING_MODE") is not None:
        raise RuntimeError("endpoint_preflight_requires_unset_INTERN_THINKING_MODE")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = ROOT / SOURCE_DATASET
    items = _load_items()
    spec_path = ROOT / "docs" / "experiments" / "MATH-HARNESS-V1-SPEC" / "spec.md"
    started = time.monotonic()
    started_at = _now_utc()
    runtime: dict[str, Any] = {
        "model": None,
        "api_host": None,
        "thinking_mode": "official_default",
        "python": sys.version.split()[0],
    }
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "phase": PHASE,
        "method_id": METHOD_ID,
        "harness_version": HARNESS_VERSION,
        "status": "running",
        "started_at_utc": started_at,
        "source_dataset": str(SOURCE_DATASET),
        "source_dataset_sha256": _sha256(source_path),
        "selection_ids": list(SELECTION_IDS),
        "records_expected": EXPECTED_RECORDS,
        "evaluation_mode": "format_health_only",
        "temporary_answer_bank": "off",
        "thinking_mode": "official_default / client thinking_mode=None",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "logical_calls_per_item": 1,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "window_hard_stop_seconds": WINDOW_HARD_STOP_SECONDS,
        "retry_count": 1,
        "extractable_gate": EXTRACTABLE_GATE,
        "prompt_id": "math_harness_ordinary_free_form_v1",
        "prompt_sha256": hashlib.sha256(
            (SYSTEM_PROMPT + "\n" + USER_PROMPT_PREFIX + "<problem>").encode("utf-8")
        ).hexdigest(),
        "spec_sha256": _sha256(spec_path),
        "answers": "answers.jsonl",
        "report": "report.json",
        "result": "result.md",
        "zero_model_calls": False,
        "capability_conclusion": "NONE",
    }
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rows: list[dict[str, Any]] = []
    hard_stop_reached = False

    for item in items:
        if time.monotonic() - started >= WINDOW_HARD_STOP_SECONDS:
            hard_stop_reached = True
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
            if runtime["model"] is None:
                snapshot = client.diagnostic_snapshot()
                runtime["model"] = snapshot.get("model")
                runtime["api_host"] = snapshot.get("api_host")
            response = client.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_PREFIX + item["problem"],
                    },
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
        except Exception as exc:  # keep the persisted record sanitized
            row["error_category"] = _safe_error_category(exc)
            row["diagnostic"] = classify_response(item["problem"], None, "", 0)
        row["latency_seconds"] = round(time.perf_counter() - request_started, 3)
        rows.append(row)
        _atomic_write(
            output_dir / "answers.jsonl",
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in rows),
        )
        interim = _build_report(
            rows,
            elapsed_seconds=time.monotonic() - started,
            hard_stop_reached=False,
            runtime=runtime,
            final=False,
        )
        _atomic_write(output_dir / "report.json", json.dumps(interim, ensure_ascii=False, indent=2) + "\n")

    report = _build_report(
        rows,
        elapsed_seconds=time.monotonic() - started,
        hard_stop_reached=hard_stop_reached,
        runtime=runtime,
        final=True,
    )
    ended_at = _now_utc()
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": ended_at,
            "records": len(rows),
            "remote_model_calls": len(rows),
            "final_void": bool(report["void"]),
            "capability_conclusion": "NONE",
            "runtime": runtime,
        }
    )
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    result = (
        f"# {EXPERIMENT_ID}\n\n"
        f"结论：`{report['disposition']}`\n\n"
        f"记录：{report['records']}/{EXPECTED_RECORDS}；model error：{report['model_error_count']}；"
        f"唯一可抽取候选：{report['unique_extractable_candidate_count']}/{EXPECTED_RECORDS}；"
        f"finish_reason：{report['finish_reason_counts']}。\n\n"
        "本窗只验证 thinking-on 官方默认端点下的普通自由格式答案抽取，"
        "不要求 CANDIDATE/FINAL marker，不产生数学能力结论，不启动 HEALTH 或 A/B。\n"
    )
    _atomic_write(output_dir / "result.md", result)
    return report


def finalize_existing(output_dir: Path, stop_reason: str) -> dict[str, Any]:
    """Close a deliberately stopped window without issuing another request."""
    manifest_path = output_dir / "run_manifest.json"
    answers_path = output_dir / "answers.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in answers_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    previous_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    report = _build_report(
        rows,
        elapsed_seconds=float(previous_report.get("elapsed_seconds", 0.0)),
        hard_stop_reached=False,
        runtime=dict(manifest.get("runtime") or previous_report.get("runtime") or {}),
        final=True,
        stop_reason=stop_reason,
    )
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now_utc(),
            "records": len(rows),
            "remote_model_calls": len(rows),
            "final_void": True,
            "stopped_early": True,
            "stop_reason": stop_reason,
            "capability_conclusion": "NONE",
        }
    )
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    result = (
        f"# {EXPERIMENT_ID}\n\n"
        f"结论：`{report['disposition']}`\n\n"
        f"记录：{report['records']}/{EXPECTED_RECORDS}；model error：{report['model_error_count']}；"
        f"唯一可抽取候选：{report['unique_extractable_candidate_count']}/{EXPECTED_RECORDS}；"
        f"finish_reason：{report['finish_reason_counts']}。\n\n"
        f"窗口因 `{stop_reason}` 提前停止；已记录的错误足以触发停止门。\n"
        "本窗只验证 thinking-on 官方默认端点下的普通自由格式答案抽取，"
        "不产生数学能力结论，不启动 HEALTH 或 A/B。\n"
    )
    _atomic_write(output_dir / "result.md", result)
    return report


def main() -> int:
    import argparse

    global EXPERIMENT_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="docs/experiments/MATH-HARNESS-ENDPOINT-PREFLIGHT-001",
    )
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="Close an already stopped window without issuing a model request.",
    )
    parser.add_argument(
        "--stop-reason",
        default="stopped_after_irrecoverable_failure",
    )
    parser.add_argument("--experiment-id", default=EXPERIMENT_ID)
    args = parser.parse_args()
    EXPERIMENT_ID = args.experiment_id
    output_dir = Path(args.output_dir)
    report = (
        finalize_existing(output_dir, args.stop_reason)
        if args.finalize_existing
        else run(output_dir)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
