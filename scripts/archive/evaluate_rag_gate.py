"""Strict gate for two-round baseline-vs-RAG evaluation reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _round_gate(baseline: dict[str, Any], rag: dict[str, Any], min_gain: float, max_regression: float) -> list[str]:
    failures = []
    if rag.get("accuracy", 0.0) - baseline.get("accuracy", 0.0) < min_gain:
        failures.append("medium_gain_below_gate")
    if rag.get("regression_accuracy", baseline.get("regression_accuracy", 0.0)) < baseline.get("regression_accuracy", 0.0) - max_regression:
        failures.append("regression_backslide")
    if rag.get("empty_final_response_count", 0) != 0:
        failures.append("empty_final_response")
    if rag.get("timeout_count", 0) != 0:
        failures.append("timeout")
    if rag.get("failed_item_ids"):
        failures.append("failed_items_present")
    if rag.get("status") == "error":
        failures.append("evaluation_status_error")
    if rag.get("average_model_calls", 0.0) > baseline.get("average_model_calls", float("inf")):
        failures.append("average_calls_increased")
    return failures


def gate(reports: list[tuple[dict[str, Any], dict[str, Any]]], min_gain: float = 5 / 60, max_regression: float = 2 / 100) -> dict[str, Any]:
    round_failures = [_round_gate(baseline, rag, min_gain, max_regression) for baseline, rag in reports]
    failures = [f"round{index + 1}:{failure}" for index, items in enumerate(round_failures) for failure in items]
    return {"passed": not failures, "failures": failures, "round_failures": round_failures, "min_gain": min_gain, "max_regression": max_regression}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs=4, type=Path, metavar="REPORT", help="baseline1 rag1 baseline2 rag2")
    args = parser.parse_args()
    result = gate([(_load(args.reports[0]), _load(args.reports[1])), (_load(args.reports[2]), _load(args.reports[3]))])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
