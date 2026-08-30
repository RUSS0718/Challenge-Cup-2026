"""PRE0-STATIC-001 self-test: pairing, VOID and data-integrity contract.

Structural-only (zero model calls).  Builds the synthetic artifacts frozen in
docs/experiments/PRE0-STATIC-001/preregistration.md, checks every positive
expectation and every fail-closed negative, audits the real local datasets,
and writes pre0_static_result.md.  Any failure exits non-zero and stops Pre-P0.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_paired_ab import (  # noqa: E402
    BREAKER_REASON,
    ERROR_RATE_REASON,
    assert_pooling_allowed,
    classifier_label_audit,
    detect_dataset_overlap,
    group_rows,
    item_cluster_counts,
    mcnemar_exact,
    paired_counts,
    resolve_dataset_sha256,
    window_void_state,
)

EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-STATIC-001"
ARTIFACT_DIR = EXPERIMENT_DIR / "synthetic_artifacts"

CHECKS: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def expect_exit(name: str, fn, needle: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        message = str(exc)
        check(name, needle in message, f"exit message: {message[:160]}")
        return
    except Exception as exc:  # noqa: BLE001
        check(name, False, f"wrong exception type {type(exc).__name__}: {exc}")
        return
    check(name, False, "no SystemExit raised")


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def answer_row(input_file: str, round_no: int, variant: str, idx: int, verdict: str,
               result_status: str = "ok", diagnostics: list[str] | None = None) -> dict:
    return {
        "input_file": input_file,
        "round": round_no,
        "variant": variant,
        "idx": idx,
        "extracted_answer": "" if verdict != "correct" else "7",
        "verdict": verdict,
        "diagnostic_reasons": diagnostics or [],
        "result_status": result_status,
        "latency_seconds": 1.0,
        "total_completion_tokens": 100,
        "main_finish_reason": "stop",
    }


def build_positive_artifacts() -> tuple[str, list[dict]]:
    """2 datasets x 2 rounds x 2 arms x 3 items; dsB shares dsA item 0's problem."""
    ds_a = [
        {"idx": 0, "problem": "已知 a=1, b=2，求 a+b 的值。", "answer": "3"},
        {"idx": 1, "problem": "已知 a=2, b=3，求 a+b 的值。", "answer": "5"},
        {"idx": 2, "problem": "已知 a=3, b=4，求 a+b 的值。", "answer": "7"},
    ]
    ds_b = [
        {"idx": 0, "problem": "已知 a=1, b=2，求 a+b 的值。", "answer": "3"},  # overlap with dsA
        {"idx": 1, "problem": "Different problem text entirely about geometry.", "answer": "9"},
        {"idx": 2, "problem": "Another distinct problem about number theory.", "answer": "11"},
    ]
    path_a = write_jsonl(ARTIFACT_DIR / "dsA.jsonl", ds_a)
    path_b = write_jsonl(ARTIFACT_DIR / "dsB.jsonl", ds_b)

    # Frozen outcome table (preregistration §4): I=not correct, C=correct.
    outcomes = {
        (1, 0): ("ctl", "treat"),  # r1: ctl=I, treat=C
        (1, 1): ("treat", "ctl"),  # r1: ctl=C, treat=I
        (1, 2): ("ctl", "treat"),
        (2, 0): ("ctl", "treat"),
        (2, 1): ("treat", "ctl"),
        (2, 2): ("none", "none"),  # r2 item2: both I
    }
    rows: list[dict] = []
    for round_no in (1, 2):
        for item in (0, 1, 2):
            correct_by = {"ctl": False, "treat": False}
            wrong, right = outcomes[(round_no, item)]
            if right != "none":
                correct_by[right] = True
            for variant in ("ctl", "treat"):
                rows.append(answer_row(
                    str(path_a.relative_to(REPO_ROOT)).replace("\\", "/"),
                    round_no, variant, item,
                    "correct" if correct_by[variant] else "unknown",
                ))
    sha_a = resolve_dataset_sha256(str(path_a.relative_to(REPO_ROOT)).replace("\\", "/"))
    return sha_a, rows


