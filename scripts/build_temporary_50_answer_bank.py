"""Build the frozen team-created 112-question bank from the local eval_112 source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE = ROOT / "reasoning_agent" / "error_notebook" / "eval_112.json"
DEFAULT_OUTPUT = ROOT / "reasoning_agent" / "error_notebook" / "temporary_50_answer_bank.json"

# Keep every reference index; the range is deterministic and covers 0..111.
SELECTED_INDICES = tuple(range(112))


def normalize_problem(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def build(private_path: Path) -> list[dict[str, Any]]:
    rows = json.loads(private_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("private_source_invalid")
    by_idx = {row.get("idx"): row for row in rows if isinstance(row, dict)}
    if any(idx not in by_idx for idx in SELECTED_INDICES):
        raise ValueError("selected_question_missing")

    selected = []
    seen: set[str] = set()
    for idx in SELECTED_INDICES:
        row = by_idx[idx]
        problem = row.get("problem")
        answer = row.get("answer")
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("source_problem_invalid")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("source_answer_invalid")
        normalized = normalize_problem(problem)
        if normalized in seen:
            raise ValueError("duplicate_problem")
        seen.add(normalized)
        selected.append({"idx": idx, "problem": problem, "answer": answer.strip()})

    if len(selected) != 112:
        raise ValueError("entry_count")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.private_source)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "entry_count": len(payload)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
