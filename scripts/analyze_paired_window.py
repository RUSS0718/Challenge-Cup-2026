"""Analyze a same-question paired diagnostic window (Issue #16 step 3 loop).

Reads one experiment directory produced by run_external_hard_sets_smoke.py
with --pairing paired and prints/aggregates the paired outcome matrix plus
the acceptance metrics the iteration loop needs:

- per-item paired verdict matrix and net correct gain (candidate - baseline),
  including correct->incorrect reversals;
- E valid-final formation rate and E truncation rate (finish_reason aligned
  by successful-call order; client retries may shift indices, so '?' marks
  unavailable);
- for arms with d_result_to_e: whether E's final copied the injected
  FINAL_D_FOR_CHECK verbatim, produced a different value, or abstained;
- handoff field-state aggregates (absent/unknown/conflict/unclosed/content);
- mean and nearest-rank P95 duration per arm.

Pure aggregation over the recorded answers.jsonl; zero model calls.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def finish_reason_at(record: dict[str, Any], index: int) -> str:
    reasons = record.get("client_finish_reasons") or []
    return str(reasons[index]) if index < len(reasons) else "unavailable"


def finalize_source(record: dict[str, Any]) -> str:
    for event in record.get("trace") or []:
        if event.get("stage") == "finalize":
            return str(event.get("fallback_source") or "?")
    return "?"


def nearest_rank_p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(0.95 * len(ordered))) - 1]


def analyze_paired(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_item: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_item[row["item_id"]][row["arm"]] = row
    arms = sorted({r["arm"] for r in rows})
    if len(arms) != 2:
        return {"error": f"expected exactly 2 arms, got {arms}", "arms": arms}
    base, cand = arms[0], arms[1]

    matrix: Counter = Counter()
    net_correct = 0
    reversals: list[dict[str, str]] = []
    gains: list[dict[str, str]] = []
    stats: dict[str, dict[str, Any]] = {}
    for arm in (base, cand):
        sub = [r for r in rows if r["arm"] == arm]
        durs = [float(r["duration_seconds"]) for r in sub]
        e_len = sum(1 for r in sub if finish_reason_at(r, 4) == "length")
        e_final = sum(
            1 for r in sub
            if str(r.get("final_response", "")).strip().upper() not in {"", "UNKNOWN"}
        )
        states_counter: Counter = Counter()
        missing = unknown = conflict = unclosed = 0
        copies = visible_candidates = 0
        for r in sub:
            for e in r.get("trace") or []:
                if e.get("stage") != "finalize":
                    continue
                for field, state in (e.get("handoff_field_states") or {}).items():
                    states_counter[state] += 1
                missing += len(e.get("handoff_missing_fields") or [])
                unknown += len(e.get("handoff_unknown_fields") or [])
                conflict += len(e.get("handoff_conflict_fields") or [])
                unclosed += len(e.get("handoff_unclosed_fields") or [])
                if e.get("d_candidate_visible_to_e"):
                    visible_candidates += 1
                    if e.get("e_final_equals_d_candidate"):
                        copies += 1
        stats[arm] = {
            "n": len(sub),
            "correct": sum(1 for r in sub if r["native"]["verdict"] == "correct"),
            "incorrect": sum(1 for r in sub if r["native"]["verdict"] == "incorrect"),
            "invalid": sum(1 for r in sub if r["native"]["verdict"] == "invalid"),
            "unknown_final": sum(
                1 for r in sub if str(r.get("final_response", "")).strip().upper() == "UNKNOWN"
            ),
            "e_final_formed": e_final,
            "e_truncation": e_len,
            "mean_duration_s": round(sum(durs) / len(durs), 2) if durs else 0,
            "p95_duration_s": nearest_rank_p95(durs),
            "handoff_field_states": dict(states_counter),
            "handoff_missing": missing,
            "handoff_unknown": unknown,
            "handoff_conflict": conflict,
            "handoff_unclosed": unclosed,
            "d_candidate_visible": visible_candidates,
            "e_final_copied_candidate": copies,
            # 逐阶段 finish_reason 计数（A/B/C/D/E = 成功调用序 0-4）。
            "stage_finish_reasons": {
                name: dict(Counter(finish_reason_at(r, idx) for r in sub))
                for idx, name in enumerate(("A", "B", "C", "D", "E"))
            },
        }

    for item_id, arms_map in sorted(by_item.items()):
        if base not in arms_map or cand not in arms_map:
            continue
        a = arms_map[base]["native"]["verdict"]
        b = arms_map[cand]["native"]["verdict"]
        matrix[f"{a}->{b}"] += 1
        if a == "correct":
            net_correct -= 1
            if b == "incorrect":
                reversals.append({"item_id": item_id, "from": a, "to": b})
        if b == "correct":
            net_correct += 1
            if a != "correct":
                gains.append({"item_id": item_id, "from": a, "to": b})

    copied = corrected = unconfirmed = 0
    for item_id, arms_map in sorted(by_item.items()):
        if cand not in arms_map:
            continue
        cand_row = arms_map[cand]
        base_row = arms_map.get(base, {})
        cand_final = str(cand_row.get("final_response", "")).strip()
        if not cand_final or cand_final.upper() == "UNKNOWN":
            unconfirmed += 1
        elif base_row and cand_final == str(base_row.get("final_response", "")).strip():
            copied += 1
        else:
            corrected += 1

    return {
        "arms": {"baseline": base, "candidate": cand},
        "per_arm": stats,
        "paired_matrix": dict(matrix),
        "net_correct_gain": net_correct,
        "correct_gains": gains,
        "correct_reversals": reversals,
        "candidate_final_disposition": {
            "copied_from_base": copied,
            "different_value": corrected,
            "unconfirmed": unconfirmed,
        },
        "n_paired_items": sum(1 for m in by_item.values() if base in m and cand in m),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--json", action="store_true", help="print full JSON")
    args = parser.parse_args()
    rows_path = args.experiment_dir / "answers.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = analyze_paired(rows)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))
    if not args.json:
        s = result.get("per_arm", {})
        for arm, st in s.items():
            print(f"[{arm}] correct={st['correct']} incorrect={st['incorrect']} invalid={st['invalid']} "
                  f"e_final={st['e_final_formed']} e_len={st['e_truncation']} "
                  f"dur={st['mean_duration_s']}/p95={st['p95_duration_s']}")
        print("paired matrix:", result.get("paired_matrix"))
        print("net correct gain:", result.get("net_correct_gain"))
        print("candidate final disposition:", result.get("candidate_final_disposition"))


if __name__ == "__main__":
    if "--selftest" not in sys.argv:
        main()
