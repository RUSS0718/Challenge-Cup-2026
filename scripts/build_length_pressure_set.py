"""Build a length-calibration pressure set from per-item historical telemetry.

The input telemetry must contain an item id, completion tokens, and the token
ceiling used for that call.  Aggregate reports are intentionally insufficient:
without item-level evidence this script refuses to select a question.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


THRESHOLD = 0.75
DEFAULT_TARGET_SIZE = 24
MIN_PRESSURE_SIZE = 20
MAX_PRESSURE_SIZE = 30
ITEM_FIELDS = (
    "idx",
    "problem",
    "task_type",
    "subject",
    "source",
    "source_url",
    "source_ref",
    "adaptation",
    "is_long",
    "is_multi_domain",
)


def load_jsonl(path: Path) -> list[dict]:
    """Load JSON objects from a non-empty JSONL file."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            rows.append(value)
    return rows


def _number(record: dict, *names: str) -> float | None:
    for name in names:
        value = record.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _evidence(record: dict, telemetry_source: str) -> dict | None:
    completion_tokens = _number(record, "completion_tokens", "main_completion_tokens")
    ceiling_tokens = _number(record, "ceiling_tokens", "max_tokens")
    if ceiling_tokens is None:
        budget = record.get("budget_config")
        if isinstance(budget, dict):
            ceiling_tokens = _number(budget, "max_tokens")
    if completion_tokens is None or ceiling_tokens is None or ceiling_tokens <= 0:
        return None
    fraction = completion_tokens / ceiling_tokens
    if fraction < THRESHOLD:
        return None
    result = {
        "completion_tokens": int(completion_tokens),
        "ceiling_tokens": int(ceiling_tokens),
        "completion_fraction": round(fraction, 6),
        "finish_reason": record.get("finish_reason", record.get("main_finish_reason")),
        "variant": record.get("variant"),
        "telemetry_source": telemetry_source,
    }
    return {key: value for key, value in result.items() if value is not None}


def build_pressure_set(
    source_items: Iterable[dict],
    telemetry_records: Iterable[dict],
    *,
    telemetry_source: str,
    target_size: int = DEFAULT_TARGET_SIZE,
) -> list[dict]:
    """Select a deterministic 20–30 item set with auditable length evidence.

    If an item has multiple historical observations, its highest observed
    completion fraction is retained.  Answers and verification fields are
    deliberately not copied from the source dataset.
    """
    if not MIN_PRESSURE_SIZE <= target_size <= MAX_PRESSURE_SIZE:
        raise ValueError(f"target size must be {MIN_PRESSURE_SIZE}..{MAX_PRESSURE_SIZE}")

    by_idx: dict[int, dict] = {}
    for record in telemetry_records:
        idx = record.get("idx")
        evidence = _evidence(record, telemetry_source)
        if not isinstance(idx, int) or evidence is None:
            continue
        previous = by_idx.get(idx)
        if previous is None or evidence["completion_fraction"] > previous["completion_fraction"]:
            by_idx[idx] = evidence

    candidates: list[dict] = []
    for source_item in source_items:
        idx = source_item.get("idx")
        if not isinstance(idx, int) or idx not in by_idx:
            continue
        item = {field: source_item[field] for field in ITEM_FIELDS if field in source_item}
        item["length_evidence"] = by_idx[idx]
        candidates.append(item)

    candidates.sort(key=lambda item: (-item["length_evidence"]["completion_fraction"], item["idx"]))
    if len(candidates) < target_size:
        raise ValueError(
            f"fewer than target size: {len(candidates)} qualifying items for target {target_size}"
        )
    return candidates[:target_size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dataset", type=Path)
    parser.add_argument("telemetry_jsonl", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-size", type=int, default=DEFAULT_TARGET_SIZE)
    args = parser.parse_args()

    source = load_jsonl(args.source_dataset)
    telemetry = load_jsonl(args.telemetry_jsonl)
    source_name = args.telemetry_jsonl.as_posix()
    result = build_pressure_set(
        source,
        telemetry,
        telemetry_source=source_name,
        target_size=args.target_size,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for item in result:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(result)} items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
