"""V5-HARD20-TYPED-CAPSULE-001 diagnostic runner."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from user_agent import (
    AgentConfig,
    ReasoningAgent,
    SUBMISSION_CONFIG,
    extract_typed_answer,
    answer_equivalence,
)

WRITE_LOCK = threading.Lock()
INTEGER_RE = re.compile(r"^-?\d+$")
UNKNOWN_VALUES = {"", "UNKNOWN", "未能生成有效数学答案。"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def v5_config() -> AgentConfig:
    return dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_typed_answer_capsule=True,
        enable_condition_checked_selection=False,
        enable_plan_solve_compact=False,
        enable_stateful_tail_completion=False,
        max_model_calls=2,
        max_tokens=4096,
        capsule_retry_max_tokens=2048,
    )


def native_score(pred: str, gold: str, family: str) -> str:
    pred = (pred or "").strip()
    gold = (gold or "").strip()
    if pred.upper() in UNKNOWN_VALUES:
        return "invalid"
    if family == "AIME":
        if not INTEGER_RE.fullmatch(pred) or not INTEGER_RE.fullmatch(gold):
            return "invalid"
        return "correct" if int(pred) == int(gold) else "incorrect"
    eq = answer_equivalence(pred, gold)
    if eq == "EQUIVALENT":
        return "correct"
    if eq == "NOT_EQUIVALENT":
        return "incorrect"
    return "invalid"


def compact_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = {
        "step", "status", "reason", "model_calls", "method", "typed",
        "generation_calls", "max_model_calls", "plan_chars",
    }
    return [{k: entry[k] for k in entry if k in keep} for entry in trace]


def solve_one(item: dict[str, Any], timeout: int) -> dict[str, Any]:
    config = v5_config()
    # Client retry=1 means exactly one HTTP attempt (the client loops over
    # range(retry)); the experiment itself does not auto-retry model errors.
    client = InternChatClient(timeout=timeout, retry=1)
    agent = ReasoningAgent(client=client, config=config)
    started = time.perf_counter()
    status = "ok"
    try:
        result = agent.solve(item["problem"], {"idx": item.get("item_id")})
    except Exception as exc:
        status = f"error:{getattr(exc, 'category', type(exc).__name__)}"
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
    duration = time.perf_counter() - started
    final_response = str(result.get("final_response") or "")
    extracted = str(result.get("extracted_answer") or "")
    typed = extract_typed_answer(final_response)
    # The capsule returns a canonical ANSWER line; reparse it as the formal source.
    pred = typed
    native = native_score(pred, str(item.get("answer", "")), item.get("source_family", ""))
    trace = result.get("trace") or []
    retry_entries = [e for e in trace if e.get("step") == "capsule_retry"]
    model_error = status.startswith("error") or any(
        e.get("reason") in {"model_call_failed", "timeout", "empty_model_response"}
        or "error" in str(e.get("reason", "")).lower()
        for e in trace
    )
    return {
        "item_id": item["item_id"],
        "source_family": item["source_family"],
        "language": item["language"],
        "subject": item["subject"],
        "status": status,
        "final_response": final_response,
        "typed_answer": typed,
        "diagnostic_extracted_answer": extracted,
        "native_verdict": native,
        "typed_valid": bool(typed),
        "retry_triggered": bool(retry_entries),
        "model_error": model_error,
        "model_calls": int(trace[-1].get("model_calls") or 0) if trace else 0,
        "duration_seconds": duration,
        "trace": compact_trace(trace),
        "gold": item.get("answer", ""),
    }


def run(output_dir: Path, timeout: int, workers: int, hard_stop: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = output_dir / "official_like_hard20_v1.jsonl"
    answers = output_dir / "answers.jsonl"
    report = output_dir / "report.json"
    items = load_jsonl(dataset)
    if len(items) != 20:
        raise SystemExit(f"expected 20 items, found {len(items)}")
    dataset_sha = sha256_file(dataset)
    done = {r["item_id"] for r in load_jsonl(answers)} if answers.exists() else set()
    pending = [item for item in items if item["item_id"] not in done]
    manifest = {
        "run_id": "V5-HARD20-TYPED-CAPSULE-001",
        "method_id": "typed_answer_capsule_v1",
        "dataset_sha256": dataset_sha,
        "expected_items": 20,
        "pending_items": len(pending),
        "workers": workers,
        "timeout_seconds": timeout,
        "hard_stop_seconds": hard_stop,
        "max_calls_per_item": 2,
        "primary_max_tokens": 4096,
        "retry_max_tokens": 2048,
        "client_retry": 0,
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "start_unix": time.time(),
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[V5] pending={len(pending)} dataset={dataset_sha[:12]} workers={workers}", flush=True)
    started = time.perf_counter()

    def job(item: dict[str, Any]) -> dict[str, Any]:
        if time.perf_counter() - started >= hard_stop:
            return {"skipped": True, "item_id": item["item_id"], "reason": "hard_stop"}
        row = solve_one(item, timeout)
        with WRITE_LOCK:
            with answers.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
        print(
            f"[{row['item_id']}] native={row['native_verdict']} typed={row['typed_valid']} "
            f"retry={row['retry_triggered']} calls={row['model_calls']} dur={row['duration_seconds']:.0f}s",
            flush=True,
        )
        return row

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, item) for item in pending]
        for future in as_completed(futures):
            future.result()

    rows = load_jsonl(answers)
    typed_valid = sum(r["typed_valid"] for r in rows)
    typed_formed = sum(1 for r in rows if r["typed_valid"])
    native_correct = sum(r["native_verdict"] == "correct" for r in rows)
    native_incorrect = sum(r["native_verdict"] == "incorrect" for r in rows)
    invalid = sum(r["native_verdict"] == "invalid" for r in rows)
    model_errors = sum(r["model_error"] for r in rows)
    retries = sum(r["retry_triggered"] for r in rows)
    total_calls = sum(r["model_calls"] for r in rows)
    total = len(rows)
    summary = {
        "run_id": "V5-HARD20-TYPED-CAPSULE-001",
        "method_id": "typed_answer_capsule_v1",
        "dataset_sha256": dataset_sha,
        "total_items": total,
        "typed_answer_formed": typed_formed,
        "typed_answer_formation_rate": typed_formed / total if total else 0.0,
        "native_correct": native_correct,
        "native_incorrect": native_incorrect,
        "invalid": invalid,
        "model_errors": model_errors,
        "model_error_rate": model_errors / total if total else 1.0,
        "retry_triggered": retries,
        "total_calls": total_calls,
        "mean_calls": total_calls / total if total else 0.0,
        "mean_duration_seconds": sum(r["duration_seconds"] for r in rows) / total if total else 0.0,
        "elapsed_seconds": time.perf_counter() - started,
        "gates": {
            "complete_20": total == 20,
            "health_pass": model_errors / total <= 0.10 if total else False,
            "formation_pass": typed_formed / total >= 0.60 if total else False,
            "native_correct_screen_pass": native_correct >= 4,
            "invalid_error_pass": invalid + model_errors <= 16,
            "mean_calls_pass": total_calls / total <= 1.50 if total else False,
        },
    }
    summary["verdict"] = "EXPLORATORY_CONTINUE_TO_BASELINE_MATCHED" if all(summary["gates"].values()) else "EXPLORATORY_NO_GO"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "docs" / "experiments" / "V5-HARD20-TYPED-CAPSULE-001"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--hard-stop-seconds", type=float, default=180 * 60)
    args = parser.parse_args()
    run(Path(args.output_dir), args.timeout, args.workers, args.hard_stop_seconds)
