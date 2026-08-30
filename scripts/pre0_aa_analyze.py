"""PRE0-AA-001 analysis: six preregistered gates over the A/A window artifacts.

Reads the runner's round reports + compact answers, applies the fixed pairing
contract (scripts/analyze_paired_ab.py), and emits machine-readable gate
results.  Zero model calls.

Gates (preregistration §5, in order):
 1 completeness   — both rounds 24/24 per arm, no breaker void marker
 2 health         — per arm per round error rate <= 10%
 3 noise          — per round |correct diff| <= 2 and |invalid+error diff| <= 2
 4 significance   — per-round McNemar p >= 0.05 and item-cluster sign test p >= 0.05
 5 cost           — mean calls / mean tokens / P95 latency ratios in [0.90, 1.10]
 6 order bias     — no arm strictly dominates both rounds; first-arm x winner
                    Fisher exact p >= 0.05
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_paired_ab import (  # noqa: E402
    item_cluster_counts,
    paired_counts,
    resolve_dataset_sha256,
    window_void_state,
)

WORKTREE = REPO_ROOT / ".worktrees" / "main-integration-20260829"
ANSWERS = WORKTREE / "tmp" / "pre0_aa_answers.jsonl"
REPORTS = [WORKTREE / "tmp" / "pre0_aa_reports_r1.json", WORKTREE / "tmp" / "pre0_aa_reports_r2.json"]
EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-AA-001"
DATASET = EXPERIMENT_DIR / "aa24_dataset.jsonl"
EXPECTED_N = 24
ARMS = ("aa_left", "aa_right")
ROUND_ARM_ORDER = {1: ["aa_left", "aa_right"], 2: ["aa_right", "aa_left"]}


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (stdlib hypergeometric)."""
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d
    n = row1 + row2
    if min(row1, row2) == 0 or min(col1, col2) == 0:
        return 1.0

    def log_comb(k: int, r: int) -> float:
        return math.lgamma(k + 1) - math.lgamma(r + 1) - math.lgamma(k - r + 1)

    def prob(x: int) -> float:
        return math.exp(log_comb(col1, x) + log_comb(col2, row1 - x) - log_comb(n, row1))

    observed = prob(a)
    total = 0.0
    lo, hi = max(0, row1 - col2), min(row1, col1)
    for x in range(lo, hi + 1):
        p = prob(x)
        if p <= observed * (1 + 1e-9):
            total += p
    return min(1.0, total)


def p95(values: list) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(min(int(len(ordered) * 0.95 + 0.999) - 1, len(ordered) - 1), 0)]


def load_round_reports(path: Path) -> dict:
    reports = json.loads(path.read_text(encoding="utf-8"))
    return {report["variant"]: report for report in reports}


