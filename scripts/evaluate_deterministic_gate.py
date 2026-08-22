"""Gate two deterministic-solver audit reports before any runtime promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(first: dict[str, Any], second: dict[str, Any], minimum_correct: int = 10) -> dict[str, Any]:
    def correct_ids(report: dict[str, Any]) -> set[Any]:
        return {record.get("idx") for record in report.get("records", []) if record.get("verdict") == "correct"}
    ids1, ids2 = correct_ids(first), correct_ids(second)
    failures = []
    for label, report in (("round1", first), ("round2", second)):
        if report.get("correct", 0) < minimum_correct:
            failures.append(f"{label}:correct_below_{minimum_correct}")
        if report.get("incorrect", 0) != 0:
            failures.append(f"{label}:incorrect_nonzero")
        if report.get("unknown", 0) != 0:
            failures.append(f"{label}:unknown_nonzero")
    if ids1 != ids2:
        failures.append("correct_id_sets_differ")
    return {"passed": not failures, "failures": failures, "round1_correct_ids": sorted(ids1), "round2_correct_ids": sorted(ids2)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round1", type=Path)
    parser.add_argument("round2", type=Path)
    args = parser.parse_args()
    result = gate(load(args.round1), load(args.round2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
