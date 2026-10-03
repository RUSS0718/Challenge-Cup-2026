"""Run the experimental EACL control plane over a JSONL problem set.

The runner is deliberately separate from ``main.py`` so a local experiment
cannot silently change the official ``ReasoningAgent`` submission profile.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

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
    return parser.parse_args()


def run(args: argparse.Namespace) -> Path:
    """Run serially and save answers, metrics, and manifest atomically."""

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
    context = RunContext.create(
        "grh-eacl-v1",
        dataset=input_path.name,
        model=getattr(client, "model", None),
    )
    manager = ArtifactManager.from_context(args.output_root, context)
    manager.save_manifest(
        context,
        requested_items=len(rows),
        thinking_on=args.thinking_on,
        off_finalizer=args.off_finalizer,
        max_model_calls=args.max_model_calls,
        total_token_budget=args.total_token_budget,
        timeout_seconds=args.timeout_seconds,
        retry_count=args.retry_count,
    )

    answers: list[dict[str, Any]] = []
    counts = {
        "completed": 0,
        "unknown": 0,
        "error": 0,
        "model_calls": 0,
        "requested_tokens": 0,
        "completion_tokens": 0,
        "finish_reason_length": 0,
        "call_latencies_seconds": [],
        "decision_actions": {},
    }
    for row in rows:
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
                "decision": result.get("decision", {}),
                "trace": result.get("trace", []),
            }
            counts["completed"] += 1
            counts["model_calls"] += int(result.get("model_calls", 0) or 0)
            counts["requested_tokens"] += int(result.get("requested_tokens", 0) or 0)
            if final_response == "UNKNOWN":
                counts["unknown"] += 1
            action = str(result.get("decision", {}).get("action", "UNKNOWN"))
            actions = counts["decision_actions"]
            actions[action] = int(actions.get(action, 0)) + 1
            for event in result.get("trace", []):
                if event.get("stage") != "call":
                    continue
                completion = event.get("completion_tokens")
                if isinstance(completion, int):
                    counts["completion_tokens"] += completion
                duration = event.get("duration_ms")
                if isinstance(duration, (int, float)):
                    counts["call_latencies_seconds"].append(round(float(duration) / 1000.0, 3))
                if str(event.get("finish_reason", "")).casefold() == "length":
                    counts["finish_reason_length"] += 1
        except Exception as exc:  # keep one row per problem for diagnosis
            answer = {
                "idx": row["idx"],
                "status": "error",
                "final_response": "UNKNOWN",
                "error": {"type": type(exc).__name__, "category": "runner_error"},
                "trace": [],
            }
            counts["error"] += 1
        answers.append(answer)
        print(f"finished idx={row['idx']} status={answer['status']}")

    manager.save_answers(answers)
    latencies = list(counts.pop("call_latencies_seconds"))
    counts["average_latency_seconds"] = round(statistics.mean(latencies), 3) if latencies else None
    counts["p95_latency_seconds"] = round(_percentile(latencies, 0.95), 3) if latencies else None
    counts["records"] = len(answers)
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
