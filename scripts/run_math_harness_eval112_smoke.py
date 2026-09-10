"""Run a ten-item smoke test on the team-created eval_112 dataset."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_math_harness_112_diagnostic import solve_one  # noqa: E402


RUN_ID = "MATH-HARNESS-EVAL112-SMOKE-001"
SOURCE_PATH = Path("reasoning_agent/error_notebook/eval_112.json")
ITEM_COUNT = 10
WORKERS = 3
REQUEST_TIMEOUT_SECONDS = 600
HARD_STOP_SECONDS = 7_200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _load_items(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) < ITEM_COUNT:
        raise ValueError("eval_112_requires_at_least_10_items")
    selected = rows[:ITEM_COUNT]
    if len({row.get("idx") for row in selected}) != ITEM_COUNT:
        raise ValueError("eval_112_first_10_indices_must_be_unique")
    if any(not isinstance(row.get("problem"), str) or not row["problem"].strip() for row in selected):
        raise ValueError("eval_112_first_10_problems_invalid")
    return selected


def _summary(rows: list[dict[str, Any]], elapsed: float, *, final: bool) -> dict[str, Any]:
    outcomes = Counter(row.get("outcome", "invalid") for row in rows)
    verdicts = Counter(row.get("verdict", "unknown") for row in rows)
    calls = [int(row.get("model_calls", 0)) for row in rows]
    durations = [float(row.get("duration_seconds", 0.0)) for row in rows]
    requested = [int(row.get("requested_tokens", 0)) for row in rows]
    return {
        "run_id": RUN_ID,
        "phase": "team_eval112_smoke",
        "method_id": "bounded_evidence_trajectory_selection_v1",
        "harness_version": "MATH-HARNESS-V1",
        "status": "completed" if final else "running",
        "diagnostic_only": True,
        "dataset_role": "team_created_answer_bearing_internal",
        "temporary_answer_bank": "off",
        "records": len(rows),
        "expected_records": ITEM_COUNT,
        "outcome_counts": dict(outcomes),
        "verdict_counts": dict(verdicts),
        "correct": outcomes.get("correct", 0),
        "incorrect": outcomes.get("incorrect", 0),
        "invalid": outcomes.get("invalid", 0),
        "model_errors": outcomes.get("error", 0),
        "timeout_count": sum(bool(row.get("timeout")) for row in rows),
        "candidate_formed_rows": sum(row.get("candidate_count", 0) > 0 for row in rows),
        "total_model_calls": sum(calls),
        "average_model_calls": sum(calls) / len(rows) if rows else 0.0,
        "total_requested_tokens": sum(requested),
        "average_duration_seconds": sum(durations) / len(rows) if rows else 0.0,
        "max_duration_seconds": max(durations, default=0.0),
        "health_pass": len(rows) == ITEM_COUNT and not any(row.get("model_error") for row in rows),
        "elapsed_seconds": round(elapsed, 3),
        "capability_conclusion": "NONE",
        "disposition": "SMOKE_COMPLETE_NO_CAPABILITY_CONCLUSION" if final and len(rows) == ITEM_COUNT else "SMOKE_INCOMPLETE_NO_CAPABILITY_CONCLUSION",
    }


def run(output_dir: Path, *, workers: int, timeout: int, hard_stop: float) -> dict[str, Any]:
    if not 1 <= workers <= 3:
        raise ValueError("workers must be between 1 and 3")
    source = ROOT / SOURCE_PATH
    items = _load_items(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    manifest = {
        "run_id": RUN_ID,
        "phase": "team_eval112_smoke",
        "method_id": "bounded_evidence_trajectory_selection_v1",
        "harness_version": "MATH-HARNESS-V1",
        "status": "running",
        "started_at_utc": _now(),
        "dataset_path": str(SOURCE_PATH),
        "dataset_sha256": _sha256(source),
        "selected_indices": [row["idx"] for row in items],
        "dataset_items": ITEM_COUNT,
        "workers": workers,
        "request_timeout_seconds": timeout,
        "hard_stop_seconds": hard_stop,
        "temporary_answer_bank": "off",
        "gold_passed_to_agent": False,
        "answers": "answers.jsonl",
        "summary": "summary.json",
        "result": "result.md",
        "diagnostic_only": True,
        "capability_conclusion": "NONE",
    }
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rows_by_id: dict[str, dict[str, Any]] = {}
    next_index = 0
    active: dict[Any, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while active or next_index < len(items):
            while next_index < len(items) and len(active) < workers and time.perf_counter() - started < hard_stop:
                item = items[next_index]
                next_index += 1
                active[pool.submit(solve_one, item, timeout)] = item
            if not active:
                break
            done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                row = future.result()
                rows_by_id[str(item["idx"])] = row
                print(
                    f"[{item['idx']}] outcome={row['outcome']} calls={row['model_calls']} "
                    f"duration={row['duration_seconds']:.1f}s",
                    flush=True,
                )
                rows = [rows_by_id[str(selected["idx"])] for selected in items if str(selected["idx"]) in rows_by_id]
                _atomic_write(output_dir / "answers.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
                _atomic_write(output_dir / "summary.json", json.dumps(_summary(rows, time.perf_counter() - started, final=False), ensure_ascii=False, indent=2) + "\n")

    rows = [rows_by_id[str(item["idx"])] for item in items if str(item["idx"]) in rows_by_id]
    summary = _summary(rows, time.perf_counter() - started, final=True)
    _atomic_write(output_dir / "answers.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    _atomic_write(output_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    manifest.update({"status": "completed", "ended_at_utc": _now(), "records": len(rows), "remote_model_calls": summary["total_model_calls"], "capability_conclusion": "NONE"})
    _atomic_write(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {RUN_ID}\n\n"
            f"记录：{summary['records']}/{ITEM_COUNT}；correct={summary['correct']}；"
            f"incorrect={summary['incorrect']}；invalid={summary['invalid']}；"
            f"model_error={summary['model_errors']}；timeout={summary['timeout_count']}。\n\n"
            "本窗使用团队自建 eval_112 前 10 题，最新 Harness、bank-off；gold 只在宿主侧评分。"
            "本窗只作 smoke 观测，不产生官方能力结论。\n"
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/experiments/MATH-HARNESS-EVAL112-SMOKE-001")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--hard-stop-seconds", type=float, default=HARD_STOP_SECONDS)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.output_dir), workers=args.workers, timeout=args.timeout, hard_stop=args.hard_stop_seconds), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
