"""Gate two-round protocol A/B reports before any default-path promotion.

PRE0 audit (2026-08-30) extension: beyond the per-round comparison checks, the
gate can now consume the window's run manifest and compact answers to verify
the spec §4.1/§4.4 mandatory facts — pairing-key integrity (no duplicates),
completed counts vs expected_n, per-arm model-error health gate (<=10%),
dataset/artifact hashes, and per-round + item-cluster exact McNemar statistics.
These integrity checks are fail-closed and separate from the promotion
comparisons; either side failing fails the gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_paired_ab import (  # noqa: E402
    group_rows,
    is_error_row,
    item_cluster_counts,
    paired_counts,
)

ERROR_RATE_THRESHOLD = 0.10


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_integrity(manifest: dict[str, Any], answers_path: Path,
                    baseline_variant: str, dataset_sha256: str | None) -> dict[str, Any]:
    """Spec §4.1/§4.4 mandatory-field consumption; fail-closed, zero model calls."""
    failures: list[str] = []
    stats: dict[str, Any] = {}

    artifacts = manifest.get("artifacts") or {}
    arms_field = manifest.get("arms") or []
    arm_names = list(arms_field) if isinstance(arms_field, dict) else list(arms_field)
    expected_n = manifest.get("expected_n")
    if not arm_names or expected_n is None:
        failures.append("manifest:missing_arms_or_expected_n")
        return {"passed": False, "failures": failures, "stats": stats}

    # artifact hashes recorded in the manifest must match the actual files
    for role in ("answers", "reports"):
        entries = artifacts.get(role) or []
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries:
            path = entry.get("path")
            recorded = entry.get("sha256")
            if not path or not recorded:
                failures.append(f"manifest:{role}:missing_path_or_sha")
                continue
            actual_path = REPO_ROOT / path
            if not actual_path.is_file():
                failures.append(f"manifest:{role}:file_missing:{path}")
                continue
            if sha256_file(actual_path) != recorded:
                failures.append(f"manifest:{role}:sha_mismatch:{path}")

    dataset_entry = artifacts.get("dataset") or {}
    recorded_dataset_sha = dataset_entry.get("sha256")
    if dataset_sha256 and recorded_dataset_sha and dataset_sha256 != recorded_dataset_sha:
        failures.append("manifest:dataset_sha_mismatch_vs_cli")

    rows = [json.loads(line) for line in answers_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    try:
        grouped = group_rows(rows, sha_map=None)
    except SystemExit as exc:
        failures.append(f"answers:pairing_integrity:{exc}")
        return {"passed": False, "failures": failures, "stats": stats}

    # dataset sha override: when provided, every row's recorded hash must equal it
    if dataset_sha256:
        resolved = sorted({resolve_safe(row["input_file"]) for row in rows})
        if resolved and resolved != [dataset_sha256]:
            failures.append(f"answers:dataset_sha_unexpected:{resolved[:2]}")

    counts: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (_sha, row_round, _idx, variant), row in grouped.items():
        slot = counts[(int(row_round), variant)]
        slot["total"] += 1
        slot["errors"] += int(is_error_row(row))
    for round_no in sorted({key[0] for key in counts}):
        for arm in arm_names:
            slot = counts.get((round_no, arm), {"total": 0, "errors": 0})
            if slot["total"] != expected_n:
                failures.append(f"completeness:round{round_no}:{arm}:completed={slot['total']}:expected={expected_n}")
            rate = slot["errors"] / expected_n if expected_n else 0.0
            if rate > ERROR_RATE_THRESHOLD:
                failures.append(f"health:round{round_no}:{arm}:error_rate={rate:.3f}")
    stats["completed_counts"] = {f"r{r}:{a}": counts[(r, a)]["total"] for (r, a) in sorted(counts)}
    stats["error_counts"] = {f"r{r}:{a}": counts[(r, a)]["errors"] for (r, a) in sorted(counts)}

    candidates = [arm for arm in arm_names if arm != baseline_variant]
    if len(candidates) == 1 and len(arm_names) == 2:
        baseline = baseline_variant
        for round_no in sorted({row["round"] for row in rows}):
            round_rows = [row for row in rows if row["round"] == round_no]
            try:
                per_round = paired_counts(round_rows, baseline, candidates[0],
                                          round_no=round_no, expected_n=expected_n)
                stats[f"mcnemar_round{round_no}"] = {
                    "b": per_round["b"], "c": per_round["c"], "p": per_round["mcnemar_exact_p"]}
            except SystemExit as exc:
                failures.append(f"pairing:round{round_no}:{exc}")
        try:
            cluster = item_cluster_counts(rows, baseline, candidates[0])
            stats["item_cluster"] = {"b": cluster["b"], "c": cluster["c"],
                                     "ties": cluster["ties"], "p": cluster["sign_test_exact_p"]}
        except SystemExit as exc:
            failures.append(f"pairing:cluster:{exc}")

    return {"passed": not failures, "failures": failures, "stats": stats}


def resolve_safe(input_file: str) -> str:
    """Best-effort dataset hash resolution that never hard-fails the audit trail."""
    try:
        from scripts.analyze_paired_ab import resolve_dataset_sha256

        return resolve_dataset_sha256(input_file)
    except SystemExit:
        return "unresolvable"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check two-round protocol A/B promotion gates.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", default="baseline86",
                        help="Reference arm name (default: baseline86; PRE0-AA-001 may use aa_left).")
    parser.add_argument("--baseline-rounds",
                        help="Comma-separated baseline rounds paired with variant rounds 1,2, e.g. 3,4.")
    parser.add_argument("--manifest", type=Path,
                        help="Run manifest with mandatory artifacts/arms/expected_n fields (integrity mode).")
    parser.add_argument("--answers", type=Path,
                        help="Compact answers JSONL (required with --manifest).")
    parser.add_argument("--dataset-sha256",
                        help="Expected dataset content hash; removes dev-machine path dependence.")
    args = parser.parse_args()
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    result = check_gate(
        payload if isinstance(payload, list) else payload.get("reports", []),
        baseline_pairing=_parse_baseline_rounds(args.baseline_rounds),
        baseline_variant=args.baseline,
    )
    if args.manifest:
        if not args.answers:
            raise SystemExit("--manifest requires --answers")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result["integrity"] = check_integrity(manifest, args.answers, args.baseline, args.dataset_sha256)
        result["passed"] = bool(result["passed"] and result["integrity"]["passed"])
        result["failures"] = list(result["failures"]) + [
            f"integrity:{failure}" for failure in result["integrity"]["failures"]
        ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

