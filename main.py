"""Local JSONL runner for the competition reasoning agent."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List

from llm_client import InternChatClient
from reasoning_agent.artifacts import ArtifactManager
from user_agent import ReasoningAgent


LOCAL_MAX_CONCURRENCY = int(os.environ.get("LOCAL_MAX_CONCURRENCY", "3"))


def load_jsonl(path: Path) -> List[Dict]:
    items = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file):
            if not line.strip():
                continue
            item = json.loads(line)
            item.setdefault("idx", line_number)
            items.append(item)
    return items


def result_path(output_dir: Path, item: Dict) -> Path:
    return output_dir / f"{item['idx']}.json"


def is_processed(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def write_json(manager: ArtifactManager, filename: str, record: Dict) -> None:
    """Persist one per-problem result through the run artifact boundary."""

    manager.save_json(filename, record)


def build_output_record(item: Dict, agent_result: Dict) -> Dict:
    final_response = agent_result.get("final_response", "")
    if not isinstance(final_response, str) or not final_response.strip():
        raise ValueError("agent.solve must return a non-empty string field: final_response")

    output = {
        "idx": item["idx"],
        "status": "success",
        "final_response": final_response,
        "trace": agent_result.get("trace", []),
    }
    return output


def parse_args() -> argparse.Namespace:
    """Parse input/output paths and the local runtime profile selector."""

    parser = argparse.ArgumentParser(description="Competition sample reasoning agent.")
    parser.add_argument("--input_file", required=True, help="Path to input JSONL.")
    parser.add_argument("--output_dir", required=True, help="Directory for per-problem JSON outputs.")
    parser.add_argument(
        "--profile",
        choices=("submission",),
        default="submission",
        help="Run the imported submission entry; legacy profiles are archived.",
    )
    return parser.parse_args()


def solve_item(agent: ReasoningAgent, item: Dict) -> Dict:
    result = agent.solve(
        problem=item["problem"],
        metadata={"idx": item["idx"]},
    )
    return build_output_record(item, result)


async def process_item(
    agent: ReasoningAgent,
    item: Dict,
    manager: ArtifactManager,
    semaphore: asyncio.Semaphore,
) -> None:
    """Solve one item and save exactly one result inside the run directory."""

    path = result_path(manager.run_dir, item)
    if is_processed(path):
        print(f"Skip idx={item['idx']} because {path} already exists.")
        return

    async with semaphore:
        try:
            record = await asyncio.to_thread(solve_item, agent, item)
        except Exception as exc:  # noqa: BLE001 - keep one output file per input item.
            record = {
                "idx": item["idx"],
                "status": "error",
                "final_response": "",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "trace": [],
            }
        await asyncio.to_thread(write_json, manager, path.name, record)
        print(f"Finished idx={item['idx']}")


async def run(args: argparse.Namespace) -> None:
    """Run the imported entry with independent agent state for each problem."""

    input_path = Path(args.input_file)
    manager = ArtifactManager(Path(args.output_dir))

    items = load_jsonl(input_path)

    client = InternChatClient()
    semaphore = asyncio.Semaphore(LOCAL_MAX_CONCURRENCY)

    print(
        f"Loaded {len(items)} items. Profile: {args.profile}. "
        f"Max concurrency: {LOCAL_MAX_CONCURRENCY}."
    )
    tasks = [
        process_item(ReasoningAgent(client=client), item, manager, semaphore)
        for item in items
    ]
    await asyncio.gather(*tasks)
    print(f"Saved outputs to {manager.run_dir}")


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
