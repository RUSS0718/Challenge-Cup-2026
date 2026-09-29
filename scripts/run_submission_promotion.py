"""Run the official-equivalent FSDF/ARM promotion comparison.

Each round uses the same fixed dataset, endpoint configuration, serial runner,
and local judge for four explicit profiles.  The script records diagnostics and
reports a gate; it never changes ``SUBMISSION_CONFIG`` or promotes a default.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.submission_diagnostics import (  # noqa: E402
    check_record_integrity,
    compact_submission_diagnostics,
    promotion_gate,
    summarize_submission_diagnostics,
)
from scripts.run_arm_v21_eval112_timing import (  # noqa: E402
    load_dataset,
    run_timing,
)


PROMOTION_ARMS = {
    "A": "submission",
    "B": "arm-v2.1.2-off",
    "C": "arm-v2.1.2-on",
    "D": "arm-v2.1.2-adaptive",
}
DEFAULT_DATASET = ROOT / "sample_data" / "arm_fixed_items_30.json"


def _now_utc() -> str:
    """Return an artifact timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSONL records from one completed runner artifact."""
    if not path.is_file():
        raise RuntimeError(f"answers_required:{path}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one deterministic, human-readable JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _aggregate_rounds(reports: list[Mapping[str, Any]], profile: str) -> dict[str, Any]:
    """Aggregate repeated round reports while retaining round variance."""
    accuracies = [float(report.get("accuracy", 0.0) or 0.0) for report in reports]
    invalid_rates = [
        float(report.get("invalid", 0) or 0) / max(1, int(report.get("records", 0) or 0))
        for report in reports
    ]
    calls = [float(report.get("mean_calls_per_problem", 0.0) or 0.0) for report in reports]
    return {
        "profile": profile,
        "rounds": len(reports),
        "mean_accuracy": round(statistics.mean(accuracies), 6) if accuracies else 0.0,
        "accuracy_variance": round(statistics.pvariance(accuracies), 6) if len(accuracies) > 1 else 0.0,
        "mean_invalid_rate": round(statistics.mean(invalid_rates), 6) if invalid_rates else 0.0,
        "mean_calls_per_problem": round(statistics.mean(calls), 6) if calls else 0.0,
        "mean_correct": round(statistics.mean(float(report.get("correct", 0) or 0) for report in reports), 6)
        if reports else 0.0,
        "mean_invalid": round(statistics.mean(float(report.get("invalid", 0) or 0) for report in reports), 6)
        if reports else 0.0,
        "mean_errors": round(statistics.mean(float(report.get("errors", 0) or 0) for report in reports), 6)
        if reports else 0.0,
        "all_rounds_complete": all(bool(report.get("integrity_passed", True)) for report in reports),
    }


def _aggregate_gate(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the same gate to repeated-run means."""
    checks = {
        "baseline_complete": bool(baseline.get("all_rounds_complete", True)),
        "candidate_complete": bool(candidate.get("all_rounds_complete", True)),
        "mean_accuracy_not_below_baseline": candidate["mean_accuracy"] >= baseline["mean_accuracy"],
        "mean_invalid_rate_not_above_baseline": candidate["mean_invalid_rate"] <= baseline["mean_invalid_rate"],
        "mean_errors_not_above_baseline": candidate["mean_errors"] <= baseline["mean_errors"],
        "mean_calls_within_budget": candidate["mean_calls_per_problem"] <= 3.0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "NO_GO",
        "checks": checks,
        "baseline_profile": baseline.get("profile"),
        "candidate_profile": candidate.get("profile"),
    }


def run_promotion(
    *,
    run_prefix: str,
    dataset_path: Path | str = DEFAULT_DATASET,
    output_root: Path | str = ROOT / "artifacts",
    expected_records: int = 30,
    selection_seed: int | None = 20260905,
    rounds: int = 1,
    client_factory: Any | None = None,
    agent_factory: Any | None = None,
) -> dict[str, Any]:
    """Run all promotion arms and return a fail-closed comparison report."""
    if rounds < 1:
        raise ValueError("rounds_must_be_positive")
    started_at = _now_utc()
    expected_rows = load_dataset(
        dataset_path,
        expected_records=expected_records,
        error_prefix="promotion",
        selection_seed=selection_seed,
    )
    expected_ids = {row["idx"] for row in expected_rows}
    round_reports: dict[str, list[dict[str, Any]]] = {arm: [] for arm in PROMOTION_ARMS}
    for round_number in range(1, rounds + 1):
        for arm_id, profile in PROMOTION_ARMS.items():
            run_id = f"{run_prefix}-r{round_number}-{arm_id}"
            run_kwargs = {
                "profile": profile,
                "run_id": run_id,
                "dataset_path": dataset_path,
                "output_root": output_root,
                "expected_records": expected_records,
                "selection_seed": selection_seed,
            }
            if client_factory is not None:
                run_kwargs["client_factory"] = client_factory
            if agent_factory is not None:
                run_kwargs["agent_factory"] = agent_factory
            report = run_timing(**run_kwargs)
            rows = _read_jsonl(Path(output_root) / run_id / "answers.jsonl")
            diagnostics = [
                {"idx": row.get("idx"), **compact_submission_diagnostics(row, profile)}
                for row in rows
            ]
            diagnostic_report = summarize_submission_diagnostics(
                rows,
                profile=profile,
                expected_records=expected_records,
            )
            diagnostic_report.update(check_record_integrity(rows, expected_ids))
            _write_json(Path(output_root) / run_id / "diagnostic_metrics.json", diagnostic_report)
            (Path(output_root) / run_id / "diagnostics.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in diagnostics),
                encoding="utf-8",
            )
            round_reports[arm_id].append({**report, **diagnostic_report})

    baseline = round_reports["A"][0]
    gates = {
        arm_id: promotion_gate(baseline, reports[0])
        for arm_id, reports in round_reports.items()
        if arm_id != "A"
    }
    aggregates = {
        arm_id: _aggregate_rounds(reports, PROMOTION_ARMS[arm_id])
        for arm_id, reports in round_reports.items()
    }
    aggregate_gates = {
        arm_id: _aggregate_gate(aggregates["A"], aggregate)
        for arm_id, aggregate in aggregates.items()
        if arm_id != "A"
    }
    result = {
        "protocol": "submission_promotion_v1",
        "started_at": started_at,
        "ended_at": _now_utc(),
        "run_prefix": run_prefix,
        "dataset_path": str(Path(dataset_path)),
        "expected_records": expected_records,
        "selection_seed": selection_seed,
        "rounds": rounds,
        "arms": PROMOTION_ARMS,
        "round_reports": round_reports,
        "aggregates": aggregates,
        "full30_gates": gates,
        "repeated_run_gates": aggregate_gates,
        "default_promotion": "NONE",
    }
    _write_json(Path(output_root) / run_prefix / "promotion_report.json", result)
    return result


def main() -> int:
    """Parse the promotion comparison CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--expected-records", type=int, default=30)
    parser.add_argument("--selection-seed", type=int, default=20260905)
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()
    print(
        json.dumps(
            run_promotion(
                run_prefix=args.run_prefix,
                dataset_path=args.dataset_path,
                output_root=args.output_root,
                expected_records=args.expected_records,
                selection_seed=args.selection_seed,
                rounds=args.rounds,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
