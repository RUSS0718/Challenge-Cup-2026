"""Small local runner for the official EACL submission facade."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_client import InternChatClient
from reasoning_agent.artifacts import ArtifactManager, RunContext
from reasoning_agent.eacl_contracts import EACLConfig
from user_agent import ReasoningAgent


def load_jsonl(path: Path) -> list[dict]:
    """Load non-empty JSONL rows and assign a stable line index when absent."""

    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        row.setdefault("idx", line_number)
        rows.append(row)
    return rows


def parse_args() -> argparse.Namespace:
    """Parse the local input, output, and bounded EACL controls."""

    parser = argparse.ArgumentParser(description="Run the Challenge Cup EACL agent.")
    parser.add_argument("--input_file", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--max_model_calls", type=int, default=3)
    parser.add_argument("--total_token_budget", type=int, default=12_288)
    parser.add_argument("--timeout_seconds", type=int, default=None)
    parser.add_argument("--retry_count", type=int, default=None)
    return parser.parse_args()


def run(args: argparse.Namespace) -> Path:
    """Solve every input row serially and persist one bounded artifact stream."""

    input_path = Path(args.input_file)
    context = RunContext.create("grh-eacl-v1", dataset=input_path.name, model="intern-s2")
    manager = ArtifactManager(Path(args.output_dir))
    client_kwargs = {}
    if args.timeout_seconds is not None:
        client_kwargs["timeout"] = args.timeout_seconds
    if args.retry_count is not None:
        client_kwargs["retry"] = args.retry_count
    agent = ReasoningAgent(
        InternChatClient(**client_kwargs),
        config=EACLConfig(
            max_model_calls=args.max_model_calls,
            total_token_budget=args.total_token_budget,
        ),
    )
    manager.save_manifest(
        context,
        requested_items=len(load_jsonl(input_path)),
        max_model_calls=args.max_model_calls,
        total_token_budget=args.total_token_budget,
        status="running",
    )
    rows = []
    for item in load_jsonl(input_path):
        result = agent.solve(item["problem"], {"idx": item["idx"]})
        row = {"idx": item["idx"], "status": "success", **result}
        rows.append(row)
        manager.append_answer(row)
    manager.save_answers(rows)
    manager.save_manifest(context, status="completed", completed_items=len(rows))
    return manager.run_dir


if __name__ == "__main__":
    print(run(parse_args()))
