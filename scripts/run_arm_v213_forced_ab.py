"""Run the bounded, independent A/B diagnostic for ARM-Harness v2.1.3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.artifacts import ArtifactManager  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402
from scripts.run_arm_v21_eval112_timing import load_dataset, run_timing  # noqa: E402


PROFILE = "arm-v2.1.3-forced-ab"


def _candidate_verdict(candidate: Any, gold: str) -> str:
    """Score one bounded candidate projection without exposing it to runtime."""
    if not isinstance(candidate, Mapping):
        return "invalid"
    if not bool(candidate.get("answer_complete")):
        return "invalid"
    if candidate.get("structural_validity") != "valid":
        return "invalid"
    value = candidate.get("value")
    return judge_correct(value, gold) if isinstance(value, str) and value else "invalid"


def summarize_forced_ab(
    rows: list[Mapping[str, Any]],
    gold_by_id: Mapping[Any, str],
) -> dict[str, Any]:
    """Compute A/B/oracle counts from response-free candidate projections."""
    a_verdicts: list[str] = []
    b_verdicts: list[str] = []
    transitions: dict[str, int] = {}
    both_correct_same = 0
    both_correct_conflict = 0
    for row in rows:
        summary = row.get("arm_v2_summary")
        summary = summary if isinstance(summary, Mapping) else {}
        gold = gold_by_id.get(row.get("idx"), "")
        a = _candidate_verdict(summary.get("candidate_a"), gold)
        b = _candidate_verdict(summary.get("candidate_b"), gold)
        a_verdicts.append(a)
        b_verdicts.append(b)
        label = f"{a} -> {b}"
        transitions[label] = transitions.get(label, 0) + 1
        if a == b == "correct":
            if summary.get("a_b_relation") == "EQUIVALENT":
                both_correct_same += 1
            else:
                both_correct_conflict += 1
    total = len(rows)
    a_correct = sum(value == "correct" for value in a_verdicts)
    b_correct = sum(value == "correct" for value in b_verdicts)
    oracle_correct = sum(
        left == "correct" or right == "correct"
        for left, right in zip(a_verdicts, b_verdicts)
    )
    return {
        "records": total,
        "A_correct": a_correct,
        "B_correct": b_correct,
        "oracle_correct": oracle_correct,
        "A_accuracy": round(a_correct / total, 6) if total else 0.0,
        "B_accuracy": round(b_correct / total, 6) if total else 0.0,
        "oracle_accuracy": round(oracle_correct / total, 6) if total else 0.0,
        "A_wrong_B_correct": sum(
            left != "correct" and right == "correct"
            for left, right in zip(a_verdicts, b_verdicts)
        ),
        "A_correct_B_wrong": sum(
            left == "correct" and right != "correct"
            for left, right in zip(a_verdicts, b_verdicts)
        ),
        "both_wrong": sum(left == right == "incorrect" for left, right in zip(a_verdicts, b_verdicts)),
        "both_correct_same": both_correct_same,
        "both_correct_conflict": both_correct_conflict,
        "transition_counts": transitions,
    }


def run_forced_ab(
    *,
    run_id: str,
    dataset_path: Path | str = ROOT / "sample_data" / "arm_fixed_items_30.json",
    output_root: Path | str = ROOT / "artifacts",
    expected_records: int = 30,
    selection_seed: int | None = 20260905,
    client_factory: Any | None = None,
    agent_factory: Any | None = None,
) -> dict[str, Any]:
    """Run forced A/B and persist only bounded aggregate metrics."""
    dataset = load_dataset(
        dataset_path,
        expected_records=expected_records,
        error_prefix="forced_ab",
        selection_seed=selection_seed,
    )
    run_kwargs: dict[str, Any] = {
        "profile": PROFILE,
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
    base_report = run_timing(**run_kwargs)
    run_dir = Path(output_root) / run_id
    rows = [
        json.loads(line)
        for line in (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gold_by_id = {row["idx"]: row["answer"] for row in dataset}
    metrics = summarize_forced_ab(rows, gold_by_id)
    metrics.update(
        {
            "run_id": run_id,
            "profile": PROFILE,
            "dataset_hash": json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))["dataset_hash"],
            "base_run_status": base_report.get("status"),
            "submission_promotion": "NONE",
        }
    )
    manager = ArtifactManager(run_dir)
    manager.save_json("forced_ab_metrics.json", metrics)
    manager.save_text(
        "forced_ab_result.md",
        "# ARM v2.1.3 forced A/B diagnostic\n\n"
        f"A accuracy: {metrics['A_accuracy']:.4f}\n"
        f"B accuracy: {metrics['B_accuracy']:.4f}\n"
        f"Oracle(A,B) accuracy: {metrics['oracle_accuracy']:.4f}\n"
        f"A wrong -> B correct: {metrics['A_wrong_B_correct']}\n"
        f"A correct -> B wrong: {metrics['A_correct_B_wrong']}\n"
        "submission promotion: NONE\n",
    )
    return metrics


def main() -> int:
    """Parse the fixed-diagnostic CLI and execute one serial A/B run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset-path", type=Path, default=ROOT / "sample_data" / "arm_fixed_items_30.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--expected-records", type=int, default=30)
    parser.add_argument("--selection-seed", type=int, default=20260905)
    args = parser.parse_args()
    print(json.dumps(run_forced_ab(**vars(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
