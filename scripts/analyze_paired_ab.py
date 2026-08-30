"""Exact McNemar analysis for interleaved paired A/B answer files.

PRE0-STATIC-001 (2026-08-30): the unique pairing key is
``(dataset_sha256, round, item_id, variant)``.  The legacy implementation
paired by ``idx`` alone and silently overwrote cross-round / cross-dataset
records (local_evaluation_benchmark_audit_2026-08-29 §2.3); duplicates now
fail closed.  Health (error-rate) gating, circuit-breaker separation, and the
item-cluster sign test follow math_reasoning_agent_experiment_driven_spec
2026-08-29 §4.2-§4.5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ERROR_RATE_VOID_THRESHOLD = 0.10
BREAKER_REASON = "consecutive_model_errors"
ERROR_RATE_REASON = "error_rate_above_threshold"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial McNemar p-value (pure stdlib).

    Also serves as the exact sign test for item-cluster ``b``/``c``.
    """
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def normalize_problem_text(text: str) -> str:
    """Canonical problem-text form for dedup/overlap: NFKC, no whitespace, lower."""
    normalized = unicodedata.normalize("NFKC", str(text))
    return "".join(normalized.split()).lower()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def resolve_dataset_sha256(input_file: str, sha_map: dict[str, str] | None = None) -> str:
    """Resolve the dataset content hash for a recorded ``input_file`` string.

    Resolution order: explicit ``sha_map`` (from run manifest) → repo-relative
    path → answer-file-relative path.  Fail closed when neither file nor map
    entry exists: a path string must never stand in for the content hash.
    """
    if sha_map and input_file in sha_map:
        return sha_map[input_file]
    for base in (REPO_ROOT, Path.cwd()):
        candidate = base / input_file
        if candidate.is_file():
            return sha256_file(candidate)
    raise SystemExit(
        f"dataset_sha256_unresolvable:{input_file} — provide --sha-map or the dataset file"
    )


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def is_error_row(row: dict) -> bool:
    """Model-error rows: explicit status or the runner's diagnostic marker."""
    if row.get("result_status") == "error":
        return True
    return "model_error" in (row.get("diagnostic_reasons") or [])


def _require_fields(row: dict, source: str) -> None:
    for field in ("input_file", "round", "variant", "idx"):
        if row.get(field) is None:
            raise SystemExit(f"missing_field:{field} in {source}")


def group_rows(rows: list[dict], sha_map: dict[str, str] | None = None) -> dict[tuple, dict]:
    """Group answer rows by the full pairing key; duplicates fail closed."""
    grouped: dict[tuple, dict] = {}
    for position, row in enumerate(rows):
        _require_fields(row, f"line {position + 1}")
        dataset_sha = resolve_dataset_sha256(row["input_file"], sha_map)
        key = (dataset_sha, row["round"], row["idx"], row["variant"])
        if key in grouped:
            raise SystemExit(
                f"duplicate_pair_key:{key} — cross-round/variant records must never overwrite"
            )
        grouped[key] = row
    return grouped


