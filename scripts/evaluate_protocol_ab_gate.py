"""Gate two-round protocol A/B reports before any default-path promotion."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def check_gate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        grouped[(str(report.get("input_file", "")), str(report.get("variant", "")))].append(report)

    failures: list[str] = []
    comparisons: list[dict[str, Any]] = []
    datasets = sorted({key[0] for key in grouped})
    variants = sorted({key[1] for key in grouped if key[1] != "baseline86"})
    for dataset in datasets:
        baseline_rounds = {int(r.get("round", 0)): r for r in grouped.get((dataset, "baseline86"), [])}
        if len(baseline_rounds) < 2:
            failures.append(f"{dataset}:baseline_missing_two_rounds")
            continue
        for variant in variants:
            rounds = {int(r.get("round", 0)): r for r in grouped.get((dataset, variant), [])}
            if len(rounds) < 2:
                failures.append(f"{dataset}:{variant}:missing_two_rounds")
                continue
            for round_no in (1, 2):
                baseline = baseline_rounds.get(round_no)
                candidate = rounds.get(round_no)
                if baseline is None or candidate is None:
                    failures.append(f"{dataset}:{variant}:round{round_no}:missing_pair")
                    continue
                checks = {
                    "accuracy_not_below_baseline": candidate.get("accuracy", 0) >= baseline.get("accuracy", 0),
                    "invalid_not_above_baseline": candidate.get("invalid", 0) <= baseline.get("invalid", 0),
                    "incorrect_not_above_baseline": candidate.get("incorrect", 0) <= baseline.get("incorrect", 0),
                    "main_length_not_above_baseline": candidate.get("main_length_rate", 1.0) <= baseline.get("main_length_rate", 1.0),
                    "nonempty_100pct": candidate.get("final_response_nonempty_rate") == 1.0,
                    "average_calls_le_1.5": candidate.get("average_model_calls", 999) <= 1.5,
                    "max_calls_le_2": candidate.get("max_model_calls", 999) <= 2,
                }
                for name, passed in checks.items():
                    if not passed:
                        failures.append(f"{dataset}:{variant}:round{round_no}:{name}")
                comparisons.append({
                    "dataset": dataset,
                    "variant": variant,
                    "round": round_no,
                    "baseline_accuracy": baseline.get("accuracy"),
                    "candidate_accuracy": candidate.get("accuracy"),
                    "baseline_invalid": baseline.get("invalid"),
                    "candidate_invalid": candidate.get("invalid"),
                    "baseline_incorrect": baseline.get("incorrect"),
                    "candidate_incorrect": candidate.get("incorrect"),
                    "baseline_main_length_rate": baseline.get("main_length_rate"),
                    "candidate_main_length_rate": candidate.get("main_length_rate"),
                    "checks": checks,
                })
    return {"passed": not failures, "failures": failures, "comparisons": comparisons}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check two-round protocol A/B promotion gates.")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    result = check_gate(payload if isinstance(payload, list) else payload.get("reports", []))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()


