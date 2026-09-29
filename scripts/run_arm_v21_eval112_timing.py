"""Run the strict-serial, one-solve-per-item ARM-Harness v2.1 experiment.

Every item is recorded exactly once, including incomplete and error results.
The team answer is used only by the local judge and is never passed to the
agent.
"""

from __future__ import annotations

import argparse
from collections import Counter
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
from reasoning_agent.arm_dataset import expand_selection_manifest  # noqa: E402
from reasoning_agent.artifacts import ArtifactManager  # noqa: E402
from reasoning_agent.profiles import (  # noqa: E402
    ARM_V21_REQUEST_TIMEOUT_SECONDS,
    PROFILE_NAMES,
    build_profile_config,
)
from scripts.evaluate_dev import judge_correct  # noqa: E402
from user_agent import ReasoningAgent  # noqa: E402


EVAL112_PATH = ROOT / "reasoning_agent" / "error_notebook" / "eval_112.json"
WORKERS = 1
EXPECTED_RECORDS = 112
REQUEST_TIMEOUT_SECONDS = ARM_V21_REQUEST_TIMEOUT_SECONDS
ClientFactory = Callable[[], Any]
AgentFactory = Callable[..., Any]


def _now_utc() -> str:
    """Return an ISO-8601 UTC timestamp for a run artifact."""
    return datetime.now(timezone.utc).isoformat()


def load_dataset(
    path: Path | str | None = None,
    *,
    expected_records: int = EXPECTED_RECORDS,
    error_prefix: str = "dataset",
    selection_seed: int | None = None,
) -> list[dict[str, Any]]:
    """Load a fixed scoreable dataset with unique ids, problems, and gold answers."""
    dataset_path = EVAL112_PATH if path is None else Path(path)
    if dataset_path != EVAL112_PATH and not dataset_path.is_file():
        raise RuntimeError(f"{error_prefix}_required:{dataset_path}")
    if not dataset_path.is_file():
        raise RuntimeError(f"{error_prefix}_required:{dataset_path}")
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{error_prefix}_invalid_json:{dataset_path}") from exc
    if isinstance(payload, Mapping):
        if "records" in payload or "items" in payload:
            payload = payload.get("records", payload.get("items"))
        else:
            payload = expand_selection_manifest(
                payload,
                pool_root=dataset_path.parent / "external_hard_sets",
                seed=selection_seed,
            )
    if not isinstance(payload, list) or len(payload) != int(expected_records):
        raise RuntimeError(f"{error_prefix}_count_required:{expected_records}")
    rows: list[dict[str, Any]] = []
    ids: set[Any] = set()
    for row in payload:
        if not isinstance(row, Mapping):
            raise RuntimeError(f"{error_prefix}_row_must_be_object")
        idx = row.get("idx")
        problem = row.get("problem")
        try:
            duplicate = idx in ids
            ids.add(idx)
        except TypeError as exc:
            raise RuntimeError(f"{error_prefix}_idx_must_be_hashable") from exc
        if duplicate:
            raise RuntimeError(f"{error_prefix}_idx_must_be_unique")
        if idx is None:
            raise RuntimeError(f"{error_prefix}_idx_required")
        if not isinstance(problem, str) or not problem.strip():
            raise RuntimeError(f"{error_prefix}_problem_must_be_non_empty")
        answer = row.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(f"{error_prefix}_answer_must_be_non_empty")
        rows.append(dict(row))
    return rows


