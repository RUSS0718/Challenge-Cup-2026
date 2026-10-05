"""Run ten bounded real-endpoint rounds and aggregate low-score failure signals.

Each round keeps gold answers in the host-side scorer, records only bounded
diagnostics, and writes artifacts below ``artifacts/``.  The output is local
replay evidence; it cannot be used as an official hidden-set score.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from reasoning_agent.artifacts import ArtifactManager, RunContext  # noqa: E402
from reasoning_agent.experiment_matrix import (  # noqa: E402
    DATASET_PATHS,
    RoundSpec,
    build_round_config,
    compact_finalizer_round_specs,
    default_round_specs,
    external_pressure_round_specs,
    external_pressure_replication_round_specs,
    incumbent_guard_round_specs,
    answer_commit_round_specs,
    format_matrix_summary,
    load_scored_rows,
    missing_candidate_round_specs,
    primary_tail_continuation_round_specs,
    recovery_round_specs,
    select_rows,
    summarize_rows,
    structured_confirmation_round_specs,
)
from scripts.evaluate_dev import classify_problem_type, judge_correct  # noqa: E402
from user_agent import ReasoningAgent  # noqa: E402


WRITE_LOCK = threading.Lock()


def _merge_counter_dicts(counters: Any) -> dict[str, int]:
    """Merge bounded integer counter mappings from round reports."""

    merged: dict[str, int] = {}
    for counter in counters:
        if not isinstance(counter, Mapping):
            continue
        for key, value in counter.items():
            try:
                merged[str(key)] = merged.get(str(key), 0) + int(value)
            except (TypeError, ValueError):
                continue
    return merged


def _summarize_reports_by_profile(reports: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate paired-run metrics by profile so candidate and baseline stay distinct."""

    fields = (
        "records",
        "correct",
        "incorrect",
        "invalid",
        "model_errors",
        "total_model_calls",
        "truncation_count",
        "compact_finalizer_activations",
        "incumbent_guard_activations",
        "primary_tail_continuation_activations",
    )
    summaries: dict[str, dict[str, Any]] = {}
    for report in reports:
        profile = str(report.get("profile") or "unknown")
        summary = summaries.setdefault(profile, {field: 0 for field in fields})
        for field in fields:
            value = report.get(field, 0)
            if field == "model_errors":
                summary[field] += int(bool(value))
            else:
                try:
                    summary[field] += int(value or 0)
                except (TypeError, ValueError):
                    continue
    for summary in summaries.values():
        records = summary["records"]
        summary["average_model_calls"] = (
            summary["total_model_calls"] / records if records else 0.0
        )
    return summaries


def _paired_record_count(reports: list[Mapping[str, Any]]) -> int | None:
    """Return paired records only when adjacent reports share the same items."""

    if len(reports) % 2:
        return None
    paired = 0
    for left, right in zip(reports[::2], reports[1::2]):
        left_items = left.get("selected_items")
        right_items = right.get("selected_items")
        if not isinstance(left_items, list) or left_items != right_items:
            return None
        try:
            left_records = int(left.get("records", 0) or 0)
            right_records = int(right.get("records", 0) or 0)
        except (TypeError, ValueError):
            return None
        if left_records != right_records:
            return None
        paired += left_records
    return paired