def paired_counts(rows: list[dict], baseline_name: str, treatment_name: str,
                  round_no: int | None = None, expected_n: int | None = None,
                  sha_map: dict[str, str] | None = None) -> dict:
    """Pair verdicts per (dataset, round, item); unknown/incorrect/error count as not-correct.

    Completeness is fail-closed: both arms must cover the same item set, and
    ``expected_n`` (per arm) must match when provided.
    """
    grouped = group_rows(rows, sha_map)
    by_variant: dict[str, dict[tuple, dict]] = {baseline_name: {}, treatment_name: {}}
    datasets: set[str] = set()
    for (dataset_sha, row_round, item_id, variant), row in grouped.items():
        if round_no is not None and row_round != round_no:
            continue
        if variant in by_variant:
            by_variant[variant][(dataset_sha, row_round, item_id)] = row
            datasets.add(dataset_sha)

    base = by_variant[baseline_name]
    treat = by_variant[treatment_name]
    if not base and not treat:
        raise SystemExit("no_paired_rows_after_filtering")
    if set(base) != set(treat):
        raise SystemExit(
            f"unpaired_items: only_baseline={sorted(set(base) - set(treat))} "
            f"only_treatment={sorted(set(treat) - set(base))}"
        )
    if expected_n is not None and len(base) != expected_n:
        raise SystemExit(f"completed_n_mismatch: expected={expected_n} completed={len(base)}")

    b = c = baseline_correct = treatment_correct = 0
    baseline_errors = treatment_errors = 0
    for key in sorted(base):
        base_row, treat_row = base[key], treat[key]
        base_hit = base_row.get("verdict") == "correct"
        treat_hit = treat_row.get("verdict") == "correct"
        baseline_correct += base_hit
        treatment_correct += treat_hit
        baseline_errors += is_error_row(base_row)
        treatment_errors += is_error_row(treat_row)
        if treat_hit and not base_hit:
            b += 1
        elif base_hit and not treat_hit:
            c += 1

    n_paired = len(base)
    result = {
        "n_paired": n_paired,
        "datasets": sorted(datasets),
        "round": round_no,
        "b": b,
        "c": c,
        "baseline_correct": baseline_correct,
        "treatment_correct": treatment_correct,
        "baseline_errors": baseline_errors,
        "treatment_errors": treatment_errors,
        "mean_gain": (treatment_correct - baseline_correct) / n_paired if n_paired else 0.0,
        "mcnemar_exact_p": mcnemar_exact(b, c),
        "significant_at_0_05": mcnemar_exact(b, c) < 0.05,
    }
    if expected_n is not None:
        result["error_rates"] = {
            baseline_name: baseline_errors / expected_n,
            treatment_name: treatment_errors / expected_n,
        }
        result["void"] = any(rate > ERROR_RATE_VOID_THRESHOLD for rate in result["error_rates"].values())
        result["void_reason"] = ERROR_RATE_REASON if result["void"] else None
    return result


def window_void_state(rows: list[dict], arms: list[str], expected_n: int,
                      breaker_report: dict | None = None,
                      sha_map: dict[str, str] | None = None) -> dict:
    """Window-level health state: error-rate VOID and runner breaker kept separate.

    The runner's consecutive-error breaker is an ``aborted_resource_guard``
    signal; the preregistered health VOID is the per-arm error-rate test.  Both
    fields are reported distinctly and either one voids the window.
    """
    grouped = group_rows(rows, sha_map)
    per_arm: dict[str, int] = {arm: 0 for arm in arms}
    seen: dict[str, int] = {arm: 0 for arm in arms}
    for _key, row in grouped.items():
        arm = row["variant"]
        if arm in per_arm:
            seen[arm] += 1
            per_arm[arm] += int(is_error_row(row))
    incomplete = any(seen[arm] != expected_n for arm in arms)
    error_rates = {arm: per_arm[arm] / expected_n for arm in arms}
    error_rate_void = any(rate > ERROR_RATE_VOID_THRESHOLD for rate in error_rates.values())
    breaker_tripped = bool((breaker_report or {}).get("void", False))
    state = {
        "completed_counts": seen,
        "expected_n": expected_n,
        "complete": not incomplete,
        "error_counts": per_arm,
        "error_rates": error_rates,
        "error_rate_void": error_rate_void,
        "error_rate_void_reason": ERROR_RATE_REASON if error_rate_void else None,
        "breaker_tripped": breaker_tripped,
        "breaker_reason": BREAKER_REASON if breaker_tripped else None,
        "breaker_max_streak": (breaker_report or {}).get("consecutive_failures_max"),
        "void": error_rate_void or breaker_tripped or incomplete,
        "void_reason": (
            ERROR_RATE_REASON if error_rate_void
            else BREAKER_REASON if breaker_tripped
            else "incomplete_window" if incomplete
            else None
        ),
    }
    return state


