"""Run the strict-serial, accuracy-first ARM-Harness v2.1 eval112 experiment.

Each problem is retried until its result is non-empty and non-UNKNOWN.  The
team answer is used only by the local judge and is never passed to the agent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from reasoning_agent.artifacts import ArtifactManager  # noqa: E402
from reasoning_agent.profiles import PROFILE_NAMES, build_profile_config  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402
from user_agent import ReasoningAgent  # noqa: E402


EVAL112_PATH = ROOT / "reasoning_agent" / "error_notebook" / "eval_112.json"
WORKERS = 1
EXPECTED_RECORDS = 112
REQUEST_TIMEOUT_SECONDS = 600
ClientFactory = Callable[[], Any]
AgentFactory = Callable[..., Any]


def _now_utc() -> str:
    """Return an ISO-8601 UTC timestamp for a run artifact."""
    return datetime.now(timezone.utc).isoformat()


def load_eval112(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load 112 scoreable rows with unique ids, problem text, and gold answers."""
    dataset_path = EVAL112_PATH if path is None else Path(path)
    if dataset_path != EVAL112_PATH and not dataset_path.is_file():
        raise RuntimeError(f"eval112_required:{dataset_path}")
    if not dataset_path.is_file():
        raise RuntimeError("eval112_required:reasoning_agent/error_notebook/eval_112.json")
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"eval112_invalid_json:{dataset_path}") from exc
    if isinstance(payload, Mapping):
        payload = payload.get("records", payload.get("items"))
    if not isinstance(payload, list) or len(payload) != EXPECTED_RECORDS:
        raise RuntimeError(f"eval112_count_required:{EXPECTED_RECORDS}")
    rows: list[dict[str, Any]] = []
    ids: set[Any] = set()
    for row in payload:
        if not isinstance(row, Mapping):
            raise RuntimeError("eval112_row_must_be_object")
        idx = row.get("idx")
        problem = row.get("problem")
        try:
            duplicate = idx in ids
            ids.add(idx)
        except TypeError as exc:
            raise RuntimeError("eval112_idx_must_be_hashable") from exc
        if duplicate:
            raise RuntimeError("eval112_idx_must_be_unique")
        if idx is None:
            raise RuntimeError("eval112_idx_required")
        if not isinstance(problem, str) or not problem.strip():
            raise RuntimeError("eval112_problem_must_be_non_empty")
        answer = row.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("eval112_answer_must_be_non_empty")
        rows.append(dict(row))
    return rows


def has_complete_answer(result: Mapping[str, Any] | None) -> bool:
    """Reject empty answers and explicit abstentions before scoring."""
    final = result.get("final_response") if isinstance(result, Mapping) else None
    if not isinstance(final, str) or not final.strip():
        return False
    normalized = final.strip().casefold().strip(" .。!！?？")
    abstentions = {
        "unknown", "n/a", "none", "null", "abstain", "不确定", "无法确定",
        "无法完成", "不知道", "cannot determine", "unable to solve", "i don't know",
    }
    return normalized not in abstentions and not normalized.startswith(("unknown:", "无法确定：", "无法确定:"))