def main() -> None:
    rows = [json.loads(line) for line in ANSWERS.read_text(encoding="utf-8").splitlines() if line.strip()]
    # key the sha map by the exact input_file string the runner recorded
    recorded_inputs = sorted({row["input_file"] for row in rows})
    sha_map = {input_file: resolve_dataset_sha256(input_file) for input_file in recorded_inputs}
    round_reports = {number: load_round_reports(path) for number, path in enumerate(REPORTS, start=1)}

    gates: dict = {}
    details: dict = {}

    # ── 1. completeness + 2. health ──────────────────────────────────────
    completeness = {}
    health = {}
    breaker_tripped = any(
        round_reports[number][arm].get("void", False)
        for number in (1, 2) for arm in ARMS
    )
    for number in (1, 2):
        state = window_void_state([r for r in rows if r["round"] == number], list(ARMS),
                                  expected_n=EXPECTED_N, sha_map=sha_map)
        completeness[number] = state["complete"]
        health[number] = {
            "error_rates": state["error_rates"],
            "passed": all(rate <= 0.10 for rate in state["error_rates"].values()) and state["complete"],
        }
    gates["gate1_completeness"] = all(completeness.values()) and not breaker_tripped
    gates["gate2_health"] = all(entry["passed"] for entry in health.values())
    details["health"] = health
    details["breaker_tripped"] = breaker_tripped

    # ── 3. noise + 4. significance, per round ────────────────────────────
    per_round = {}
    for number in (1, 2):
        round_rows = [r for r in rows if r["round"] == number]
        counts = paired_counts(round_rows, ARMS[0], ARMS[1], round_no=number,
                               expected_n=EXPECTED_N, sha_map=sha_map)
        correct_diff = abs(counts["baseline_correct"] - counts["treatment_correct"])
        invalid_error = {
            arm: round_reports[number][arm].get("invalid", 0) + round_reports[number][arm].get("error", 0)
            for arm in ARMS
        }
        invalid_error_diff = abs(invalid_error[ARMS[0]] - invalid_error[ARMS[1]])
        per_round[number] = {
            "b": counts["b"], "c": counts["c"], "mcnemar_p": counts["mcnemar_exact_p"],
            "correct": {ARMS[0]: counts["baseline_correct"], ARMS[1]: counts["treatment_correct"]},
            "correct_diff": correct_diff,
            "invalid_plus_error": invalid_error,
            "invalid_plus_error_diff": invalid_error_diff,
        }
    cluster = item_cluster_counts(rows, ARMS[0], ARMS[1], sha_map=sha_map)
    gates["gate3_noise"] = all(
        entry["correct_diff"] <= 2 and entry["invalid_plus_error_diff"] <= 2
        for entry in per_round.values()
    )
    gates["gate4_significance"] = all(
        entry["mcnemar_p"] >= 0.05 for entry in per_round.values()
    ) and cluster["sign_test_exact_p"] >= 0.05
    details["per_round"] = per_round
    details["item_cluster"] = {
        key: cluster[key] for key in ("n_items", "b", "c", "ties", "sign_test_exact_p",
                                      "baseline_cluster_correct", "treatment_cluster_correct")
    }

    # ── 5. cost ratios (pooled over both rounds; per-round reported) ─────
    def arm_cost(rows_for_arm: list[dict]) -> dict:
        return {
            "mean_calls": sum(r.get("model_calls", 0) for r in rows_for_arm) / len(rows_for_arm),
            "mean_tokens": sum(r.get("total_completion_tokens", 0) for r in rows_for_arm) / len(rows_for_arm),
            "p95_latency": p95([r.get("latency_seconds", 0.0) for r in rows_for_arm]),
        }

    pooled_cost = {}
    per_round_cost = {}
    for arm in ARMS:
        arm_rows = [r for r in rows if r["variant"] == arm]
        pooled_cost[arm] = arm_cost(arm_rows)
        for number in (1, 2):
            per_round_cost.setdefault(number, {})[arm] = arm_cost(
                [r for r in rows if r["variant"] == arm and r["round"] == number])
    ratios = {
        metric: pooled_cost[ARMS[1]][metric] / pooled_cost[ARMS[0]][metric] if pooled_cost[ARMS[0]][metric] else 1.0
        for metric in ("mean_calls", "mean_tokens", "p95_latency")
    }
    gates["gate5_cost"] = all(0.90 <= value <= 1.10 for value in ratios.values())
    details["cost"] = {"pooled": pooled_cost, "per_round": per_round_cost, "ratios_right_over_left": ratios}

    # ── 6. order bias ────────────────────────────────────────────────────
    dominance = (
        per_round[1]["correct"][ARMS[0]] > per_round[1]["correct"][ARMS[1]]
        and per_round[2]["correct"][ARMS[0]] > per_round[2]["correct"][ARMS[1]]
    ) or (
        per_round[1]["correct"][ARMS[1]] > per_round[1]["correct"][ARMS[0]]
        and per_round[2]["correct"][ARMS[1]] > per_round[2]["correct"][ARMS[0]]
    )
    # first-arm x winner table over decisive item-rounds
    table = {"left_first": {"left_wins": 0, "right_wins": 0},
             "right_first": {"left_wins": 0, "right_wins": 0}}
    by_key: dict[tuple, dict] = {}
    for row in rows:
        key = (row["round"], row["idx"])
        by_key.setdefault(key, {})[row["variant"]] = row.get("verdict") == "correct"
    for (number, idx), arms in by_key.items():
        if set(arms) != set(ARMS):
            continue
        if arms[ARMS[0]] == arms[ARMS[1]]:
            continue  # tie
        first_arm = ROUND_ARM_ORDER[number][idx % 2]
        winner = ARMS[0] if arms[ARMS[0]] else ARMS[1]
        side = "left_first" if first_arm == ARMS[0] else "right_first"
        win = "left_wins" if winner == ARMS[0] else "right_wins"
        table[side][win] += 1
    fisher_p = fisher_exact_2x2(table["left_first"]["left_wins"], table["left_first"]["right_wins"],
                                table["right_first"]["left_wins"], table["right_first"]["right_wins"])
    gates["gate6_order_bias"] = (not dominance) and fisher_p >= 0.05
    details["order_bias"] = {"dominance": dominance, "first_arm_table": table, "fisher_p": fisher_p}

    # ── summary ──────────────────────────────────────────────────────────
    manifest = {
        "experiment": "PRE0-AA-001",
        "analyzed_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "dataset_sha256": sha_map[recorded_inputs[0]] if len(recorded_inputs) == 1 else sha_map,
        "recorded_input_files": recorded_inputs,
        "expected": {"rounds": 2, "items": EXPECTED_N, "arms": list(ARMS)},
        "round_arm_order": ROUND_ARM_ORDER,
        "schedule_seeds": {1: 8301, 2: 8302},
        "timeout_seconds": 180,
    }
    output = {
        "manifest": manifest,
        "gates": gates,
        "all_passed": all(gates.values()),
        "details": details,
    }
    (EXPERIMENT_DIR / "analysis.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "all_passed": output["all_passed"],
                      "cluster": details["item_cluster"], "ratios": ratios,
                      "fisher_p": fisher_p}, ensure_ascii=False, indent=2))
    sys.exit(0 if output["all_passed"] else 1)


if __name__ == "__main__":
    main()
