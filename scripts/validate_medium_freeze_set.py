"""Validate the 60-item medium freeze set without invoking the model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support both ``python scripts/validate_medium_freeze_set.py`` and module use.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_dev import judge_correct

REQUIRED = {
    "idx", "task_type", "subject", "source", "source_url", "source_ref",
    "adaptation", "problem", "answer", "verification", "is_long", "is_multi_domain",
}
TASK_TYPES = {"choice", "fill_blank", "calculation", "derivation", "proof", "explanation"}


def validate(path: Path, *, require_public_sources: bool = False) -> list[str]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        items = [json.loads(line) for line in handle if line.strip()]
    if len(items) != 60:
        errors.append(f"dataset_size:{len(items)}")
    seen_idx: set[int] = set()
    seen_problem: set[str] = set()
    for pos, item in enumerate(items):
        idx = item.get("idx", pos)
        missing = REQUIRED - set(item)
        if missing:
            errors.append(f"missing_fields:{idx}:{','.join(sorted(missing))}")
        if not isinstance(item.get("idx"), int) or item["idx"] in seen_idx:
            errors.append(f"bad_or_duplicate_idx:{idx}")
        seen_idx.add(item.get("idx"))
        problem = str(item.get("problem", "")).strip()
        if not problem or problem in seen_problem:
            errors.append(f"bad_or_duplicate_problem:{idx}")
        seen_problem.add(problem)
        if item.get("task_type") not in TASK_TYPES:
            errors.append(f"bad_task_type:{idx}")
        if require_public_sources and item.get("source") != "ai_generated" and not str(item.get("source_url", "")).startswith("https://"):
            errors.append(f"bad_source_url:{idx}")
        if require_public_sources and item.get("source") == "ai_generated":
            errors.append(f"non_public_source:{idx}")
        if not str(item.get("answer", "")).strip():
            errors.append(f"empty_answer:{idx}")
        if judge_correct(str(item.get("answer", "")), str(item.get("answer", "")), str(item.get("task_type", ""))) != "correct":
            errors.append(f"answer_not_self_judgeable:{idx}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--require-public-sources", action="store_true")
    args = parser.parse_args()
    errors = validate(args.dataset, require_public_sources=args.require_public_sources)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"valid: {args.dataset} (60 items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