def _git_head() -> str | None:
    """Read the current commit without making Git state changes."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _trace_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    """Extract bounded timing fields from a harness trace."""
    trace = result.get("trace")
    events = trace if isinstance(trace, list) else []
    ledger = next((item for item in events if isinstance(item, Mapping) and item.get("stage") == "evidence_ledger"), {})
    summary = next((item for item in events if isinstance(item, Mapping) and item.get("stage") == "arm_v2_summary"), {})
    finalize = next((item for item in events if isinstance(item, Mapping) and item.get("stage") == "finalize"), {})
    budget = ledger.get("budget", {}) if isinstance(ledger, Mapping) else {}
    calls = budget.get("records", []) if isinstance(budget, Mapping) else []
    if not isinstance(calls, list):
        calls = []
    modes = [call.get("reasoning_mode") for call in calls if isinstance(call, Mapping) and call.get("reasoning_mode")]
    timeout_count = sum(
        1 for call in calls if isinstance(call, Mapping) and call.get("error_category") == "timeout"
    )
    candidate_count = len(ledger.get("candidates", [])) if isinstance(ledger, Mapping) and isinstance(ledger.get("candidates"), list) else 0
    safe_fallback = bool(summary.get("safe_fallback_used")) or any(
        isinstance(item, Mapping) and item.get("stage") == "safe_candidate_fallback" for item in events
    )
    return {
        "model_calls": int(budget.get("calls", len(calls))) if isinstance(budget, Mapping) else len(calls),
        "reasoning_modes": modes,
        "timeout_count": timeout_count,
        "candidate_count": candidate_count,
        "final_source": summary.get("final_source") or finalize.get("source"),
        "safe_fallback_used": safe_fallback,
        # Do not infer this from call duration; the current trace has no
        # unambiguous candidate timestamp, so the documented value is null.
        "time_to_first_candidate": None,
    }


def _read_completed(path: Path) -> set[Any]:
    """Read completed item ids from an existing append-only answer stream."""
    if not path.is_file():
        return set()
    completed: set[Any] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("answers_jsonl_invalid") from exc
        if not isinstance(row, Mapping) or "idx" not in row:
            raise RuntimeError("answers_jsonl_record_invalid")
        completed.add(row["idx"])
    return completed


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    """Return the nearest-rank percentile for a non-empty duration list."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = max(1, int((len(ordered) * percentile) + 0.999999))
    return ordered[min(len(ordered), rank) - 1]


def summarize_timing(rows: list[Mapping[str, Any]], total_wall_seconds: float) -> dict[str, Any]:
    """Summarize complete-answer accuracy first and elapsed time second."""
    durations = [float(row.get("duration_seconds", 0.0)) for row in rows]
    calls = [int(row.get("model_calls", 0) or 0) for row in rows]
    complete = sum(bool(row.get("complete_answer")) for row in rows)
    correct = sum(row.get("verdict") == "correct" for row in rows)
    incorrect = sum(row.get("verdict") == "incorrect" for row in rows)
    judge_unknown = sum(row.get("verdict") == "unknown" for row in rows)
    report = {
        "records": len(rows),
        "records_completed": len(rows),
        "complete_answers": complete,
        "complete_answer_count": complete,
        "incomplete_answers": len(rows) - complete,
        "correct_count": correct,
        "incorrect_count": incorrect,
        "judge_unknown_count": judge_unknown,
        "accuracy": round(correct / len(rows), 6) if rows else 0.0,
        "known_answer_accuracy": round(correct / (correct + incorrect), 6) if correct + incorrect else None,
        "total_wall_seconds": round(float(total_wall_seconds), 3),
        "mean_duration_seconds": round(statistics.mean(durations), 3) if durations else 0.0,
        "median_duration_seconds": round(statistics.median(durations), 3) if durations else 0.0,
        "p90_duration_seconds": _percentile(durations, 0.90),
        "p95_duration_seconds": _percentile(durations, 0.95),
        "max_duration_seconds": round(max(durations, default=0.0), 3),
        "total_calls": sum(calls),
        "total_model_calls": sum(calls),
        "mean_calls_per_problem": round(statistics.mean(calls), 3) if calls else 0.0,
        "request_timeouts": sum(int(row.get("timeout_count", 0) or 0) for row in rows),
        "safe_fallback_count": sum(bool(row.get("safe_fallback_used")) for row in rows),
        "disposition": "ACCURACY_COMPLETE" if len(rows) == EXPECTED_RECORDS and complete == EXPECTED_RECORDS else "INCOMPLETE",
        "submission_promotion": "NONE",
    }
    return report


def _failure_categories(result: Mapping[str, Any]) -> set[str]:
    """Collect bounded call failure categories from a solve trace."""
    events = result.get("trace")
    if not isinstance(events, list):
        return set()
    ledger = next(
        (item for item in events if isinstance(item, Mapping) and item.get("stage") == "evidence_ledger"),
        {},
    )
    calls = ledger.get("calls", []) if isinstance(ledger, Mapping) else []
    return {
        str(call.get("error_category"))
        for call in calls
        if isinstance(call, Mapping) and call.get("error_category")
    }


def _permanent_configuration_error(client: Any, result: Mapping[str, Any]) -> bool:
    """Stop retrying when credentials or authorization make progress impossible."""
    if "configuration" in _failure_categories(result):
        return True
    category = str(getattr(client, "last_failure_category", "") or "").casefold()
    failure_type = str(getattr(client, "last_failure_type", "") or "").casefold()
    return category == "configuration" or "httperror:401" in failure_type or "httperror:403" in failure_type