def item_cluster_counts(rows: list[dict], baseline_name: str, treatment_name: str,
                        sha_map: dict[str, str] | None = None) -> dict:
    """Cluster-sign-test counts with the item as the unit (spec §4.5).

    ``delta_i`` = treatment correct count across rounds − baseline correct count
    across rounds; ``b``/``c`` count positive/negative deltas; ties (0) are
    excluded.  Item-round pooling is reported descriptively only.
    """
    grouped = group_rows(rows, sha_map)
    items: dict[tuple, dict] = {}
    for (dataset_sha, row_round, item_id, variant), row in grouped.items():
        if variant not in (baseline_name, treatment_name):
            continue
        entry = items.setdefault(
            (dataset_sha, item_id),
            {"seen": {baseline_name: set(), treatment_name: set()},
             "correct": {baseline_name: set(), treatment_name: set()}},
        )
        entry["seen"][variant].add(row_round)
        if row.get("verdict") == "correct":
            entry["correct"][variant].add(row_round)

    b = c = baseline_total = treatment_total = 0
    deltas: dict[str, int] = {}
    for key in sorted(items):
        entry = items[key]
        base_seen = entry["seen"][baseline_name]
        treat_seen = entry["seen"][treatment_name]
        if base_seen != treat_seen:
            # Both arms must attempt the same rounds for the item, or it is
            # incomplete and any delta would be an artifact.
            raise SystemExit(f"round_set_mismatch:{key}: {sorted(base_seen)} vs {sorted(treat_seen)}")
        delta = len(entry["correct"][treatment_name]) - len(entry["correct"][baseline_name])
        deltas[str(key)] = delta
        baseline_total += len(entry["correct"][baseline_name])
        treatment_total += len(entry["correct"][treatment_name])
        if delta > 0:
            b += 1
        elif delta < 0:
            c += 1

    item_round_pooled: dict = {}
    # Descriptive item-round pooling: pair per round independently.
    pooled_b = pooled_c = 0
    item_round_pairs = 0
    by_round: dict[int, dict[tuple, dict[str, bool]]] = {}
    for (dataset_sha, row_round, item_id, variant), row in grouped.items():
        if variant not in (baseline_name, treatment_name):
            continue
        slot = by_round.setdefault(row_round, {})
        slot.setdefault((dataset_sha, item_id), {})[variant] = row.get("verdict") == "correct"
    for slot in by_round.values():
        for key, arms in slot.items():
            if set(arms) != {baseline_name, treatment_name}:
                continue
            item_round_pairs += 1
            if arms[treatment_name] and not arms[baseline_name]:
                pooled_b += 1
            elif arms[baseline_name] and not arms[treatment_name]:
                pooled_c += 1
    item_round_pooled.update({
        "n_item_rounds": item_round_pairs,
        "b": pooled_b,
        "c": pooled_c,
        "p": mcnemar_exact(pooled_b, pooled_c),
        "note": "descriptive only; never formal significance evidence (spec §4.5)",
    })

    return {
        "n_items": len(items),
        "b": b,
        "c": c,
        "ties": len(items) - b - c,
        "baseline_cluster_correct": baseline_total,
        "treatment_cluster_correct": treatment_total,
        "sign_test_exact_p": mcnemar_exact(b, c),
        "significant_at_0_05": mcnemar_exact(b, c) < 0.05,
        "deltas": deltas,
        "item_round_pooled_descriptive": item_round_pooled,
    }