def _assert_scoring_dependencies() -> None:
    """Fail before endpoint calls when the local judge cannot score safely."""

    try:
        importlib.import_module("sympy")
    except ImportError as exc:
        raise ValueError("scoring_dependency_unavailable:sympy") from exc


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for a run manifest."""

    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    """Hash one dataset file so later rounds cannot silently change inputs."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str | None:
    """Read the checkout commit without changing repository state."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _dirty_tree() -> bool:
    """Report whether the current checkout has tracked or untracked changes."""

    result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def _trace_entry(trace: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    """Return the latest bounded trace entry for one stage."""

    return next(
        (
            entry
            for entry in reversed(trace)
            if isinstance(entry, dict) and entry.get("stage") == stage
        ),
        {},
    )


def _strip_sensitive(value: Any) -> Any:
    """Remove prompts, raw responses, and problem text from stored diagnostics."""

    if isinstance(value, dict):
        return {
            str(key): _strip_sensitive(item)
            for key, item in value.items()
            if key not in {"prompt", "content", "response", "problem"}
        }
    if isinstance(value, list):
        return [_strip_sensitive(item) for item in value]
    return value


def _compact_trace(trace: Any) -> list[dict[str, Any]]:
    """Keep bounded decision evidence while excluding raw model material."""

    if not isinstance(trace, list):
        return []
    return [
        _strip_sensitive(entry)
        for entry in trace
        if isinstance(entry, dict)
    ]


def _safe_error(exc: BaseException) -> str:
    """Map a client or runner exception to a bounded category."""

    category = getattr(exc, "category", None)
    allowed = {
        "timeout", "rate_limit", "configuration", "connectivity", "proxy",
        "tls", "http_status", "invalid_response", "request", "client_error",
    }
    return str(category) if category in allowed else "client_error"


def _call_records(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract evidence-ledger call records from a compact trace."""

    ledger = _trace_entry(trace, "evidence_ledger")
    calls = ledger.get("calls")
    if isinstance(calls, list):
        return [record for record in calls if isinstance(record, dict)]
    budget = ledger.get("budget")
    if isinstance(budget, Mapping) and isinstance(budget.get("records"), list):
        return [record for record in budget["records"] if isinstance(record, dict)]
    return []


def _call_telemetry(client: Any, trace: list[dict[str, Any]]) -> tuple[list[str], int, bool]:
    """Unify harness-ledger and legacy-agent call counters for one result."""

    calls = _call_records(trace)
    client_finish_reasons = getattr(client, "finish_reasons", [])
    if not isinstance(client_finish_reasons, list):
        client_finish_reasons = []
    finish_reasons = [str(record.get("finish_reason") or "missing") for record in calls]
    if not finish_reasons:
        finish_reasons = [str(reason or "missing") for reason in client_finish_reasons]
    request_diagnostics = getattr(client, "request_diagnostics", [])
    if not isinstance(request_diagnostics, list):
        request_diagnostics = []
    model_error = any(
        isinstance(record, Mapping) and record.get("status") == "error"
        for record in request_diagnostics
    ) or any(record.get("status") == "error" for record in calls)
    return finish_reasons, len(calls) or len(client_finish_reasons) or len(request_diagnostics), model_error


def run_item(item: Mapping[str, Any], config: Any, *, timeout: int) -> dict[str, Any]:
    """Solve one item and return score plus bounded failure diagnostics."""

    started = time.perf_counter()
    item_id = str(item["item_id"])
    status = "ok"
    error = None
    result: dict[str, Any]
    client: Any = None
    try:
        client = InternChatClient(timeout=timeout, retry=1, thinking_mode=None)
        result = ReasoningAgent(client=client, config=config).solve(
            str(item["problem"]),
            {"idx": item_id},
        )
    except BaseException as exc:
        status = "model_error"
        error = _safe_error(exc)
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
    final_response = result.get("final_response")
    final_response = final_response if isinstance(final_response, str) else "UNKNOWN"
    extracted = result.get("extracted_answer")
    extracted = extracted if isinstance(extracted, str) else ""
    trace = _compact_trace(result.get("trace"))
    calls = _call_records(trace)
    verdict = judge_correct(
        extracted,
        str(item["answer"]),
        classify_problem_type(str(item["problem"])),
        str(item["problem"]),
    )
    invalid = (
        not extracted.strip()
        or final_response.strip().upper() == "UNKNOWN"
        or verdict == "unknown"
    )
    if status == "model_error":
        outcome = "error"
    elif invalid:
        outcome = "invalid"
    else:
        outcome = verdict
    finish_reasons, model_calls, client_error = _call_telemetry(client, trace)
    return {
        "item_id": item_id,
        "problem_sha256": hashlib.sha256(str(item["problem"]).encode("utf-8")).hexdigest(),
        "expected_answer_sha256": hashlib.sha256(str(item["answer"]).encode("utf-8")).hexdigest(),
        "status": status,
        "error_category": error,
        "final_response": final_response[:512],
        "extracted_answer": extracted[:512],
        "verdict": verdict,
        "outcome": outcome,
        "invalid": invalid,
        "model_error": status == "model_error" or client_error or any(record.get("status") == "error" for record in calls),
        "finish_reasons": finish_reasons,
        "model_calls": model_calls,
        "candidate_count": sum(
            int(_trace_entry(trace, "arm_v2_summary").get(key, {}).get("candidate_count", 0) or 0)
            for key in ("primary_parse", "second_parse")
            if isinstance(_trace_entry(trace, "arm_v2_summary").get(key), Mapping)
        ),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "trace": trace,
    }


