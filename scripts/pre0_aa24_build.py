"""PRE0-AA-001: build the frozen 24-item A/A dataset from deduplicated legacy84.

Algorithm (preregistration §3): complex48 ∪ medium60 dedup by normalized
problem text (NFKC, whitespace-stripped, lowercased) -> exactly 84 unique
items; stratify by the runtime classifier into the six task types; within each
class sort by SHA-256 of the normalized problem and take the first 4.  Any
class with fewer than 4 items aborts the window (no degraded fallback).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from user_agent import classify_problem_type  # noqa: E402
from scripts.analyze_paired_ab import detect_dataset_overlap, normalize_problem_text  # noqa: E402

EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-AA-001"
SOURCES = [
    ("complex48", REPO_ROOT / "sample_data/complex_capability_freeze_48.jsonl"),
    ("medium60", REPO_ROOT / "sample_data/medium_capability_freeze_60.jsonl"),
]
EXPECTED_UNIQUE = 84
PER_CLASS = 4


def main() -> None:
    overlap = detect_dataset_overlap([path for _, path in SOURCES])
    pair_key = next(iter(overlap["overlaps"]))
    shared = overlap["overlaps"][pair_key]["count"]
    if shared != 24 or overlap["union_unique"] != EXPECTED_UNIQUE:
        raise SystemExit(
            f"legacy_dedup_mismatch: shared={shared} union={overlap['union_unique']} "
            f"(expected 24 shared / {EXPECTED_UNIQUE} unique)"
        )

    seen: set[str] = set()
    unique_items: list[dict] = []
    for source_name, path in SOURCES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            digest = hashlib.sha256(normalize_problem_text(item["problem"]).encode("utf-8")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            unique_items.append({
                "source_dataset": source_name,
                "source_idx": item["idx"],
                "problem": item["problem"],
                "answer": str(item["answer"]),
                "stored_task_type": item.get("task_type"),
                "runtime_type": classify_problem_type(item["problem"]),
                "norm_sha256": digest,
            })

    by_class: dict[str, list[dict]] = {}
    for item in unique_items:
        by_class.setdefault(item["runtime_type"], []).append(item)

    selected: list[dict] = []
    for task_type in sorted(by_class):
        pool = sorted(by_class[task_type], key=lambda item: item["norm_sha256"])
        if len(pool) < PER_CLASS:
            raise SystemExit(f"class_underfilled:{task_type}: {len(pool)} < {PER_CLASS}")
        for item in pool[:PER_CLASS]:
            selected.append(item)

    selected.sort(key=lambda item: item["norm_sha256"])
    rows = []
    for new_idx, item in enumerate(selected):
        rows.append({
            "idx": new_idx,
            "problem": item["problem"],
            "answer": item["answer"],
            "source_dataset": item["source_dataset"],
            "source_idx": item["source_idx"],
            "runtime_type": item["runtime_type"],
            "norm_sha256": item["norm_sha256"],
        })

    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    dataset_path = EXPERIMENT_DIR / "aa24_dataset.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    dataset_sha = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    class_counts: dict[str, int] = {}
    for row in rows:
        class_counts[row["runtime_type"]] = class_counts.get(row["runtime_type"], 0) + 1

    manifest = {
        "experiment": "PRE0-AA-001",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [str(path) for _, path in SOURCES],
        "dedup": {"shared_problems": shared, "unique_total": overlap["union_unique"]},
        "selection": {
            "classifier": "user_agent.classify_problem_type (runtime)",
            "sort_key": "sha256(normalized problem text)",
            "per_class": PER_CLASS,
            "class_counts": class_counts,
        },
        "dataset_sha256": dataset_sha,
        "item_count": len(rows),
        "norm_algorithm": "NFKC -> remove all whitespace -> lowercase",
    }
    (EXPERIMENT_DIR / "build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