def detect_dataset_overlap(files: list[Path]) -> dict:
    """Overlap of normalized problem texts across datasets (spec §5.1)."""
    hashes_per_file: dict[str, set[str]] = {}
    items_per_file: dict[str, dict[str, dict]] = {}
    for path in files:
        entries: dict[str, dict] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            digest = sha256_bytes(normalize_problem_text(item["problem"]).encode("utf-8"))
            entries[digest] = item
        hashes_per_file[str(path)] = set(entries)
        items_per_file[str(path)] = entries
    names = list(hashes_per_file)
    overlaps: dict[str, list[str]] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            shared = sorted(hashes_per_file[names[i]] & hashes_per_file[names[j]])
            if shared:
                overlaps[f"{names[i]}||{names[j]}"] = shared
    union: set[str] = set()
    for hashes in hashes_per_file.values():
        union |= hashes
    return {
        "files": names,
        "unique_counts": {name: len(hashes) for name, hashes in hashes_per_file.items()},
        "union_unique": len(union),
        "overlaps": {pair: {"count": len(digests), "digests": digests[:5]} for pair, digests in overlaps.items()},
        "total_overlap_pairs": sum(len(digests) for digests in overlaps.values()),
    }


def assert_pooling_allowed(files: list[Path]) -> None:
    """Refuse to treat overlapping datasets as independent samples."""
    report = detect_dataset_overlap(files)
    if report["overlaps"]:
        raise SystemExit(f"dataset_overlap_blocks_pooling:{report['overlaps'].keys()}")


def classifier_label_audit(path: Path) -> dict:
    """Record stored task_type vs runtime classifier distribution for a local set."""
    sys.path.insert(0, str(REPO_ROOT))
    from user_agent import classify_problem_type

    stored: dict[str, int] = {}
    runtime: dict[str, int] = {}
    mismatches: list[dict] = []
    count = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        count += 1
        stored_label = item.get("task_type") or "<absent>"
        runtime_label = classify_problem_type(item["problem"])
        stored[stored_label] = stored.get(stored_label, 0) + 1
        runtime[runtime_label] = runtime.get(runtime_label, 0) + 1
        if stored_label != runtime_label:
            mismatches.append({"idx": item.get("idx"), "stored": stored_label, "runtime": runtime_label})
    return {
        "dataset": str(path),
        "count": count,
        "stored_label_counts": stored,
        "runtime_label_counts": runtime,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exact McNemar test on paired protocol A/B answers.")
    parser.add_argument("answers", type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--round", type=int, help="Restrict to one recorded round.")
    parser.add_argument("--expected-n", type=int, help="Per-arm expected completions (fail-closed check).")
    parser.add_argument("--sha-map", type=Path, help="JSON mapping input_file -> dataset sha256.")
    parser.add_argument("--cluster", action="store_true", help="Also emit item-cluster sign test.")
    args = parser.parse_args()
    rows = load_rows(args.answers)
    sha_map = json.loads(args.sha_map.read_text(encoding="utf-8")) if args.sha_map else None

    # Resolve each row's dataset hash once, then split per dataset: multiple
    # datasets in one answers file are never pooled into one statistic.
    resolved_cache: dict[str, str] = {}
    per_dataset_rows: dict[str, list[dict]] = {}
    for row in rows:
        input_file = row.get("input_file")
        if input_file not in resolved_cache:
            resolved_cache[input_file] = resolve_dataset_sha256(input_file, sha_map)
        per_dataset_rows.setdefault(resolved_cache[input_file], []).append(row)

    def analyze(dataset_rows: list[dict]) -> dict:
        result = paired_counts(dataset_rows, args.baseline, args.treatment, round_no=args.round,
                               expected_n=args.expected_n, sha_map=sha_map)
        if args.cluster:
            result["item_cluster"] = item_cluster_counts(dataset_rows, args.baseline, args.treatment,
                                                         sha_map=sha_map)
        return result

    if len(per_dataset_rows) > 1:
        output = {
            "mode": "per_dataset",
            "datasets": {sha: analyze(dataset_rows) for sha, dataset_rows in sorted(per_dataset_rows.items())},
            "note": "multi-dataset answers are never pooled; check overlaps with detect_dataset_overlap",
        }
    else:
        output = analyze(next(iter(per_dataset_rows.values())))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