def load_eval112(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load the canonical 112-row evaluation dataset."""
    return load_dataset(path, expected_records=EXPECTED_RECORDS, error_prefix="eval112")


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
    ledger_calls = ledger.get("calls", []) if isinstance(ledger, Mapping) else []
    calls = ledger_calls if isinstance(ledger_calls, list) and ledger_calls else (
        budget.get("records", []) if isinstance(budget, Mapping) else []
    )
    if not isinstance(calls, list):
        calls = []
    call_schema = [
        {
            key: call[key]
            for key in (
                "stage",
                "status",
                "reasoning_mode",
                "finish_reason",
                "completion_tokens",
                "has_reasoning_content",
                "reasoning_content_chars",
                "content_chars",
                "error_category",
                "duration_ms",
            )
            if key in call
        }
        for call in calls
        if isinstance(call, Mapping)
    ]
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
        "call_schema": call_schema,
        "timeout_count": timeout_count,
        "candidate_count": candidate_count,
        "final_source": summary.get("final_source") or finalize.get("source"),
        "safe_fallback_used": safe_fallback,
        "final_failure_reason": result.get("final_failure_reason") or summary.get("final_failure_reason"),
        "arm_v2_summary": dict(summary) if isinstance(summary, Mapping) else {},
        "primary_parse": summary.get("primary_parse") if isinstance(summary, Mapping) else None,
        "primary_candidate": summary.get("primary_candidate") if isinstance(summary, Mapping) else None,
        "second_parse": summary.get("second_parse") if isinstance(summary, Mapping) else None,
        "second_candidate": summary.get("second_candidate") if isinstance(summary, Mapping) else None,
        "safe_candidate": summary.get("safe_candidate") if isinstance(summary, Mapping) else None,
        "verification": summary.get("verification") if isinstance(summary, Mapping) else None,
        "resolver": summary.get("resolver") if isinstance(summary, Mapping) else None,
        "final": summary.get("final") if isinstance(summary, Mapping) else None,
        "primary_candidate_value": (
            summary.get("primary_candidate", {}).get("value")
            if isinstance(summary.get("primary_candidate"), Mapping)
            else None
        ),
        "primary_candidate_complete": bool(
            summary.get("primary_candidate", {}).get("answer_complete")
            if isinstance(summary.get("primary_candidate"), Mapping)
            else False
        ),
        "second_sample_triggered": bool(summary.get("second_sample_triggered")),
        "second_sample_trigger_reason": summary.get("second_sample_trigger_reason"),
        "pair_relation": summary.get("a_b_relation"),
        "second_sample_outcome": summary.get("second_sample_outcome"),
        "agreement": bool(summary.get("agreement")),
        "conflict": bool(summary.get("conflict")),
        "resolver_triggered": bool(summary.get("resolver_triggered")),
        "resolver_decision": summary.get("resolver_decision"),
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


def summarize_timing(
    rows: list[Mapping[str, Any]],
    total_wall_seconds: float,
    expected_records: int = EXPECTED_RECORDS,
) -> dict[str, Any]:
    """Summarize every item, retaining incomplete/error denominators."""
    durations = [float(row.get("duration_seconds", 0.0)) for row in rows]
    calls = [int(row.get("model_calls", 0) or 0) for row in rows]
    complete = sum(row.get("status") == "complete" or bool(row.get("complete_answer")) for row in rows)
    incomplete = sum(row.get("status") == "incomplete" for row in rows)
    errors = sum(row.get("status") == "error" for row in rows)
    correct = sum(row.get("verdict") == "correct" for row in rows)
    incorrect = sum(row.get("verdict") == "incorrect" for row in rows)
    invalid = sum(row.get("verdict") == "invalid" for row in rows)
    judge_unknown = sum(row.get("verdict") == "unknown" for row in rows)
    sampled = sum(bool(row.get("second_sample_triggered")) for row in rows)
    agreement = sum(row.get("pair_relation") == "EQUIVALENT" for row in rows)
    conflict = sum(row.get("pair_relation") == "CONFLICT" for row in rows)
    no_valid_pair = sum(row.get("pair_relation") == "NO_VALID_PAIR" for row in rows)
    gains = [
        row for row in rows
        if row.get("second_sample_triggered")
        and row.get("baseline_verdict") != "correct"
        and row.get("candidate_verdict") == "correct"
    ]
    losses = [
        row for row in rows
        if row.get("second_sample_triggered")
        and row.get("baseline_verdict") == "correct"
        and row.get("candidate_verdict") != "correct"
    ]
    paired_rows = [
        row for row in rows
        if row.get("second_sample_triggered")
        and "baseline_verdict" in row
        and "candidate_verdict" in row
    ]
    source_breakdown = Counter(str(row.get("final_source") or "unknown") for row in rows)
    trigger_breakdown = Counter(str(row.get("second_sample_trigger_reason") or "none") for row in rows)
    relation_breakdown = Counter(str(row.get("pair_relation") or "none") for row in rows)
    outcome_breakdown = Counter(str(row.get("second_sample_outcome") or "none") for row in rows)
    resolver_breakdown = Counter(str(row.get("resolver_decision") or "none") for row in rows)
    report = {
        "records": len(rows),
        "records_completed": len(rows),
        "complete_answers": complete,
        "complete_answer_count": complete,
        "incomplete_answers": incomplete,
        "complete": complete,
        "incomplete": incomplete,
        "errors": errors,
        "correct_count": correct,
        "incorrect_count": incorrect,
        "invalid_count": invalid,
        "correct": correct,
        "incorrect": incorrect,
        "invalid": invalid,
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
        "second_sample_trigger_count": sampled,
        "second_sample_trigger_rate": round(sampled / len(rows), 6) if rows else 0.0,
        "agreement_count": agreement,
        "agreement_rate": round(agreement / sampled, 6) if sampled else 0.0,
        "conflict_count": conflict,
        "conflict_rate": round(conflict / sampled, 6) if sampled else 0.0,
        "no_valid_pair_count": no_valid_pair,
        "no_valid_pair_rate": round(no_valid_pair / sampled, 6) if sampled else 0.0,
        "correct_gain_from_second_sample": len(gains) if paired_rows else None,
        "correct_loss_from_second_sample": len(losses) if paired_rows else None,
        "resolver_count": sum(bool(row.get("resolver_triggered")) for row in rows),
        "outcome_matrix": {
            "complete": complete,
            "incomplete": incomplete,
            "error": errors,
            "correct": correct,
            "incorrect": incorrect,
            "invalid": invalid,
        },
        "final_source_breakdown": dict(source_breakdown),
        "second_sample_breakdown": {
            "trigger_reason": dict(trigger_breakdown),
            "pair_relation": dict(relation_breakdown),
            "outcome": dict(outcome_breakdown),
        },
        "resolver_breakdown": dict(resolver_breakdown),
        "safe_candidate_breakdown": {
            "used": sum(bool(row.get("safe_fallback_used")) for row in rows),
            "not_used": sum(not bool(row.get("safe_fallback_used")) for row in rows),
        },
        "disposition": (
            "ACCURACY_COMPLETE"
            if len(rows) == expected_records and complete == expected_records
            else "RUN_COMPLETE_WITH_INCOMPLETE"
            if len(rows) == expected_records
            else "INCOMPLETE"
        ),
        "submission_promotion": "NONE",
    }
    return report


def run_timing(
    *,
    profile: str,
    run_id: str,
    dataset_path: Path | str | None = None,
    output_root: Path | str = ROOT / "artifacts",
    expected_records: int | None = None,
    selection_seed: int | None = None,
    client_factory: ClientFactory | None = None,
    agent_factory: AgentFactory = ReasoningAgent,
) -> dict[str, Any]:
    """Run eval112 serially with exactly one solve attempt per item."""
    profile = profile.strip().lower()
    dataset_path = EVAL112_PATH if dataset_path is None else dataset_path
    expected_records = EXPECTED_RECORDS if expected_records is None else int(expected_records)
    if expected_records < 1:
        raise ValueError("expected_records_must_be_positive")
    rows = load_dataset(
        dataset_path,
        expected_records=expected_records,
        error_prefix="eval112" if expected_records == EXPECTED_RECORDS else "dataset",
        selection_seed=selection_seed,
    )
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
            previous_manifest.get("experiment_objective") != "one_item_one_solve_timing"
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
        "experiment_objective": "one_item_one_solve_timing",
        "provider": "InternChatClient",
        "model": os.environ.get("INTERN_MODEL", "intern-s2"),
        "dataset_path": str(dataset.relative_to(ROOT)).replace("\\", "/") if dataset.is_relative_to(ROOT) else str(dataset),
        "dataset_hash": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "expected_records": expected_records,
        "selection_seed": selection_seed,
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
        "one_item_one_solve": True,
        "retry_until_complete": False,
        "max_attempts_per_item": 1,
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
            if attempt_counts.get(idx, 0):
                raise RuntimeError(f"one_item_one_solve_violation:{idx}")
            attempt_started = time.perf_counter()
            client: Any = None
            solve_error: Exception | None = None
            try:
                if client_factory is None:
                    client = InternChatClient(timeout=REQUEST_TIMEOUT_SECONDS, retry=1)
                else:
                    client = client_factory()
                agent = agent_factory(client=client, config=build_profile_config(profile))
                result = agent.solve(item["problem"], {"idx": idx, "run_id": run_id})
                if not isinstance(result, Mapping):
                    result = {"final_response": "UNKNOWN", "trace": []}
            except Exception as exc:
                solve_error = exc
                result = {
                    "final_response": "UNKNOWN",
                    "final_failure_reason": f"runner_error:{type(exc).__name__}",
                    "trace": [{"stage": "runner_error", "error": type(exc).__name__}],
                }
            fields = _trace_fields(result)
            complete = has_complete_answer(result)
            status = "complete" if complete else "error" if solve_error is not None else "incomplete"
            if not complete and not fields["final_failure_reason"]:
                fields["final_failure_reason"] = (
                    f"runner_error:{type(solve_error).__name__}"
                    if solve_error is not None
                    else "incomplete_without_failure_reason"
                )
            final_response = str(result.get("final_response", "UNKNOWN"))[:2000]
            extracted = result.get("extracted_answer")
            if not isinstance(extracted, str) or not extracted.strip():
                extracted = final_response if complete else ""
            verdict = (
                judge_correct(extracted, item["answer"])
                if complete
                else "invalid"
                if status == "incomplete"
                else None
            )
            baseline_verdict = (
                judge_correct(fields["primary_candidate_value"], item["answer"])
                if fields["primary_candidate_complete"] and fields["primary_candidate_value"]
                else "invalid"
            )
            duration = round(time.perf_counter() - attempt_started, 3)
            attempt_row = {
                "idx": idx,
                "attempt": 1,
                "profile": profile,
                "status": status,
                "complete_answer": complete,
                "verdict": verdict,
                "baseline_verdict": baseline_verdict,
                "candidate_verdict": verdict,
                "duration_seconds": duration,
                "model_calls": fields["model_calls"],
                "timeout_count": fields["timeout_count"],
                "reasoning_modes": fields["reasoning_modes"],
                "final_failure_reason": fields["final_failure_reason"],
                "final_response": final_response,
            }
            manager.append_jsonl("attempts.jsonl", attempt_row)
            attempt_counts[idx] = 1
            record = {
                "idx": idx,
                "profile": profile,
                "solver_reasoning_mode": config.arm_solver_reasoning_mode,
                "status": status,
                "duration_seconds": duration,
                "time_to_final_answer": duration if complete else None,
                "attempts": 1,
                "complete_answer": complete,
                "verdict": verdict,
                "baseline_verdict": baseline_verdict,
                "candidate_verdict": verdict,
                **fields,
                "extracted_answer": str(extracted)[:2000],
                "final_response": final_response,
            }
            manager.append_answer(record)
            all_rows.append(record)
            completed_ids.add(idx)
            manager.save_json("progress.json", {
                "records": len(rows),
                "completed": len(completed_ids),
                "current_idx": None,
                "status": "running",
            })
            manager.save_json(
                "metrics.json",
                summarize_timing(all_rows, time.perf_counter() - started, expected_records),
            )
            if client_factory is None:
                print(json.dumps({"run_id": run_id, "idx": idx, "status": status, "verdict": verdict, "completed": len(completed_ids)}, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        report = summarize_timing(all_rows, time.perf_counter() - started, expected_records)
        report["status"] = "interrupted"
        manifest.update({"ended_at": _now_utc(), "status": "interrupted"})
        manager.save_json("metrics.json", report)
        manager.save_manifest(manifest)
        raise
    except RuntimeError:
        report = summarize_timing(all_rows, time.perf_counter() - started, expected_records)
        report["status"] = "blocked"
        manifest.update({"ended_at": _now_utc(), "status": "blocked"})
        manager.save_json("metrics.json", report)
        manager.save_manifest(manifest)
        raise

    report = summarize_timing(all_rows, time.perf_counter() - started, expected_records)
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
    parser.add_argument("--dataset-path", type=Path, default=EVAL112_PATH)
    parser.add_argument("--expected-records", type=int, default=None)
    parser.add_argument("--selection-seed", type=int, default=None)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(
        json.dumps(
            run_timing(
                profile=args.profile,
                run_id=args.run_id,
                dataset_path=args.dataset_path,
                expected_records=args.expected_records,
                selection_seed=args.selection_seed,
                output_root=args.output_root,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