def _run_round(
    spec: RoundSpec,
    *,
    output_root: Path,
    workers: int,
    timeout: int,
) -> dict[str, Any]:
    """Run one fixed round and persist its manifest, rows, and report."""

    dataset_path = ROOT / DATASET_PATHS[spec.dataset]
    rows = select_rows(load_scored_rows(dataset_path), spec.keys)
    config = build_round_config(spec)
    round_dir = output_root / spec.round_id
    manager = ArtifactManager(round_dir)
    context = RunContext(
        run_id=f"ROBUSTNESS-{spec.round_id}-20261005",
        config=spec.profile,
        dataset=str(DATASET_PATHS[spec.dataset]).replace("\\", "/"),
        model="InternChatClient",
        git_commit=_git_head(),
        evaluation_scope="local_replay",
        official_evaluation=False,
        dataset_sha256=_sha256(dataset_path),
        working_tree_dirty=_dirty_tree(),
        started_at=_now(),
    )
    manifest = context.as_manifest()
    manifest.update(
        {
            "run_id": context.run_id,
            "round_id": spec.round_id,
            "profile": spec.profile,
            "dataset_path": str(DATASET_PATHS[spec.dataset]).replace("\\", "/"),
            "selected_items": [row["item_id"] for row in rows],
            "workers": workers,
            "timeout_seconds": timeout,
            "gold_passed_to_agent": False,
            "diagnostic_only": True,
            "status": "running",
            "answers": "answers.jsonl",
            "report": "report.json",
        }
    )
    manager.save_manifest(manifest)
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    pending = list(rows)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_item, item, config, timeout=timeout): item
            for item in pending
        }
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                item = futures.pop(future)
                row = future.result()
                results.append(row)
                print(
                    f"[{spec.round_id}/{item['item_id']}] {row['outcome']} "
                    f"calls={row['model_calls']} finish={','.join(row['finish_reasons'])}",
                    flush=True,
                )
    results.sort(key=lambda row: rows.index(next(item for item in rows if item["item_id"] == row["item_id"])))
    report = summarize_rows(results)
    report.update(
        {
            "run_id": context.run_id,
            "round_id": spec.round_id,
            "profile": spec.profile,
            "dataset": spec.dataset,
            "dataset_sha256": context.dataset_sha256,
            "selected_items": [row["item_id"] for row in rows],
            "status": "completed",
            "diagnostic_only": True,
            "evaluation_scope": "local_replay",
            "official_evaluation": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    )
    manager.save_answers(results)
    manager.save_report(report)
    manager.save_text(
        "result.md",
        (
            f"# {spec.round_id}\n\n"
            f"profile=`{spec.profile}`；records={report['records']}；"
            f"correct={report['correct']}；incorrect={report['incorrect']}；"
            f"invalid={report['invalid']}；truncation_rate={report['truncation_rate']:.3f}。\n\n"
            f"truncation_count={report['truncation_count']}；"
            f"compact_finalizer_activations={report['compact_finalizer_activations']}；"
            f"primary_tail_continuation_activations={report['primary_tail_continuation_activations']}。\n\n"
            "这是 local_replay 诊断，不代表官方隐藏集成绩。\n"
        ),
    )
    manifest.update(
        {
            "status": "completed",
            "ended_at": _now(),
            "records": len(results),
            "health_status": "pass" if not report["model_errors"] else "degraded",
        }
    )
    manager.save_manifest(manifest)
    return report


def _load_completed_round_report(output_root: Path, round_id: str) -> dict[str, Any] | None:
    """Load one prior completed round for a bounded subset rerun.

    A subset rerun is allowed to refresh one round without invalidating the
    other nine local reports.  Only reports carrying the expected round id,
    completed status, and diagnostic-only scope are reused.
    """
    path = output_root / round_id / "report.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("round_id") != round_id
        or payload.get("status") != "completed"
        or payload.get("diagnostic_only") is not True
    ):
        return None
    return payload