def build_error_rate_artifacts(error_count_arm_x: int) -> tuple[str, list[dict], int]:
    persisted = ARTIFACT_DIR / f"er_dataset_{error_count_arm_x}.jsonl"
    write_jsonl(persisted, [{"idx": i, "problem": f"p{i}", "answer": "1"} for i in range(100)])
    rel = str(persisted.relative_to(REPO_ROOT)).replace("\\", "/")
    rows = []
    for variant in ("armX", "armY"):
        for idx in range(100):
            error = idx < error_count_arm_x if variant == "armX" else idx < 9
            rows.append(answer_row(
                rel, 1, variant, idx, "unknown",
                result_status="error" if error else "ok",
                diagnostics=["model_error"] if error else [],
            ))
    sha = resolve_dataset_sha256(rel)
    return sha, rows, 100


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. positive pairing + hand-checked statistics ──────────────────
    sha_a, rows = build_positive_artifacts()
    check("dataset sha resolution yields 64-hex digest", len(sha_a) == 64 and all(c in "0123456789abcdef" for c in sha_a), sha_a[:16])
    r1 = paired_counts(rows, "ctl", "treat", round_no=1, expected_n=3, sha_map=None)
    r2 = paired_counts(rows, "ctl", "treat", round_no=2, expected_n=3, sha_map=None)
    check("r1 mcnemar hand-calc", (r1["b"], r1["c"], round(r1["mcnemar_exact_p"], 6)) == (2, 1, 1.0), json.dumps({k: r1[k] for k in ("b", "c", "mcnemar_exact_p")}))
    check("r2 mcnemar hand-calc", (r2["b"], r2["c"], round(r2["mcnemar_exact_p"], 6)) == (1, 1, 1.0), json.dumps({k: r2[k] for k in ("b", "c", "mcnemar_exact_p")}))
    check("per-round n_paired=3 (cross-round not collapsed)",
          r1["n_paired"] == 3 and r2["n_paired"] == 3,
          f"r1={r1['n_paired']} r2={r2['n_paired']}")
    cluster = item_cluster_counts(rows, "ctl", "treat")
    check("cluster hand-calc",
          (cluster["b"], cluster["c"], cluster["ties"], round(cluster["sign_test_exact_p"], 6),
           cluster["baseline_cluster_correct"], cluster["treatment_cluster_correct"])
          == (2, 1, 0, 1.0, 2, 3),
          json.dumps({k: cluster[k] for k in ("b", "c", "ties", "sign_test_exact_p",
                                              "baseline_cluster_correct", "treatment_cluster_correct")}))
    check("item-round pooled descriptive = 6 observations",
          cluster["item_round_pooled_descriptive"]["n_item_rounds"] == 6)
    check("cluster deltas match hand-calc",
          sorted(cluster["deltas"].values()) == [-2, 1, 2], json.dumps(cluster["deltas"]))
    check("healthy expected_n satisfied", r1["void"] is False and r1["void_reason"] is None)

    # ── 2. error-rate health gate: 9% healthy, 11% VOID ────────────────
    sha_ok, rows_ok, n100 = build_error_rate_artifacts(9)
    state_ok = window_void_state(rows_ok, ["armX", "armY"], expected_n=n100)
    check("9% error healthy", state_ok["void"] is False and state_ok["error_rate_void"] is False,
          json.dumps(state_ok["error_rates"]))
    check("9% error rates are exactly 0.09",
          all(abs(rate - 0.09) < 1e-9 for rate in state_ok["error_rates"].values()))
    sha_void, rows_void, n100 = build_error_rate_artifacts(11)
    state_void = window_void_state(rows_void, ["armX", "armY"], expected_n=n100)
    check("11% error VOID", state_void["void"] is True and state_void["void_reason"] == ERROR_RATE_REASON,
          json.dumps(state_void["error_rates"]))
    pc_void = paired_counts(rows_void, "armX", "armY", expected_n=n100)
    check("paired_counts expected_n path flags VOID and exact rates",
          pc_void["void"] is True
          and abs(pc_void["error_rates"]["armX"] - 0.11) < 1e-9
          and abs(pc_void["error_rates"]["armY"] - 0.09) < 1e-9,
          json.dumps(pc_void["error_rates"]))

    # ── 3. breaker vs preregistered VOID stay separate fields ──────────
    state_breaker = window_void_state(rows_ok, ["armX", "armY"], expected_n=n100,
                                      breaker_report={"void": True, "consecutive_failures_max": 8})
    check("breaker field separate from error-rate field",
          state_breaker["breaker_tripped"] is True
          and state_breaker["breaker_reason"] == BREAKER_REASON
          and state_breaker["error_rate_void"] is False
          and state_breaker["void"] is True
          and state_breaker["void_reason"] == BREAKER_REASON,
          json.dumps({k: state_breaker[k] for k in ("breaker_reason", "error_rate_void_reason", "void_reason")}))
    check("breaker and health reasons are distinct strings", BREAKER_REASON != ERROR_RATE_REASON)

    # ── 4. fail-closed negatives ────────────────────────────────────────
    duplicated = rows + [dict(rows[0])]
    expect_exit("duplicate key fails closed", lambda: group_rows(duplicated), "duplicate_pair_key")
    missing = [row for row in rows if not (row["round"] == 1 and row["variant"] == "ctl" and row["idx"] == 0)]
    expect_exit("missing arm item fails closed",
                lambda: paired_counts(missing, "ctl", "treat", round_no=1), "unpaired_items")
    partial = [row for row in rows if not (row["round"] == 2 and row["idx"] == 2)]
    expect_exit("partial window (completed != expected) fails closed",
                lambda: paired_counts(partial, "ctl", "treat", round_no=2, expected_n=3),
                "completed_n_mismatch")
    unresolvable = [answer_row("does/not/exist.jsonl", 1, "ctl", 0, "correct")]
    expect_exit("unresolvable dataset hash fails closed",
                lambda: group_rows(unresolvable), "dataset_sha256_unresolvable")
    expect_exit("real overlap blocks independent pooling",
                lambda: assert_pooling_allowed([
                    REPO_ROOT / "sample_data/complex_capability_freeze_48.jsonl",
                    REPO_ROOT / "sample_data/medium_capability_freeze_60.jsonl",
                ]), "dataset_overlap_blocks_pooling")

    # ── 5. real-dataset overlap audit (24 shared / 84 unique) ──────────
    overlap = detect_dataset_overlap([
        REPO_ROOT / "sample_data/complex_capability_freeze_48.jsonl",
        REPO_ROOT / "sample_data/medium_capability_freeze_60.jsonl",
    ])
    pair_key = next(iter(overlap["overlaps"]))
    check("complex48 vs medium60 overlap == 24",
          overlap["overlaps"][pair_key]["count"] == 24,
          json.dumps({k: overlap["unique_counts"][k] for k in overlap["unique_counts"]}))
    check("dedup union == 84 unique problems", overlap["union_unique"] == 84,
          f"union={overlap['union_unique']}")
    overlap_public = detect_dataset_overlap([
        REPO_ROOT / "sample_data/public_regression_112.jsonl",
        REPO_ROOT / "sample_data/complex_capability_freeze_48.jsonl",
        REPO_ROOT / "sample_data/medium_capability_freeze_60.jsonl",
    ])
    print(f"[info] public112 overlap with legacy sets: {json.dumps(overlap_public['overlaps'])}")

    # synthetic dsA/dsB single-problem overlap is detected
    overlap_synth = detect_dataset_overlap([ARTIFACT_DIR / "dsA.jsonl", ARTIFACT_DIR / "dsB.jsonl"])
    synth_pair = next(iter(overlap_synth["overlaps"]))
    check("synthetic single-problem overlap detected",
          overlap_synth["overlaps"][synth_pair]["count"] == 1)

    # ── 6. classifier distribution + stored-label mismatch audit ───────
    audits = {}
    for name in ("public_regression_112", "complex_capability_freeze_48", "medium_capability_freeze_60"):
        audits[name] = classifier_label_audit(REPO_ROOT / "sample_data" / f"{name}.jsonl")
    pub = audits["public_regression_112"]
    check("public112 runtime classifier all calculation",
          pub["runtime_label_counts"] == {"calculation": 112},
          json.dumps(pub["runtime_label_counts"]))
    for name, audit in audits.items():
        print(f"[info] {name}: stored={json.dumps(audit['stored_label_counts'])} "
              f"runtime={json.dumps(audit['runtime_label_counts'])} mismatches={audit['mismatch_count']}")

    # ── 7. legacy CLI still runs end-to-end (backwards compatibility) ──
    answers_path = ARTIFACT_DIR / "legacy_answers.jsonl"
    write_jsonl(answers_path, rows)
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "analyze_paired_ab.py"),
         str(answers_path), "--baseline", "ctl", "--treatment", "treat", "--cluster"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    check("CLI end-to-end on positive artifacts",
          completed.returncode == 0 and '"b": 2' in completed.stdout,
          (completed.stderr or completed.stdout)[:200])

    passed = all(entry["passed"] for entry in CHECKS)
    summary = {
        "experiment": "PRE0-STATIC-001",
        "all_passed": passed,
        "checks": CHECKS,
        "classifier_audits": audits,
        "overlap_complex_medium": {
            "overlap_count": overlap["overlaps"][pair_key]["count"],
            "union_unique": overlap["union_unique"],
            "unique_counts": overlap["unique_counts"],
        },
        "overlap_public_vs_legacy": {
            "total_overlap_pairs": overlap_public["total_overlap_pairs"],
            "overlaps": overlap_public["overlaps"],
        },
    }
    (EXPERIMENT_DIR / "pre0_static_checks.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": passed, "checks": len(CHECKS)}, ensure_ascii=False))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
