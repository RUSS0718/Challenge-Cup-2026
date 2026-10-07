"""Probe the endpoint through the bare public client contract only."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402


EXPERIMENT_ID = "MATH-ENDPOINT-DIRECT-PROBE-001"
MAX_TOKENS = 128
TEMPERATURE = 0.0
REQUEST_TIMEOUT_SECONDS = 90
RETRY_COUNT = 1
CASES = (
    ("plain_text", "Reply with exactly: OK."),
    ("basic_math", "Compute 1+1. Reply with exactly: 2."),
)
REPETITIONS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _category(exc: BaseException) -> str:
    value = getattr(exc, "category", None)
    allowed = {
        "timeout", "rate_limit", "configuration", "connectivity", "proxy",
        "tls", "http_status", "invalid_response", "request",
    }
    return str(value) if value in allowed else "client_error"


def _atomic_write(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def run(output_dir: Path) -> dict[str, Any]:
    if os.environ.get("INTERN_THINKING_MODE") is not None:
        raise RuntimeError("direct_probe_requires_unset_INTERN_THINKING_MODE")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    for case_name, prompt in CASES:
        for repetition in range(REPETITIONS):
            request_started = time.perf_counter()
            row: dict[str, Any] = {
                "case": case_name,
                "repetition": repetition,
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
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    retry=RETRY_COUNT,
                    thinking_mode=None,
                )
                response = client.chat(
                    messages=[
                        {"role": "system", "content": "You are a minimal endpoint probe."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                row["response_present"] = isinstance(response, str) and bool(response.strip())
                row["response_chars"] = len(response) if isinstance(response, str) else 0
                row["finish_reason"] = client.finish_reasons[-1] if client.finish_reasons else ""
                row["completion_tokens"] = client.completion_tokens[-1] if client.completion_tokens else 0
                row["status"] = "ok" if row["response_present"] else "model_error"
                if row["status"] != "ok":
                    row["error_category"] = "invalid_response"
            except Exception as exc:
                row["error_category"] = _category(exc)
            row["latency_seconds"] = round(time.perf_counter() - request_started, 3)
            rows.append(row)
            _atomic_write(
                output_dir / "answers.jsonl",
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
            )
    latencies = [row["latency_seconds"] for row in rows]
    report = {
        "experiment_id": EXPERIMENT_ID,
        "method": "bare_InternChatClient_chat",
        "status": "completed",
        "records": len(rows),
        "expected_records": len(CASES) * REPETITIONS,
        "model_error_count": sum(row["status"] != "ok" for row in rows),
        "timeout_count": sum(row["error_category"] == "timeout" for row in rows),
        "response_present_count": sum(row["response_present"] for row in rows),
        "case_status_counts": {
            case: dict(Counter(row["status"] for row in rows if row["case"] == case))
            for case, _ in CASES
        },
        "case_latency_seconds": {
            case: {
                "mean": (
                    sum(row["latency_seconds"] for row in rows if row["case"] == case)
                    / REPETITIONS
                ),
                "max": max(
                    (row["latency_seconds"] for row in rows if row["case"] == case),
                    default=0.0,
                ),
            }
            for case, _ in CASES
        },
        "mean_latency_seconds": sum(latencies) / len(latencies) if latencies else 0.0,
        "max_latency_seconds": max(latencies, default=0.0),
        "remote_model_calls": len(rows),
        "temporary_answer_bank": "not imported",
        "thinking_mode": "official_default / client thinking_mode=None",
        "max_tokens": MAX_TOKENS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "retry_count": RETRY_COUNT,
        "capability_conclusion": "NONE",
        "diagnostic_conclusion": (
            "simple_direct_requests_fail"
            if any(row["status"] != "ok" for row in rows)
            else "simple_direct_requests_pass"
        ),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "started_at_utc": _now(),
        "method": "bare_InternChatClient_chat",
        "cases": [case for case, _ in CASES],
        "repetitions_per_case": REPETITIONS,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "retry_count": RETRY_COUNT,
        "thinking_mode": "official_default / client thinking_mode=None",
        "temporary_answer_bank": "not imported",
        "answers": "answers.jsonl",
        "report": "report.json",
        "result": "result.md",
        "remote_model_calls": len(rows),
        "capability_conclusion": "NONE",
        "ended_at_utc": _now(),
    }
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {EXPERIMENT_ID}\n\n"
            f"结论：`{report['diagnostic_conclusion']}`\n\n"
            f"记录：{report['records']}/{report['expected_records']}；"
            f"成功响应：{report['response_present_count']}；"
            f"timeout：{report['timeout_count']}；"
            f"平均延迟：{report['mean_latency_seconds']:.3f}s。\n\n"
            "本探针只经过公开 `client.chat(messages, temperature, max_tokens)`，"
            "不经过 ReasoningAgent、Harness、HostParser 或答案库，不产生数学能力结论。\n"
        ),
    )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="docs/experiments/MATH-ENDPOINT-DIRECT-PROBE-001",
    )
    args = parser.parse_args()
    print(json.dumps(run(Path(args.output_dir)), ensure_ascii=False, indent=2))
