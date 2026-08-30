"""Gate two-round protocol A/B reports before any default-path promotion."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _parse_baseline_rounds(spec: str | None) -> dict[int, int] | None:
    """Map protocol variant rounds (1, 2) to explicitly chosen baseline rounds."""
    if spec is None:
        return None
    parts = [part.strip() for part in spec.split(",") if part.strip()]
    try:
        values = [int(part) for part in parts]
    except ValueError:
        raise SystemExit("--baseline-rounds expects comma-separated integers, e.g. 3,4")
    if len(values) != 2:
        raise SystemExit("--baseline-rounds needs exactly two rounds, e.g. 3,4")
    return {variant_round: baseline_round for variant_round, baseline_round in zip((1, 2), values)}


def check_gate(reports: list[dict[str, Any]], baseline_pairing: dict[int, int] | None = None,
               baseline_variant: str = "baseline86") -> dict[str, Any]:
    pairing = baseline_pairing or {1: 1, 2: 2}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        grouped[(str(report.get("input_file", "")), str(report.get("variant", "")))].append(report)

    failures: list[str] = []
    comparisons: list[dict[str, Any]] = []
    datasets = sorted({key[0] for key in grouped})
    variants = sorted({key[1] for key in grouped if key[1] != baseline_variant})
    for dataset in datasets:
        baseline_rounds = {int(r.get("round", 0)): r for r in grouped.get((dataset, baseline_variant), [])}
        if len(baseline_rounds) < 2:
            failures.append(f"{dataset}:baseline_missing_two_rounds")
            continue
        for variant in variants:
            rounds = {int(r.get("round", 0)): r for r in grouped.get((dataset, variant), [])}
            if len(rounds) < 2:
                failures.append(f"{dataset}:{variant}:missing_two_rounds")
                continue
            for round_no in sorted(pairing):
                baseline = baseline_rounds.get(pairing[round_no])
                candidate = rounds.get(round_no)
                if baseline is None or candidate is None:
                    failures.append(f"{dataset}:{variant}:round{round_no}:missing_pair")
                    continue
                budget_cap = int((candidate.get("budget_config") or {}).get("max_model_calls") or 2)
                checks = {
                    "accuracy_not_below_baseline": candidate.get("accuracy", 0) >= baseline.get("accuracy", 0),
                    "invalid_not_above_baseline": candidate.get("invalid", 0) <= baseline.get("invalid", 0),
                    "incorrect_not_above_baseline": candidate.get("incorrect", 0) <= baseline.get("incorrect", 0),
                    "main_length_not_above_baseline": candidate.get("main_length_rate", 1.0) <= baseline.get("main_length_rate", 1.0),
                    "nonempty_100pct": candidate.get("final_response_nonempty_rate") == 1.0,
                    "average_calls_le_%s" % (budget_cap - 0.5): candidate.get("average_model_calls", 999) <= budget_cap - 0.5,
                    "max_calls_le_%s" % budget_cap: candidate.get("max_model_calls", 999) <= budget_cap,
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
            paired = [
                (baseline_rounds[pairing[round_no]], rounds[round_no])
                for round_no in sorted(pairing)
                if pairing[round_no] in baseline_rounds and round_no in rounds
            ]
            if variant in {"answer_conflict_retry", "temperature04", "temperature08", "adaptive_vote", "adaptive_vote_k5"} and len(paired) == 2:
                mean_correct_gain = sum(
                    candidate.get("correct", 0) - baseline.get("correct", 0)
                    for baseline, candidate in paired
                ) / len(paired)
                if mean_correct_gain < 2:
                    failures.append(f"{dataset}:{variant}:mean_correct_gain_lt_2")
            if variant == "failure_backoff" and len(paired) == 2:
                mean_invalid_reduction = sum(
                    baseline.get("invalid", 0) - candidate.get("invalid", 0)
                    for baseline, candidate in paired
                ) / len(paired)
                if mean_invalid_reduction < 2:
                    failures.append(f"{dataset}:{variant}:mean_invalid_reduction_lt_2")
    return {"passed": not failures, "failures": failures, "comparisons": comparisons}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check two-round protocol A/B promotion gates.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", default="baseline86",
                        help="Reference arm name (default: baseline86; PRE0-AA-001 may use aa_left).")
    parser.add_argument("--baseline-rounds",
                        help="Comma-separated baseline rounds paired with variant rounds 1,2, e.g. 3,4.")
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    result = check_gate(
        payload if isinstance(payload, list) else payload.get("reports", []),
        baseline_pairing=_parse_baseline_rounds(args.baseline_rounds),
        baseline_variant=args.baseline,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

