"""Exact McNemar analysis for interleaved paired A/B answer files."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial McNemar p-value (pure stdlib)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def paired_counts(rows: list[dict], baseline_name: str, treatment_name: str,
                  round_no: int | None = None) -> dict:
    """Pair verdicts per item; unknown/incorrect count as not-correct."""
    by_variant: dict[str, dict] = {baseline_name: {}, treatment_name: {}}
    for row in rows:
        if round_no is not None and row.get("round") != round_no:
            continue
        variant = row.get("variant")
        if variant in by_variant:
            by_variant[variant][row["idx"]] = row.get("verdict", "unknown")

    base = by_variant[baseline_name]
    treat = by_variant[treatment_name]
    if set(base) != set(treat):
        raise SystemExit(
            f"unpaired items: only_baseline={sorted(set(base) - set(treat))} "
            f"only_treatment={sorted(set(treat) - set(base))}"
        )

    b = c = baseline_correct = treatment_correct = 0
    for idx in base:
        base_hit = base[idx] == "correct"
        treat_hit = treat[idx] == "correct"
        baseline_correct += base_hit
        treatment_correct += treat_hit
        if treat_hit and not base_hit:
            b += 1
        elif base_hit and not treat_hit:
            c += 1

    p_value = mcnemar_exact(b, c)
    return {
        "n_paired": len(base),
        "b": b,
        "c": c,
        "baseline_correct": baseline_correct,
        "treatment_correct": treatment_correct,
        "mean_gain": (treatment_correct - baseline_correct) / len(base) if base else 0.0,
        "mcnemar_exact_p": p_value,
        "significant_at_0_05": p_value < 0.05,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exact McNemar test on paired protocol A/B answers.")
    parser.add_argument("answers", type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--round", type=int, help="Restrict to one recorded round.")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.answers.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(paired_counts(rows, args.baseline, args.treatment, round_no=args.round),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
