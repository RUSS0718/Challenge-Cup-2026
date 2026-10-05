"""Run and summarize the ten-round ARM v2.4 risk-gated experiment.

The script reuses the bounded matrix runner for endpoint calls and keeps the
new paired-window definition here so the large historical matrix module does
not become another experiment registry.  Raw answers stay under ``artifacts``;
the comparison contains only bounded outcomes and route-gate telemetry.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.experiment_matrix import DATASET_PATHS, RoundSpec  # noqa: E402
from reasoning_agent.paired_run_audit import audit_paired_round  # noqa: E402
from scripts.run_robustness_matrix import run_matrix  # noqa: E402


METHOD_ID = "ARM-V2.4-RISK-GATED-ANSWER-RESERVATION-20261005"


def require_clean_worktree() -> None:
    """Stop before any model call when the paired experiment is unreproducible."""
    result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git_status_failed_before_experiment")
    if result.stdout.strip():
        raise RuntimeError(
            "clean_worktree_required_before_arm_v224; commit or isolate unrelated changes"
        )


def risk_gated_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten fresh paired rounds disjoint from the Q/T pressure windows."""
    groups = (
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-42-ZH", "OlymMATH-HARD-43-EN",
                "OlymMATH-HARD-44-ZH", "OlymMATH-HARD-45-EN",
                "OlymMATH-HARD-46-ZH",
            ),
        ),
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-50-ZH", "OlymMATH-HARD-51-EN",
                "OlymMATH-HARD-52-ZH", "OlymMATH-HARD-53-EN",
                "OlymMATH-HARD-54-ZH",
            ),
        ),
        ("external_aime", ("aime-5", "aime-6", "aime-7", "aime-8", "aime-9")),
        (
            "external_hle",
            (
                "hle-670df2e172288739ca35e0e1",
                "hle-6754baec618d187bb3362936",
                "hle-670c2d61886695e43e7c18b3",
                "hle-6708862963c4d58d76c98746",
                "hle-673716bd2773953bca4195d7",
            ),
        ),
        (
            "external_hle",
            (
                "hle-673e9bb58e7609d034b4ec54",
                "hle-6732a917934ffe0cf439cf30",
                "hle-673b192f331c2eeff8631ccf",
                "hle-672067805681ce2b6f5a08a7",
                "hle-66f708eec8903a7f2c03edbe",
            ),
        ),
    )
    specs: list[RoundSpec] = []
    for index, (dataset, keys) in enumerate(groups, start=1):
        specs.extend(
            (
                RoundSpec(f"U{index * 2 - 1:02d}", "arm-v2.4-risk-gated", dataset, keys),
                RoundSpec(f"U{index * 2:02d}", "cfr-v2.4-risk-pressure", dataset, keys),
            )
        )
    return tuple(specs)


def _read_answers(output_root: Path, round_id: str) -> list[dict[str, Any]]:
    """Read one ignored answers file for bounded post-run aggregation."""
    path = output_root / round_id / "answers.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _outcome_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count outcome labels without retaining model responses."""
    return dict(Counter(str(row.get("outcome", "invalid")) for row in rows))


