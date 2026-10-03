"""Run the experimental EACL control plane over a JSONL problem set.

The runner is deliberately separate from ``main.py`` so a local experiment
cannot silently change the official ``ReasoningAgent`` submission profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

# Keep the documented ``python scripts/run_eacl.py`` invocation independent of
# the caller's current import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_client import InternChatClient
from reasoning_agent.artifacts import ArtifactManager, RunContext
from reasoning_agent.eacl_agent import EACLReasoningAgent
from reasoning_agent.eacl_contracts import EACLConfig


def _load_jsonl(path: Path, limit: int | None) -> list[dict[str, Any]]:
    """Load bounded problem records and assign missing line indexes."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("idx", line_number)
            if not isinstance(row.get("problem"), str) or not row["problem"].strip():
                continue
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _parse_args() -> argparse.Namespace:
    """Parse the explicit experiment inputs and bounded EACL controls."""

    parser = argparse.ArgumentParser(description="Run the GRH EACL experimental pipeline.")
    parser.add_argument("--input_file", required=True, help="Problem JSONL path.")
    parser.add_argument("--output_root", default="artifacts", help="Artifact root directory.")
    parser.add_argument("--max_items", type=int, default=None, help="Optional smoke-test item cap.")
    parser.add_argument("--max_model_calls", type=int, default=3)
    parser.add_argument("--total_token_budget", type=int, default=12_288)
    parser.add_argument("--timeout_seconds", type=int, default=None)
    parser.add_argument("--retry_count", type=int, default=None)
    parser.add_argument("--thinking_on", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--off_finalizer", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--run_dir", default=None, help="Optional fixed artifact directory.")
    parser.add_argument("--resume", action="store_true", help="Resume an existing run_dir.")
    return parser.parse_args()


def _load_existing_answers(path: Path) -> dict[str, dict[str, Any]]:
    """Load durable answer checkpoints keyed by item id, ignoring malformed lines."""

    answers: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return answers
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and "idx" in row:
                answers[str(row["idx"])] = row
    return answers


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load a prior manifest for resume compatibility checks."""

    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    """Hash a dataset so a resumed run cannot silently change its input."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    """Return the current commit when the runner is inside a Git checkout."""

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _validate_resume_manifest(
    manifest: dict[str, Any],
    *,
    dataset_sha256: str,
    thinking_on: bool,
    off_finalizer: bool,
    max_model_calls: int,
    total_token_budget: int,
) -> None:
    """Reject a resume when its input or bounded execution contract changed."""

    if not manifest:
        return
    if manifest.get("dataset_sha256") not in {None, dataset_sha256}:
        raise ValueError("resume_dataset_hash_mismatch")
    for field, value in {
        "thinking_on": thinking_on,
        "off_finalizer": off_finalizer,
        "max_model_calls": max_model_calls,
        "total_token_budget": total_token_budget,
    }.items():
        if field in manifest and manifest[field] != value:
            raise ValueError(f"resume_config_mismatch:{field}")


def _metrics_from_answers(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute aggregate telemetry from checkpoints, including resumed rows."""

    counts: dict[str, Any] = {
        "completed": sum(row.get("status") == "success" for row in answers),
        "unknown": sum(
            row.get("status") == "success" and row.get("final_response") == "UNKNOWN"
            for row in answers
        ),
        "error": sum(row.get("status") == "error" for row in answers),
        "model_calls": 0,
        "requested_tokens": 0,
        "completion_tokens": 0,
        "finish_reason_length": 0,
        "call_latencies_seconds": [],
        "decision_actions": {},
    }
    for row in answers:
        counts["model_calls"] += int(row.get("model_calls", 0) or 0)
        counts["requested_tokens"] += int(row.get("requested_tokens", 0) or 0)
        decision = row.get("decision")
        if isinstance(decision, dict):
            action = str(decision.get("action", "UNKNOWN"))
            counts["decision_actions"][action] = counts["decision_actions"].get(action, 0) + 1
        trace = row.get("trace")
        if not isinstance(trace, list):
            continue
        for event in trace:
            if not isinstance(event, dict) or event.get("stage") != "call":
                continue
            completion = event.get("completion_tokens")
            if isinstance(completion, int):
                counts["completion_tokens"] += completion
            duration = event.get("duration_ms")
            if isinstance(duration, (int, float)):
                counts["call_latencies_seconds"].append(round(float(duration) / 1000.0, 3))
            if str(event.get("finish_reason", "")).casefold() == "length":
                counts["finish_reason_length"] += 1
    latencies = list(counts.pop("call_latencies_seconds"))
    counts["average_latency_seconds"] = round(statistics.mean(latencies), 3) if latencies else None
    counts["p95_latency_seconds"] = round(_percentile(latencies, 0.95), 3) if latencies else None
    counts["records"] = len(answers)
    return counts


