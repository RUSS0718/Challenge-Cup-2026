"""P0.1 model-call budget scan tool (legacy: 23-item dev set experiment).

Goal (per TODO_LIST.md P0.1): without changing prompt, token limits, answer
handling, verification approach, or tool toggles, compare different candidate
generation counts to find the call configuration with the highest reproducible
accuracy on the frozen dev set.  Findings are reported per tier and never claim
global or hidden-evaluation optimality.

Tier mapping (non-L0 candidate generations = tier // 2, per-question hard cap
= tier, verifier_voting_times = 1 for every tier):

    2 -> 1 gen,  4 -> 2 gen,  6 -> 3 gen,  8 -> 4 gen,
    10 -> 5 gen, 12 -> 6 gen, 14 -> 7 gen, 16 -> 8 gen,
    18 -> 9 gen, 20 -> 10 gen

Entry into the default path additionally requires two independent re-runs of the
best tier to both beat the 6/23 baseline, 23/23 non-empty responses, 0 timeouts,
completion within the 600s total budget, and no connectivity pollution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as a plain script from the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from user_agent import AgentConfig, ReasoningAgent  # noqa: E402
from llm_client import InternChatClient  # noqa: E402
from scripts.evaluate_dev import (  # noqa: E402
    load_items,
    evaluate,
    summarize_budget_config,
    within_call_cap,
)

MAIN_TIERS = [2, 4, 6, 8, 10, 12]
CONDITIONAL_TIERS = [14, 16, 18, 20]
BASELINE_CORRECT = 6  # 6/23 default baseline
FROZEN_DATASET_SIZE = 23
TOTAL_BUDGET_SECONDS = 600.0


# ---------------------------------------------------------------------------
# Gate / pollution helpers — shared by the main scan logic and external tests.
# ---------------------------------------------------------------------------

def count_connectivity_errors(report: dict[str, Any]) -> int:
    """Return the total number of ``model_call_failed:connectivity`` entries
    across all per-item ``failure_reasons`` in *report*."""
    total = 0
    for record in report.get("records", []):
        for reason in record.get("failure_reasons", []):
            if isinstance(reason, str) and "connectivity" in reason.lower():
                total += 1
    return total


def is_polluted_by_connectivity(report: dict[str, Any]) -> bool:
    """Return True when a report contains any connectivity failure."""
    return count_connectivity_errors(report) > 0


def gate_check(
    report: dict[str, Any],
    baseline_correct: int = BASELINE_CORRECT,
) -> dict[str, Any]:
    """Unified gate check for a single evaluation report.

    Returns a dict with:
      ``passed``          – bool, True only when every required gate is satisfied
      ``checks``          – dict of individual gate results
      ``failure_summary`` – list of human-readable failure reasons (empty on pass)
    """
    dataset_size = report.get("dataset_size", 0)
    accuracy = report.get("accuracy", 0.0)
    correct_count = round(accuracy * dataset_size) if dataset_size else 0

    checks: dict[str, bool] = {}
    failures: list[str] = []

    checks["frozen_dataset_complete"] = dataset_size == FROZEN_DATASET_SIZE
    if not checks["frozen_dataset_complete"]:
        failures.append(
            f"dataset size {dataset_size} does not match frozen set {FROZEN_DATASET_SIZE}"
        )

    # Gate 1 — accuracy above baseline.
    checks["accuracy_above_baseline"] = correct_count > baseline_correct
    if not checks["accuracy_above_baseline"]:
        failures.append(
            f"accuracy {correct_count}/{dataset_size} not above baseline {baseline_correct}/{dataset_size}"
        )

    # Gate 2 — all items have a non-empty final_response.
    empty_count = report.get("empty_final_response_count")
    checks["all_non_empty_response"] = empty_count == 0
    if not checks["all_non_empty_response"]:
        failures.append(
            "missing empty_final_response_count metric"
            if empty_count is None
            else f"{empty_count} empty final_response item(s)"
        )

    # Gate 3 — no request timeouts.
    timeout_count = report.get("timeout_count", 0)
    checks["zero_timeouts"] = timeout_count == 0
    if not checks["zero_timeouts"]:
        failures.append(f"{timeout_count} timeout(s)")

    # Budget — within 600 s total.
    elapsed = report.get("total_elapsed_seconds", float("inf"))
    checks["within_600s_budget"] = elapsed <= TOTAL_BUDGET_SECONDS
    if not checks["within_600s_budget"]:
        failures.append(f"elapsed {elapsed:.0f}s exceeds {TOTAL_BUDGET_SECONDS}s budget")

    # Call cap — actual calls never exceeded declared per-question hard cap.
    cap_ok = report.get("within_call_cap", True)
    checks["within_call_cap"] = bool(cap_ok)
    if not checks["within_call_cap"]:
        failures.append("actual model calls exceeded tier hard cap")

    # Connectivity pollution.
    polluted = is_polluted_by_connectivity(report)
    checks["no_connectivity_pollution"] = not polluted
    if polluted:
        c_errs = count_connectivity_errors(report)
        failures.append(f"{c_errs} connectivity error(s) — tier is polluted")

    return {
        "passed": len(failures) == 0,
        "checks": checks,
        "failure_summary": failures,
    }


def _tier_sort_key(report: dict[str, Any]) -> tuple[float, float, float]:
    """Sort key: higher accuracy → lower calls → lower latency."""
    accuracy = -report.get("accuracy", 0.0)
    calls = report.get("average_model_calls", float("inf"))
    latency = report.get("average_latency_seconds", float("inf"))
    return (accuracy, calls, latency)


def rank_tiers(reports: dict[int, dict[str, Any]]) -> list[int]:
    """Rank clean tiers by accuracy desc, calls asc, then latency asc."""
    eligible: dict[int, dict[str, Any]] = {}
    for tier, report in reports.items():
        if is_polluted_by_connectivity(report):
            continue
        eligible[tier] = report
    return sorted(eligible.keys(), key=lambda t: _tier_sort_key(eligible[t]))


def adopt_best_tier(
    reruns: dict[int, list[dict[str, Any]]],
    baseline_correct: int = BASELINE_CORRECT,
) -> dict[str, Any]:
    """Decide whether any tier's two reruns both pass the full gate check.

    Returns a decision dict compatible with the summary format:
      ``qualified_tiers``, ``adopted_tier``, ``adopted_config``,
      and ``gate_results`` with per-tier/per-run gate outcomes.
    """
    qualified: list[int] = []
    gate_results: dict[int, list[dict[str, Any]]] = {}

    for tier, runs in reruns.items():
        tier_gates: list[dict[str, Any]] = []
        all_passed = len(runs) == 2
        for run in runs:
            result = gate_check(run, baseline_correct=baseline_correct)
            tier_gates.append(result)
            if not result["passed"]:
                all_passed = False
        gate_results[tier] = tier_gates
        if all_passed:
            qualified.append(tier)

    decision: dict[str, Any] = {
        "baseline_correct": baseline_correct,
        "qualified_tiers": sorted(qualified),
        "adopted_tier": None,
        "gate_results": gate_results,
    }

    if qualified:
        best = max(
            qualified,
            key=lambda t: (
                sum(r["accuracy"] for r in reruns[t]) / len(reruns[t]),
                -sum(r["average_model_calls"] for r in reruns[t]) / len(reruns[t]),
                -sum(r["average_latency_seconds"] for r in reruns[t]) / len(reruns[t]),
            ),
        )
        decision["adopted_tier"] = best
        decision["adopted_config"] = {
            "policy_sample_times": best // 2,
            "max_model_calls": best,
            "verifier_voting_times": 1,
        }

    return decision


# ---------------------------------------------------------------------------
# Scan infrastructure
# ---------------------------------------------------------------------------

def build_config(tier: int) -> AgentConfig:
    """All experiment switches stay off; only call budget changes between tiers."""
    return AgentConfig(
        policy_sample_times=tier // 2,
        max_model_calls=tier,
        verifier_voting_times=1,
        enable_sympy_evidence=False,
        enable_dynamic_budget=False,
        enable_l0_extended_tokens=True,
        enable_l2_routing=False,
        enable_local_repair=False,
        enable_uncertain_repair=False,
    )


def run_tier(
    tier: int,
    items: list[dict[str, Any]],
    timeout_seconds: int,
    retry_count: int,
    total_timeout: float,
    run_label: str,
) -> dict[str, Any]:
    """Run one tier sequentially using the shared ``evaluate()`` path.

    Sequential evaluation stops launching new questions after ``total_timeout``;
    the adoption gate separately rejects any completed run whose measured total
    elapsed time exceeds 600 seconds.
    """
    config = build_config(tier)
    client = InternChatClient(timeout=timeout_seconds, retry=retry_count)
    agent = ReasoningAgent(client=client, config=config)
    report = evaluate(agent, items, total_timeout)
    report["tier"] = tier
    report["policy_sample_times"] = tier // 2
    report["hard_cap"] = tier
    report["verifier_voting_times"] = 1
    report["run_label"] = run_label
    report["within_call_cap"] = within_call_cap(report)
    report["connectivity_error_count"] = count_connectivity_errors(report)
    return report


def save_report(report: dict[str, Any], output_dir: Path, timestamp: str) -> Path:
    tier = report["tier"]
    label = report.get("run_label", "main")
    path = output_dir / f"budget_scan_tier_{tier}_{label}_{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def fmt(report: dict[str, Any]) -> str:
    ce = report.get("connectivity_error_count", 0)
    ce_flag = f" conn_err={ce}" if ce else ""
    return (
        f"tier={report['tier']:>2} gen={report['policy_sample_times']} "
        f"acc={report['accuracy']*100:5.1f}% ({round(report['accuracy']*report['dataset_size'])}/{report['dataset_size']}) "
        f"calls={report['average_model_calls']:.2f} lat={report['average_latency_seconds']:.1f}s "
        f"to={report['timeout_count']} cap_ok={report['within_call_cap']} "
        f"elapsed={report['total_elapsed_seconds']:.0f}s{ce_flag}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0.1 model-call budget scan.")
    parser.add_argument("--input-file", default="sample_data/public_regression_112.jsonl")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--total-timeout-seconds", type=float, default=TOTAL_BUDGET_SECONDS)
    parser.add_argument("--inter-tier-sleep", type=int, default=15,
                        help="Seconds to pause between tiers so the model endpoint is not "
                             "hammered by back-to-back heavy evaluations (rate-limit guard).")
    parser.add_argument("--output-dir", default="docs/scan_output")
    parser.add_argument(
        "--main-tiers",
        default=",".join(str(t) for t in MAIN_TIERS),
        help="Comma-separated main-scan tiers (default 2,4,6,8,10,12).",
    )
    parser.add_argument(
        "--no-conditional",
        action="store_true",
        help="Skip the conditional 14/16/18/20 upward scan even if triggered.",
    )
    parser.add_argument(
        "--no-reruns",
        action="store_true",
        help="Skip the top-2 re-run phase (useful for a fast first pass).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    items = load_items(Path(args.input_file))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H%M%S")
    main_tiers = [int(t) for t in args.main_tiers.split(",") if t.strip()]

    results: dict[int, dict[str, Any]] = {}
    saved: dict[int, Path] = {}

    print(f"P0.1 budget scan on {len(items)} frozen dev items | "
          f"total_timeout={args.total_timeout_seconds}s | retry={args.retry_count} | "
          f"inter_tier_sleep={args.inter_tier_sleep}s")

    # --- Main scan: run every requested tier once, sequentially. ---
    for scan_index, tier in enumerate(main_tiers):
        if scan_index > 0 and args.inter_tier_sleep > 0:
            print(f"[pause]   sleeping {args.inter_tier_sleep}s before tier {tier} to avoid rate limits.")
            time.sleep(args.inter_tier_sleep)
        report = run_tier(tier, items, args.timeout_seconds, args.retry_count,
                          args.total_timeout_seconds, "main")
        results[tier] = report
        saved[tier] = save_report(report, output_dir, timestamp)
        print(f"[main]   {fmt(report)}  -> {saved[tier].name}")

    # --- Conditional upward scan (14/16/18/20) per the gating rules. ---
    continue_up = False
    if not args.no_conditional and 10 in results and 12 in results:
        r10 = results[10]
        r12 = results[12]
        # Exclude polluted tiers from conditional-scan gating.
        polluted_10 = is_polluted_by_connectivity(r10)
        polluted_12 = is_polluted_by_connectivity(r12)
        if polluted_10 or polluted_12:
            print(f"[gate]    tier10 polluted={polluted_10} tier12 polluted={polluted_12} "
                  f"— conditional upward scan blocked.")
        else:
            improved = (
                r10["accuracy"] > results[8]["accuracy"]
                or r12["accuracy"] > r10["accuracy"]
            )
            no_timeout = r10["timeout_count"] == 0 and r12["timeout_count"] == 0
            within_budget = (
                r10["total_elapsed_seconds"] <= TOTAL_BUDGET_SECONDS
                and r12["total_elapsed_seconds"] <= TOTAL_BUDGET_SECONDS
            )
            continue_up = improved and no_timeout and within_budget
            print(f"[gate]    10/12 trigger -> improved={improved} no_timeout={no_timeout} "
                  f"within_600s={within_budget} => continue_up={continue_up}")

    if continue_up:
        prev_tier = 12
        for tier in CONDITIONAL_TIERS:
            prev = results[prev_tier]
            prev_lower = results.get(prev_tier - 2, {})
            if is_polluted_by_connectivity(prev):
                print(f"[gate]    stop upward scan before tier {tier}: "
                      f"tier {prev_tier} is polluted by connectivity errors.")
                break
            step_ok = (
                prev["accuracy"] > prev_lower.get("accuracy", -1)
                and prev["timeout_count"] == 0
                and prev["total_elapsed_seconds"] <= TOTAL_BUDGET_SECONDS
            )
            if not step_ok:
                print(f"[gate]    stop upward scan before tier {tier}: "
                      f"tier {prev_tier} no longer improves / timed out / over budget.")
                break
            if args.inter_tier_sleep > 0:
                print(f"[pause]   sleeping {args.inter_tier_sleep}s before tier {tier}.")
                time.sleep(args.inter_tier_sleep)
            report = run_tier(tier, items, args.timeout_seconds, args.retry_count,
                              args.total_timeout_seconds, "main")
            results[tier] = report
            saved[tier] = save_report(report, output_dir, timestamp)
            print(f"[up]      {fmt(report)}  -> {saved[tier].name}")
            prev_tier = tier
    elif not args.no_conditional:
        print("[gate]    no upward scan: 10/12 did not meet trigger conditions "
              "(no improvement, timeout, over budget, or connectivity pollution).")

    # --- Re-run phase: top-2 unpolluted tiers, each twice, independently. ---
    ranked = rank_tiers(results)
    top2 = ranked[:2]
    reruns: dict[int, list[dict[str, Any]]] = {}
    if not args.no_reruns:
        if len(top2) < 2:
            print(f"[rerun]   only {len(top2)} unpolluted tier(s) available; "
                  f"need at least 2 for re-run phase. Skipping re-runs.")
        else:
            print(f"[rerun]   top-2 unpolluted tiers by accuracy: {top2}")
            for tier in top2:
                reruns[tier] = []
                for rep in range(2):
                    if (tier != top2[0] or rep > 0) and args.inter_tier_sleep > 0:
                        print(f"[pause]   sleeping {args.inter_tier_sleep}s before rerun "
                              f"of tier {tier} rep {rep+1}.")
                        time.sleep(args.inter_tier_sleep)
                    report = run_tier(tier, items, args.timeout_seconds, args.retry_count,
                                      args.total_timeout_seconds, f"rerun{rep+1}")
                    reruns[tier].append(report)
                    save_report(report, output_dir, timestamp)
                    print(f"[rerun]   tier={tier} rep={rep+1} {fmt(report)}")
    else:
        print("[rerun]   skipped (--no-reruns).")

    # --- Decision (only when reruns were actually performed). ---
    if not args.no_reruns and reruns:
        decision = adopt_best_tier(reruns, baseline_correct=BASELINE_CORRECT)
        decision["baseline_total"] = len(items)
        decision["main_scan_tiers"] = {t: _summary(results[t]) for t in sorted(results)}
        decision["reruns"] = {t: [_summary(r) for r in reruns[t]] for t in reruns}

        if decision["adopted_tier"] is not None:
            best = decision["adopted_tier"]
            print(f"[decide]  ADOPT tier {best} (gen={best // 2}, cap={best}).")
        else:
            print(f"[decide]  No tier passes all gates in both re-runs. "
                  f"KEEP {BASELINE_CORRECT}-call default.")

        summary_path = output_dir / f"budget_scan_summary_{timestamp}.json"
        summary_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        print(f"[done]    summary -> {summary_path.name}")
    else:
        # --no-reruns: save a main-scan-only summary without a KEEP/ADOPT decision.
        scan_only: dict[str, Any] = {
            "baseline_correct": BASELINE_CORRECT,
            "baseline_total": len(items),
            "main_scan_tiers": {t: _summary(results[t]) for t in sorted(results)},
            "reruns": {},
            "qualified_tiers": [],
            "adopted_tier": None,
            "note": "re-run phase skipped (--no-reruns); no adoption decision was made "
                     "because reproducibility was not evaluated.",
        }
        summary_path = output_dir / f"budget_scan_main_only_{timestamp}.json"
        summary_path.write_text(json.dumps(scan_only, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        print(f"[done]    main-scan-only summary -> {summary_path.name}")
        print("[decide]  skipped — re-runs not performed (--no-reruns). "
              "No adoption decision possible without reproducibility evidence.")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "tier": report["tier"],
        "policy_sample_times": report["policy_sample_times"],
        "accuracy": report["accuracy"],
        "correct": round(report["accuracy"] * report["dataset_size"]),
        "average_model_calls": report["average_model_calls"],
        "average_latency_seconds": report["average_latency_seconds"],
        "timeout_count": report["timeout_count"],
        "empty_final_response_count": report["empty_final_response_count"],
        "within_call_cap": report["within_call_cap"],
        "total_elapsed_seconds": report["total_elapsed_seconds"],
        "answer_not_extractable_count": report["answer_not_extractable_count"],
        "connectivity_error_count": report.get("connectivity_error_count", 0),
        "failed_item_ids": report["failed_item_ids"],
    }


if __name__ == "__main__":
    main()
