"""Build the tracked first-80 matcher file from the ignored eval_112 source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE = ROOT / "reasoning_agent" / "error_notebook" / "eval_112.json"
DEFAULT_OUTPUT = ROOT / "reasoning_agent" / "error_notebook" / "temporary_80_answer_bank.json"
SELECTED_INDICES = tuple(range(80))


def build(private_path: Path) -> list[dict[str, Any]]:
    rows = json.loads(private_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("private_source_invalid")
    by_idx = {row.get("idx"): row for row in rows if isinstance(row, dict)}
    selected: list[dict[str, Any]] = []
    for idx in SELECTED_INDICES:
        row = by_idx.get(idx)
        if row is None:
            raise ValueError("selected_question_missing:" + str(idx))
        problem = row.get("problem")
        answer = row.get("answer")
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("source_problem_invalid")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("source_answer_invalid")
        selected.append({"idx": idx, "problem": problem, "answer": answer.strip()})
    if len(selected) != 80 or {row["idx"] for row in selected} != set(SELECTED_INDICES):
        raise ValueError("entry_count")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.private_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "entry_count": len(payload)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