def _merge_round_reports(
    output_root: Path,
    selected_rounds: list[RoundSpec],
    fresh_reports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge fresh reports with valid prior reports in default-round order."""
    fresh_by_id = {str(report.get("round_id")): report for report in fresh_reports}
    selected_ids = {spec.round_id for spec in selected_rounds}
    merged: list[dict[str, Any]] = []
    reused: list[str] = []
    selected_ids = {spec.round_id for spec in selected_rounds}
    if selected_ids and all(round_id.startswith("B") for round_id in selected_ids):
        known_specs = recovery_round_specs()
    elif selected_ids and all(round_id.startswith("C") for round_id in selected_ids):
        known_specs = missing_candidate_round_specs()
    elif selected_ids and all(round_id.startswith("V") for round_id in selected_ids):
        known_specs = structured_confirmation_round_specs()
    elif selected_ids and all(round_id.startswith("W") for round_id in selected_ids):
        known_specs = compact_finalizer_round_specs()
    elif selected_ids and all(round_id.startswith("X") for round_id in selected_ids):
        known_specs = external_pressure_round_specs()
    elif selected_ids and all(round_id.startswith("Y") for round_id in selected_ids):
        known_specs = external_pressure_replication_round_specs()
    elif selected_ids and all(round_id.startswith("Z") for round_id in selected_ids):
        known_specs = incumbent_guard_round_specs()
    elif selected_ids and all(round_id.startswith("Q") for round_id in selected_ids):
        known_specs = answer_commit_round_specs()
    elif selected_ids and all(round_id.startswith("T") for round_id in selected_ids):
        known_specs = primary_tail_continuation_round_specs()
    elif selected_ids and all(round_id.startswith("R") for round_id in selected_ids):
        known_specs = default_round_specs()
    else:
        known_specs = (
            *default_round_specs(),
            *recovery_round_specs(),
            *missing_candidate_round_specs(),
            *structured_confirmation_round_specs(),
            *compact_finalizer_round_specs(),
            *external_pressure_round_specs(),
            *external_pressure_replication_round_specs(),
            *incumbent_guard_round_specs(),
            *answer_commit_round_specs(),
            *primary_tail_continuation_round_specs(),
        )
    for spec in known_specs:
        report = fresh_by_id.get(spec.round_id)
        if report is None and spec.round_id not in selected_ids:
            report = _load_completed_round_report(output_root, spec.round_id)
            if report is not None:
                reused.append(spec.round_id)
        if report is not None:
            merged.append(report)
    for report in fresh_reports:
        if str(report.get("round_id")) not in {item.get("round_id") for item in merged}:
            merged.append(report)
    return merged, reused


def run_matrix(
    output_root: Path,
    *,
    rounds: list[RoundSpec] | None = None,
    workers: int = 3,
    timeout: int = 120,
    matrix_id: str = "ROBUSTNESS-MATRIX-20261005",
) -> dict[str, Any]:
    """Run the requested rounds sequentially and write one aggregate report."""

    if not 1 <= workers <= 3:
        raise ValueError("workers_must_be_between_1_and_3")
    if timeout <= 0:
        raise ValueError("timeout_must_be_positive")
    _assert_scoring_dependencies()
    selected_rounds = rounds or list(default_round_specs())
    output_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    reports = [
        _run_round(
            spec,
            output_root=output_root,
            workers=workers,
            timeout=timeout,
        )
        for spec in selected_rounds
    ]
    reports, reused_round_ids = _merge_round_reports(output_root, selected_rounds, fresh_reports=reports)
    arm_summaries = _summarize_reports_by_profile(reports)
    paired_records = _paired_record_count(reports)
    aggregate = {
        "run_id": matrix_id,
        "status": "completed",
        "diagnostic_only": True,
        "evaluation_scope": "local_replay",
        "official_evaluation": False,
        "round_count": len(reports),
        "round_ids": [report["round_id"] for report in reports],
        "fresh_round_ids": [report["round_id"] for report in reports if report["round_id"] in {item.round_id for item in selected_rounds}],
        "reused_round_ids": reused_round_ids,
        "correct": sum(report["correct"] for report in reports),
        "incorrect": sum(report["incorrect"] for report in reports),
        "invalid": sum(report["invalid"] for report in reports),
        "model_errors": sum(report["model_errors"] for report in reports),
        "total_records": sum(report["records"] for report in reports),
        "paired_records": paired_records,
        "total_model_calls": sum(report["total_model_calls"] for report in reports),
        "truncation_count": sum(report.get("truncation_count", 0) for report in reports),
        "compact_finalizer_activations": sum(
            report.get("compact_finalizer_activations", 0) for report in reports
        ),
        "compact_finalizer_trigger_reason_counts": _merge_counter_dicts(
            report.get("compact_finalizer_trigger_reason_counts", {})
            for report in reports
        ),
        "incumbent_guard_activations": sum(
            report.get("incumbent_guard_activations", 0) for report in reports
        ),
        "primary_tail_continuation_activations": sum(
            report.get("primary_tail_continuation_activations", 0) for report in reports
        ),
        "incumbent_guard_reason_counts": _merge_counter_dicts(
            report.get("incumbent_guard_reason_counts", {})
            for report in reports
        ),
        "arm_summaries": arm_summaries,
        "rounds": reports,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (output_root / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "result.md").write_text(
        (
            f"# {matrix_id}\n\n"
            f"完成 {aggregate['round_count']} 轮、"
            f"{aggregate['paired_records'] if aggregate['paired_records'] is not None else aggregate['total_records']} 条"
            f"{'配对记录' if aggregate['paired_records'] is not None else '运行记录'}"
            f"（{aggregate['total_records']} 条臂记录）；"
            f"correct={aggregate['correct']}；incorrect={aggregate['incorrect']}；"
            f"invalid={aggregate['invalid']}；model_errors={aggregate['model_errors']}；"
            f"truncation_count={aggregate['truncation_count']}；"
            f"compact_finalizer_activations={aggregate['compact_finalizer_activations']}；"
            f"incumbent_guard_activations={aggregate['incumbent_guard_activations']}；"
            f"primary_tail_continuation_activations={aggregate.get('primary_tail_continuation_activations', 0)}。\n\n"
            f"按 profile 汇总：{json.dumps(arm_summaries, ensure_ascii=False, sort_keys=True)}\n\n"
            "所有结果均为 local_replay，不能替代官方隐藏集评测。\n"
        ),
        encoding="utf-8",
    )
    return aggregate


def main() -> int:
    """Parse matrix options and run the real-endpoint experiment rounds."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "artifacts" / "robustness-matrix-20261005"),
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--matrix-id", default="ROBUSTNESS-MATRIX-20261005")
    parser.add_argument("--json", action="store_true", help="print the full aggregate JSON")
    parser.add_argument(
        "--rounds",
        help="Comma-separated round ids such as R01,R02; default runs all ten.",
    )
    args = parser.parse_args()
    available = {
        spec.round_id: spec
        for spec in (
            *default_round_specs(),
            *recovery_round_specs(),
            *missing_candidate_round_specs(),
            *structured_confirmation_round_specs(),
            *compact_finalizer_round_specs(),
            *external_pressure_round_specs(),
            *external_pressure_replication_round_specs(),
            *incumbent_guard_round_specs(),
            *answer_commit_round_specs(),
            *primary_tail_continuation_round_specs(),
        )
    }
    selected = None
    if args.rounds:
        requested = [value.strip().upper() for value in args.rounds.split(",") if value.strip()]
        unknown = [value for value in requested if value not in available]
        if unknown:
            parser.error("unknown_round:" + ",".join(unknown))
        selected = [available[value] for value in requested]
    aggregate = run_matrix(
        Path(args.output_dir),
        rounds=selected,
        workers=args.workers,
        timeout=args.timeout,
        matrix_id=args.matrix_id,
    )
    if args.json:
        print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    else:
        print(format_matrix_summary(aggregate, Path(args.output_dir).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