def run_timing(
    *,
    profile: str,
    run_id: str,
    dataset_path: Path | str | None = None,
    output_root: Path | str = ROOT / "artifacts",
    client_factory: ClientFactory | None = None,
    agent_factory: AgentFactory = ReasoningAgent,
) -> dict[str, Any]:
    """Run eval112 serially and retry each item until it has a complete answer."""
    profile = profile.strip().lower()
    dataset_path = EVAL112_PATH if dataset_path is None else dataset_path
    rows = load_eval112(dataset_path)
    config = build_profile_config(profile)
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown_profile:{profile}")
    dataset = Path(dataset_path)
    output_dir = Path(output_root) / run_id
    manager = ArtifactManager(output_dir)
    answer_path = output_dir / "answers.jsonl"
    attempt_path = output_dir / "attempts.jsonl"
    manifest_path = output_dir / "run_manifest.json"
    completed_ids = _read_completed(answer_path)
    existing_rows: list[dict[str, Any]] = []
    if answer_path.is_file():
        existing_rows = [json.loads(line) for line in answer_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if manifest_path.is_file():
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            previous_manifest.get("experiment_objective") != "accuracy_first_full_completion"
            or previous_manifest.get("dataset_hash") != hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest()
            or previous_manifest.get("profile") != profile
        ):
            raise RuntimeError("run_id_conflicts_with_existing_experiment")
    attempt_counts: dict[Any, int] = {}
    if attempt_path.is_file():
        for line in attempt_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                attempt_row = json.loads(line)
                idx = attempt_row.get("idx")
                attempt_counts[idx] = attempt_counts.get(idx, 0) + 1

    started = time.perf_counter()
    started_at = _now_utc()
    manifest = {
        "run_id": run_id,
        "git_head": _git_head(),
        "profile": profile,
        "experiment_objective": "accuracy_first_full_completion",
        "provider": "InternChatClient",
        "model": os.environ.get("INTERN_MODEL", "intern-s2"),
        "dataset_path": str(dataset.relative_to(ROOT)).replace("\\", "/") if dataset.is_relative_to(ROOT) else str(dataset),
        "dataset_hash": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "solver_reasoning_mode": config.arm_solver_reasoning_mode,
        "max_tokens": config.harness_attempt_a_max_tokens,
        "token_budget": config.arm_adaptive_token_budget,
        "max_calls": config.arm_adaptive_max_calls,
        "timeout": REQUEST_TIMEOUT_SECONDS,
        "max_wall_seconds": config.harness_max_wall_seconds,
        "workers": WORKERS,
        "bank_mode": "off",
        "rag_enabled": False,
        "legacy_route_enabled": False,
        "gold_answer_sent_to_agent": False,
        "judge": "scripts.evaluate_dev.judge_correct",
        "retry_until_complete": True,
        "max_attempts_per_item": None,
        "started_at": started_at,
        "ended_at": None,
        "status": "running",
    }
    manager.save_manifest(manifest)
    manager.save_json("progress.json", {
        "records": len(rows),
        "completed": len(completed_ids),
        "current_idx": next((item["idx"] for item in rows if item["idx"] not in completed_ids), None),
        "current_attempt": None,
        "status": "running",
    })

    all_rows = list(existing_rows)
    try:
        for item in rows:
            idx = item["idx"]
            if idx in completed_ids:
                continue
            item_started = time.perf_counter()
            while True:
                attempt_number = attempt_counts.get(idx, 0) + 1
                attempt_started = time.perf_counter()
                client: Any = None
                permanent_error = False
                try:
                    if client_factory is None:
                        client = InternChatClient(timeout=REQUEST_TIMEOUT_SECONDS, retry=1)
                    else:
                        client = client_factory()
                    agent = agent_factory(client=client, config=build_profile_config(profile))
                    result = agent.solve(item["problem"], {"idx": idx, "run_id": run_id})
                except Exception as exc:
                    category = str(getattr(exc, "category", "") or "").casefold()
                    detail = str(getattr(exc, "detail", "") or "").casefold()
                    permanent_error = (
                        category == "configuration"
                        or "401" in detail
                        or "403" in detail
                    )
                    result = {
                        "final_response": "UNKNOWN",
                        "trace": [{"stage": "runner_error", "error": type(exc).__name__, "category": category}],
                    }
                fields = _trace_fields(result)
                complete = has_complete_answer(result)
                final_response = str(result.get("final_response", "UNKNOWN"))[:2000]
                extracted = result.get("extracted_answer")
                if not isinstance(extracted, str) or not extracted.strip():
                    extracted = final_response
                verdict = judge_correct(extracted, item["answer"])
                duration = round(time.perf_counter() - item_started, 3)
                attempt_row = {
                    "idx": idx,
                    "attempt": attempt_number,
                    "profile": profile,
                    "complete_answer": complete,
                    "verdict": verdict if complete else None,
                    "duration_seconds": round(time.perf_counter() - attempt_started, 3),
                    "model_calls": fields["model_calls"],
                    "timeout_count": fields["timeout_count"],
                    "reasoning_modes": fields["reasoning_modes"],
                    "final_response": final_response,
                }
                manager.append_jsonl("attempts.jsonl", attempt_row)
                attempt_counts[idx] = attempt_number
                manager.save_json("progress.json", {
                    "records": len(rows),
                    "completed": len(completed_ids),
                    "current_idx": idx if not complete else None,
                    "current_attempt": attempt_number if not complete else None,
                    "last_idx": idx if complete else None,
                    "status": "running",
                })
                if permanent_error or _permanent_configuration_error(client, result):
                    raise RuntimeError("api_configuration_or_authorization_failed")
                if not complete:
                    if client_factory is None:
                        print(json.dumps({"run_id": run_id, "idx": idx, "attempt": attempt_number, "status": "retry_incomplete"}, ensure_ascii=False), flush=True)
                    time.sleep(min(30, 2 ** min(attempt_number - 1, 5)))
                    continue

                record = {
                    "idx": idx,
                    "profile": profile,
                    "solver_reasoning_mode": config.arm_solver_reasoning_mode,
                    "duration_seconds": duration,
                    "time_to_final_answer": duration,
                    "attempts": attempt_number,
                    "complete_answer": True,
                    "verdict": verdict,
                    **fields,
                    "extracted_answer": str(extracted)[:2000],
                    "final_response": final_response,
                }
                manager.append_answer(record)
                all_rows.append(record)
                completed_ids.add(idx)
                manager.save_json("metrics.json", summarize_timing(all_rows, time.perf_counter() - started))
                if client_factory is None:
                    print(json.dumps({"run_id": run_id, "idx": idx, "attempts": attempt_number, "verdict": verdict, "completed": len(completed_ids)}, ensure_ascii=False), flush=True)
                break
    except KeyboardInterrupt:
        report = summarize_timing(all_rows, time.perf_counter() - started)
        report["status"] = "interrupted"
        manifest.update({"ended_at": _now_utc(), "status": "interrupted"})
        manager.save_json("metrics.json", report)
        manager.save_manifest(manifest)
        raise
    except RuntimeError:
        report = summarize_timing(all_rows, time.perf_counter() - started)
        report["status"] = "blocked"
        manifest.update({"ended_at": _now_utc(), "status": "blocked"})
        manager.save_json("metrics.json", report)
        manager.save_manifest(manifest)
        raise

    report = summarize_timing(all_rows, time.perf_counter() - started)
    report.update({"status": "completed" if len(completed_ids) == len(rows) else "incomplete"})
    ended_at = _now_utc()
    manifest.update({"ended_at": ended_at, "status": report["status"]})
    manager.save_json("metrics.json", report)
    manager.save_json("progress.json", {"records": len(rows), "completed": len(completed_ids), "status": report["status"]})
    manager.save_manifest(manifest)
    manager.save_text(
        "result.md",
        f"# ARM-Harness v2.1 accuracy-first run\n\nrecords: {len(all_rows)}/{len(rows)}\n"
        f"complete answers: {report['complete_answers']}\n"
        f"correct: {report['correct_count']}\n"
        f"incorrect: {report['incorrect_count']}\n"
        f"judge unknown: {report['judge_unknown_count']}\n"
        f"accuracy: {report['accuracy']:.4f}\n"
        "submission promotion: NONE\n",
    )
    return report


run = run_timing


def main() -> int:
    """Parse the fixed-profile CLI and run one serial timing experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=PROFILE_NAMES)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run_timing(profile=args.profile, run_id=args.run_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