def run(args: argparse.Namespace) -> Path:
    """Run serially with per-item checkpoints and optional resume support."""

    input_path = Path(args.input_file)
    rows = _load_jsonl(input_path, args.max_items)
    client_kwargs = {}
    if args.timeout_seconds is not None:
        client_kwargs["timeout"] = args.timeout_seconds
    if args.retry_count is not None:
        client_kwargs["retry"] = args.retry_count
    client = InternChatClient(**client_kwargs)
    config = EACLConfig(
        max_model_calls=args.max_model_calls,
        total_token_budget=args.total_token_budget,
        allow_thinking_on=args.thinking_on,
        enable_off_finalizer=args.off_finalizer,
    )
    agent = EACLReasoningAgent(client, config=config)
    git_commit = _git_commit()
    dataset_sha256 = _sha256_file(input_path)
    if args.resume and not args.run_dir:
        raise ValueError("--resume_requires_--run_dir")
    if args.run_dir:
        run_dir = Path(args.run_dir)
        context = RunContext(
            run_dir.name,
            "grh-eacl-v1",
            dataset=input_path.name,
            model=getattr(client, "model", None),
            git_commit=git_commit,
        )
        manager = ArtifactManager(run_dir)
    else:
        context = RunContext.create(
            "grh-eacl-v1",
            dataset=input_path.name,
            model=getattr(client, "model", None),
            git_commit=git_commit,
        )
        manager = ArtifactManager.from_context(args.output_root, context)
    existing = _load_existing_answers(manager.run_dir / "answers.jsonl")
    prior_manifest = _load_manifest(manager.run_dir / "run_manifest.json")
    if existing and not args.resume:
        raise FileExistsError("run_dir_contains_answers_use_--resume")
    if args.resume:
        _validate_resume_manifest(
            prior_manifest,
            dataset_sha256=dataset_sha256,
            thinking_on=args.thinking_on,
            off_finalizer=args.off_finalizer,
            max_model_calls=args.max_model_calls,
            total_token_budget=args.total_token_budget,
        )
    answers_by_idx = dict(existing)
    manager.save_manifest(
        context,
        requested_items=len(rows),
        dataset_sha256=dataset_sha256,
        resumed_records=len(existing),
        status="running",
        thinking_on=args.thinking_on,
        off_finalizer=args.off_finalizer,
        max_model_calls=args.max_model_calls,
        total_token_budget=args.total_token_budget,
        timeout_seconds=args.timeout_seconds,
        retry_count=args.retry_count,
    )

    try:
        for row in rows:
            item_key = str(row["idx"])
            if item_key in answers_by_idx:
                print(f"skip idx={row['idx']} checkpointed")
                continue
            try:
                result = agent.solve(row["problem"], {"idx": row["idx"]})
                final_response = result.get("final_response", "UNKNOWN")
                if not isinstance(final_response, str) or not final_response.strip():
                    final_response = "UNKNOWN"
                answer = {
                    "idx": row["idx"],
                    "status": "success",
                    "final_response": final_response,
                    "extracted_answer": result.get("extracted_answer", ""),
                    "model_calls": result.get("model_calls", 0),
                    "requested_tokens": result.get("requested_tokens", 0),
                    "decision": result.get("decision", {}),
                    "trace": result.get("trace", []),
                }
            except Exception as exc:  # keep one row per problem for diagnosis
                answer = {
                    "idx": row["idx"],
                    "status": "error",
                    "final_response": "UNKNOWN",
                    "error": {"type": type(exc).__name__, "category": "runner_error"},
                    "trace": [],
                }
            manager.append_answer(answer)
            answers_by_idx[item_key] = answer
            print(f"finished idx={row['idx']} status={answer['status']}")
    except KeyboardInterrupt:
        partial = list(answers_by_idx.values())
        manager.save_manifest(
            context,
            status="interrupted",
            completed_items=len(partial),
            partial_counts=_metrics_from_answers(partial),
        )
        raise

    answers = [answers_by_idx[str(row["idx"])] for row in rows if str(row["idx"]) in answers_by_idx]
    manager.save_answers(answers)
    counts = _metrics_from_answers(answers)
    manager.save_metrics(counts)
    manager.save_report({"status": "completed", "counts": counts})
    manager.save_manifest(context, status="completed", completed_items=len(answers), final_counts=counts)
    return manager.run_dir


def _percentile(values: list[float], quantile: float) -> float:
    """Return a linear-interpolated percentile for a non-empty latency list."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def main() -> None:
    """Run the configured EACL experiment."""

    args = _parse_args()
    print(f"saved artifacts to {run(args)}")


if __name__ == "__main__":
    main()
