"""Build combined length telemetry + source pool from harvest answer files.

Converts per-item answer rows (with total_completion_tokens) into the
telemetry schema consumed by scripts/build_length_pressure_set.py.
Reported completion tokens include thinking that sits outside the visible
max_tokens cap, so values are clamped to the ceiling: a truncated call reads
as fraction 1.0 (maximum pressure) instead of an invalid >1 value.
Complex-freeze items are re-keyed by +offset so the two pools cannot collide.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, required=True,
                        help="Worktree root holding docs/*_answers.jsonl harvest files")
    parser.add_argument("--repo-root", type=Path, required=True,
                        help="Repo root holding sample_data source datasets")
    parser.add_argument("--ceiling", type=int, default=4096)
    parser.add_argument("--complex-idx-offset", type=int, default=1000)
    parser.add_argument("--out-telemetry", type=Path, required=True)
    parser.add_argument("--out-pool", type=Path, required=True)
    parser.add_argument("--out-sidecar", type=Path, required=True)
    args = parser.parse_args()

    sources = {
        ("complex", "sample_data/complex_capability_freeze_48.jsonl", args.complex_idx_offset),
        ("public", "sample_data/public_regression_112.jsonl", 0),
    }

    telemetry: list[dict] = []
    pool: list[dict] = []
    sidecar: list[dict] = []

    for dataset, src_file, offset in sorted(sources):
        rows = load_jsonl(args.worktree / f"docs/length_telemetry_harvest_2026-08-24_{dataset}_answers.jsonl")
        src_items = {it["idx"]: it for it in load_jsonl(args.repo_root / src_file)}
        for row in rows:
            new_idx = row["idx"] + offset
            raw = row.get("total_completion_tokens")
            if raw is None:
                continue
            telemetry.append({
                "idx": new_idx,
                "completion_tokens": min(int(raw), args.ceiling),
                "ceiling_tokens": args.ceiling,
                "finish_reason": row.get("main_finish_reason"),
                "variant": row.get("variant"),
            })
            src = src_items.get(row["idx"])
            if src:
                item = dict(src)
                item["idx"] = new_idx
                item.setdefault("source", f"harvest:{dataset}")
                item.setdefault("source_ref", f'{dataset}:idx{row["idx"]}')
                pool.append(item)
                sidecar.append({"idx": new_idx, "answer": src.get("answer", ""),
                                "origin_dataset": dataset})

    for out, payload in ((args.out_telemetry, telemetry), (args.out_pool, pool),
                         (args.out_sidecar, sidecar)):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in payload) + "\n",
                       encoding="utf-8")
    print(f"telemetry={len(telemetry)} pool={len(pool)} sidecar={len(sidecar)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
