"""Audit the isolated deterministic solver against local datasets.

This is evaluator-only code: reference answers are read here, never by the
runtime agent.  A solver result is counted as a hit only when it is supported
and the existing conservative judge returns ``correct``; unsupported results
are reported separately.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from deterministic_math import solve_deterministic  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402


def load_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in items:
        result = solve_deterministic(str(item.get("problem", "")))
        status = result.get("status")
        verdict = "unsupported"
        if status == "supported":
            verdict = judge_correct(
                str(result.get("answer", "")),
                str(item.get("answer", "")),
                str(item.get("task_type", "")),
            )
        records.append(
            {
                "idx": item.get("idx"),
                "status": status,
                "verdict": verdict,
                "reason": result.get("reason"),
            }
        )
    supported = [record for record in records if record["status"] == "supported"]
    correct = [record for record in supported if record["verdict"] == "correct"]
    incorrect = [record for record in supported if record["verdict"] == "incorrect"]
    unknown = [record for record in supported if record["verdict"] == "unknown"]
    return {
        "total": len(records),
        "supported": len(supported),
        "unsupported": len(records) - len(supported),
        "correct": len(correct),
        "incorrect": len(incorrect),
        "unknown": len(unknown),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(load_items(args.dataset))
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
