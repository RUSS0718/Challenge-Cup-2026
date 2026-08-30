"""Gate the deterministic solver's opt-in integration against model baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(baseline1: dict[str, Any], deterministic1: dict[str, Any], baseline2: dict[str, Any], deterministic2: dict[str, Any], regression_supported: int, minimum_new_rescues: int = 10) -> dict[str, Any]:
    failures: list[str] = []
    rounds = []
    for index, (baseline, det) in enumerate(((baseline1, deterministic1), (baseline2, deterministic2)), start=1):
        gain = det.get("accuracy", 0.0) - baseline.get("accuracy", 0.0)
        calls_ok = det.get("average_model_calls", float("inf")) <= baseline.get("average_model_calls", float("inf"))
        clean = not det.get("failed_item_ids") and det.get("timeout_count", 0) == 0 and det.get("empty_final_response_count", 0) == 0
        rounds.append({"round": index, "accuracy_gain": gain, "calls_non_increasing": calls_ok, "clean": clean})
        if gain < 0:
            failures.append(f"round{index}:accuracy_regression")
        if not calls_ok:
            failures.append(f"round{index}:calls_increased")
        if not clean:
            failures.append(f"round{index}:runtime_failure")
    if regression_supported != 0:
        failures.append("regression_112_supported_items_nonzero")
    if not (rounds[0]["accuracy_gain"] > 0 and rounds[1]["accuracy_gain"] > 0):
        failures.append("positive_gain_not_reproducible")
    baseline_records = {r.get("idx"): r for r in baseline2.get("records", [])}
    deterministic_records = {r.get("idx"): r for r in deterministic2.get("records", [])}
    new_rescues = sorted(
        idx for idx, det in deterministic_records.items()
        if det.get("verdict") == "correct" and baseline_records.get(idx, {}).get("verdict") in {"unknown", "incorrect"}
    )
    if len(new_rescues) < minimum_new_rescues:
        failures.append(f"new_rescues_below_{minimum_new_rescues}")
    return {"passed": not failures, "failures": failures, "rounds": rounds, "regression_112_supported": regression_supported, "new_rescues": new_rescues, "minimum_new_rescues": minimum_new_rescues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs=4, type=Path, metavar="REPORT", help="baseline1 deterministic1 baseline2 deterministic2")
    parser.add_argument("--regression-112-supported", type=int, required=True)
    parser.add_argument("--minimum-new-rescues", type=int, default=10)
    args = parser.parse_args()
    result = gate(*(load(path) for path in args.reports), regression_supported=args.regression_112_supported, minimum_new_rescues=args.minimum_new_rescues)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