def _activation_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count route-gate activation and bypass telemetry from compact traces."""
    counts = Counter()
    for row in rows:
        for entry in row.get("trace", []) if isinstance(row.get("trace"), list) else []:
            if entry.get("stage") != "risk_gated_answer_commit":
                continue
            status = str(entry.get("status", "unknown"))
            counts[status] += 1
    return dict(counts)


def _gate_decisions(
    candidate_counts: dict[str, int],
    baseline_counts: dict[str, int],
    *,
    candidate_errors: int,
    baseline_errors: int,
    candidate_calls: int,
    baseline_calls: int,
    paired_records: int,
    activation_total: int,
    candidate_truncations: int,
    baseline_truncations: int,
    transitions: Counter[str],
    provenance_errors: list[str] | None = None,
    candidate_p95_calls: int = 0,
) -> dict[str, str]:
    """Apply the preregistered gates using candidate-to-baseline transitions."""
    regression_count = sum(
        transitions.get(f"{outcome}__to__correct", 0)
        for outcome in ("incorrect", "invalid", "error")
    )
    return {
        "void_gate": "PASS" if candidate_errors == baseline_errors == 0 and not provenance_errors else "FAIL",
        "activation_gate": "PASS" if activation_total >= 5 else "FAIL",
        "safety_gate": "PASS" if regression_count == 0 and candidate_errors <= baseline_errors else "FAIL",
        "exploration_gain_gate": (
            "PASS"
            if candidate_counts.get("correct", 0) >= baseline_counts.get("correct", 0)
            and (
                candidate_counts.get("invalid", 0) <= baseline_counts.get("invalid", 0) - 2
                or candidate_truncations <= baseline_truncations - 2
            )
            else "FAIL"
        ),
        "cost_gate": "PASS" if candidate_calls <= baseline_calls + paired_records * 0.5 and candidate_p95_calls <= 2 else "FAIL",
    }


def build_comparison(output_root: Path, specs: tuple[RoundSpec, ...]) -> dict[str, Any]:
    """Build a bounded candidate/baseline comparison from completed rounds."""
    pairs: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    provenance_errors: list[str] = []
    for candidate_spec, baseline_spec in zip(specs[::2], specs[1::2]):
        candidate = _read_answers(output_root, candidate_spec.round_id)
        baseline = _read_answers(output_root, baseline_spec.round_id)
        manifests = []
        for spec in (candidate_spec, baseline_spec):
            manifest_path = output_root / spec.round_id / "run_manifest.json"
            manifests.append(
                json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else {}
            )
        dataset_path = DATASET_PATHS[candidate_spec.dataset]
        errors = audit_paired_round(
            manifests, (candidate, baseline),
            expected_ids=[str(key) for key in candidate_spec.keys],
            profiles=(candidate_spec.profile, baseline_spec.profile),
            dataset_id=dataset_path.as_posix(),
            dataset_sha256=hashlib.sha256((ROOT / dataset_path).read_bytes()).hexdigest(),
        )
        if candidate_spec.dataset != baseline_spec.dataset or candidate_spec.keys != baseline_spec.keys:
            errors.append("mismatch:round_selection")
        provenance_errors.extend(f"{candidate_spec.round_id}:{error}" for error in errors)
        candidate_rows.extend(candidate)
        baseline_rows.extend(baseline)
        baseline_by_id = {str(row["item_id"]): row for row in baseline}
        for row in candidate:
            other = baseline_by_id.get(str(row["item_id"]))
            if other is None:
                continue
            pairs.append(
                {
                    "round": candidate_spec.round_id,
                    "item_id": str(row["item_id"]),
                    "candidate_outcome": str(row.get("outcome", "invalid")),
                    "baseline_outcome": str(other.get("outcome", "invalid")),
                    "candidate_calls": int(row.get("model_calls", 0) or 0),
                    "baseline_calls": int(other.get("model_calls", 0) or 0),
                }
            )
        datasets.append(
            {
                "candidate_round": candidate_spec.round_id,
                "baseline_round": baseline_spec.round_id,
                "dataset": candidate_spec.dataset,
                "records": len(candidate),
                "selected_items_equal": [str(row["item_id"]) for row in candidate]
                == [str(row["item_id"]) for row in baseline],
            }
        )

    transitions = Counter(
        f"{pair['candidate_outcome']}__to__{pair['baseline_outcome']}" for pair in pairs
    )
    candidate_counts = _outcome_counts(candidate_rows)
    baseline_counts = _outcome_counts(baseline_rows)
    candidate_activation = _activation_counts(candidate_rows)
    baseline_activation = _activation_counts(baseline_rows)
    candidate_errors = sum(bool(row.get("model_error")) for row in candidate_rows)
    baseline_errors = sum(bool(row.get("model_error")) for row in baseline_rows)
    candidate_calls = sum(int(row.get("model_calls", 0) or 0) for row in candidate_rows)
    baseline_calls = sum(int(row.get("model_calls", 0) or 0) for row in baseline_rows)
    candidate_truncations = sum(
        1
        for row in candidate_rows
        for reason in row.get("finish_reasons", [])
        if str(reason) in {"length", "max_tokens", "truncated"}
    )
    baseline_truncations = sum(
        1
        for row in baseline_rows
        for reason in row.get("finish_reasons", [])
        if str(reason) in {"length", "max_tokens", "truncated"}
    )
    activation_total = candidate_activation.get("activated", 0)
    candidate_call_counts = sorted(int(row.get("model_calls", 0) or 0) for row in candidate_rows)
    candidate_p95_calls = (
        candidate_call_counts[math.ceil(len(candidate_call_counts) * 0.95) - 1]
        if candidate_call_counts else 0
    )
    if len(specs) != 10 or len(pairs) != 25:
        provenance_errors.append("mismatch:ten_rounds_twenty_five_pairs")
    gates = _gate_decisions(
        candidate_counts,
        baseline_counts,
        candidate_errors=candidate_errors,
        baseline_errors=baseline_errors,
        candidate_calls=candidate_calls,
        baseline_calls=baseline_calls,
        paired_records=len(pairs),
        activation_total=activation_total,
        candidate_truncations=candidate_truncations,
        baseline_truncations=baseline_truncations,
        transitions=transitions,
        provenance_errors=provenance_errors,
        candidate_p95_calls=candidate_p95_calls,
    )
    status = "EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION"
    if all(value == "PASS" for value in gates.values()):
        status = "EXPLORATORY_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION"
    if gates["void_gate"] != "PASS":
        status = "VOID / NO_PROMOTION / NO_CAPABILITY_CONCLUSION"
    return {
        "method_id": METHOD_ID,
        "status": status,
        "evaluation_scope": "local_replay",
        "official_evaluation": False,
        "round_ids": [spec.round_id for spec in specs],
        "paired_records": len(pairs),
        "datasets": datasets,
        "candidate": {
            **candidate_counts,
            "model_errors": candidate_errors,
            "total_model_calls": candidate_calls,
            "average_model_calls": candidate_calls / len(candidate_rows) if candidate_rows else 0.0,
            "risk_gate_activation": candidate_activation,
            "truncation_count": candidate_truncations,
            "p95_model_calls": candidate_p95_calls,
        },
        "baseline": {
            **baseline_counts,
            "model_errors": baseline_errors,
            "total_model_calls": baseline_calls,
            "average_model_calls": baseline_calls / len(baseline_rows) if baseline_rows else 0.0,
            "risk_gate_activation": baseline_activation,
            "truncation_count": baseline_truncations,
        },
        "paired_transitions": dict(transitions),
        "gates": gates,
        "provenance_errors": provenance_errors,
        "pairs": pairs,
        "evidence_boundary": "Local endpoint replay only; no official selector or submission config is changed.",
    }


def main() -> int:
    """Run U01-U10 and write the bounded comparison artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "arm-v224-risk-gated-20261005"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    require_clean_worktree()
    specs = risk_gated_round_specs()
    output_root = Path(args.output_dir)
    run_matrix(
        output_root,
        rounds=list(specs),
        workers=args.workers,
        timeout=args.timeout,
        matrix_id=METHOD_ID,
    )
    comparison = build_comparison(output_root, specs)
    (output_root / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{METHOD_ID}: status={comparison['status']} rounds=10 "
        f"paired={comparison['paired_records']} "
        f"candidate={comparison['candidate'].get('correct', 0)}/"
        f"{comparison['candidate'].get('incorrect', 0)}/"
        f"{comparison['candidate'].get('invalid', 0)} "
        f"baseline={comparison['baseline'].get('correct', 0)}/"
        f"{comparison['baseline'].get('incorrect', 0)}/"
        f"{comparison['baseline'].get('invalid', 0)} "
        f"activation={comparison['candidate']['risk_gate_activation'].get('activated', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
