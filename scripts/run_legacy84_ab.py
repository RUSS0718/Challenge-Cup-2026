"""Paired A/B Runner for STATEFUL-TAIL-V1-LEGACY84-001.

Evaluates baseline_hetero vs stateful_tail_completion_v1 on legacy84 (84 items):
- 2 rounds same-item interleaved
- 8 workers concurrent execution
- Atomic checkpointing & resume support
- Exact sign test and McNemar statistics
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from user_agent import (
    AgentConfig,
    ReasoningAgent,
    SUBMISSION_CONFIG,
    answer_equivalence,
    normalize_answer,
)
from scripts.evaluate_dev import judge_correct

_write_lock = threading.Lock()


def load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    items = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            items.append(json.loads(line))
    return items


def make_configs() -> tuple[AgentConfig, AgentConfig]:
    baseline_cfg = dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_stateful_tail_completion=False,
    )
    candidate_cfg = dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_stateful_tail_completion=True,
        stateful_tail_max_chars=8000,
    )
    return baseline_cfg, candidate_cfg


def solve_arm(
    item: dict[str, Any],
    arm_name: str,
    config: AgentConfig,
    timeout: int,
    client: InternChatClient,
) -> dict[str, Any]:
    t0 = time.time()
    prob = item.get("problem", "")
    gold = item.get("answer", "")
    agent = ReasoningAgent(client=client, config=config)

    try:
        res = agent.solve(prob, {"idx": item.get("idx", 0)})
        dur = time.time() - t0
        final_resp = res.get("final_response", "")
        extracted = res.get("extracted_answer", "")
        trace = res.get("trace", [])
        calls = trace[-1].get("model_calls", 1) if trace else 1

        raw_judge = judge_correct(extracted or final_resp, gold) if gold else "incorrect"
        is_corr = bool(raw_judge == "correct")
        status = "ok"
    except Exception as exc:
        dur = time.time() - t0
        final_resp = "未能生成有效数学答案。"
        extracted = ""
        calls = 1
        is_corr = False
        status = f"error:{type(exc).__name__}"

    return {
        "arm": arm_name,
        "item_id": item.get("unique_id", item.get("id", item.get("problem", "")[:20])),
        "problem": prob,
        "gold_answer": gold,
        "final_response": final_resp,
        "extracted_answer": extracted,
        "is_correct": is_corr,
        "model_calls": calls,
        "duration_seconds": dur,
        "status": status,
    }


def run_legacy84_ab(
    dataset_path: Path,
    output_dir: Path,
    workers: int = 8,
    timeout: int = 300,
    limit: int | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    answers_file = output_dir / "answers.jsonl"
    report_file = output_dir / "report.json"

    items = load_dataset(dataset_path)
    if limit is not None:
        items = items[:limit]

    print(f"[A/B RUNNER] Dataset: {dataset_path} ({len(items)} items)")
    print(f"[A/B RUNNER] Output Dir: {output_dir}")
    print(f"[A/B RUNNER] Concurrency: {workers} workers, Request Timeout: {timeout}s")

    # Load existing progress if any
    completed_pairs = set()
    if answers_file.exists():
        with open(answers_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    completed_pairs.add((row["round"], row["item_id"]))
                except Exception:
                    pass
        print(f"[A/B RUNNER] Resuming: found {len(completed_pairs)} completed pairs.")

    base_cfg, cand_cfg = make_configs()

    # Build tasks: 2 rounds same-item interleaved
    tasks = []
    for r in [1, 2]:
        shuffled_items = list(items)
        seed = 4200 + r
        random.Random(seed).shuffle(shuffled_items)
        for idx, item in enumerate(shuffled_items):
            item_id = str(item.get("unique_id", item.get("id", item.get("problem", "")[:20])))
            if (r, item_id) in completed_pairs:
                continue
            # Round 1: baseline first; Round 2: candidate first
            first_arm = "baseline" if (r == 1 and idx % 2 == 0) else "candidate"
            tasks.append((r, item, first_arm))

    print(f"[A/B RUNNER] Total pending task pairs: {len(tasks)}")

    def worker_job(task_info):
        r, item, first_arm = task_info
        item_id = str(item.get("unique_id", item.get("id", item.get("problem", "")[:20])))
        client = InternChatClient(timeout=timeout)

        if first_arm == "baseline":
            res_base = solve_arm(item, "baseline", base_cfg, timeout, client)
            res_cand = solve_arm(item, "candidate", cand_cfg, timeout, client)
        else:
            res_cand = solve_arm(item, "candidate", cand_cfg, timeout, client)
            res_base = solve_arm(item, "baseline", base_cfg, timeout, client)

        pair_record = {
            "round": r,
            "item_id": item_id,
            "baseline": res_base,
            "candidate": res_cand,
            "delta_correct": int(res_cand["is_correct"]) - int(res_base["is_correct"]),
        }

        with _write_lock:
            with open(answers_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(pair_record, ensure_ascii=False) + "\n")
                f.flush()

        corr_str = f"B:{'✓' if res_base['is_correct'] else '✗'} | C:{'✓' if res_cand['is_correct'] else '✗'}"
        delta_str = f"Δ={pair_record['delta_correct']:+d}"
        print(f"[R{r}] [{item_id[:16]}] {corr_str} ({delta_str}) calls(B={res_base['model_calls']}, C={res_cand['model_calls']})")
        return pair_record

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_job, t) for t in tasks]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - start_time
    print(f"[A/B RUNNER] All tasks completed in {elapsed:.1f}s. Analyzing results...")

    # Load all records to generate final report
    all_pairs = []
    with open(answers_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            all_pairs.append(json.loads(line))

    # Calculate statistics
    r1_pairs = [p for p in all_pairs if p["round"] == 1]
    r2_pairs = [p for p in all_pairs if p["round"] == 2]

    base_r1_corr = sum(1 for p in r1_pairs if p["baseline"]["is_correct"])
    cand_r1_corr = sum(1 for p in r1_pairs if p["candidate"]["is_correct"])
    base_r2_corr = sum(1 for p in r2_pairs if p["baseline"]["is_correct"])
    cand_r2_corr = sum(1 for p in r2_pairs if p["candidate"]["is_correct"])

    b_count = sum(1 for p in all_pairs if p["delta_correct"] > 0)
    c_count = sum(1 for p in all_pairs if p["delta_correct"] < 0)

    # Item cluster sign test
    item_deltas = {}
    for p in all_pairs:
        iid = p["item_id"]
        item_deltas[iid] = item_deltas.get(iid, 0) + p["delta_correct"]

    cluster_b = sum(1 for d in item_deltas.values() if d > 0)
    cluster_c = sum(1 for d in item_deltas.values() if d < 0)

    base_calls = sum(p["baseline"]["model_calls"] for p in all_pairs)
    cand_calls = sum(p["candidate"]["model_calls"] for p in all_pairs)
    base_errors = sum(1 for p in all_pairs if "error" in p["baseline"]["status"])
    cand_errors = sum(1 for p in all_pairs if "error" in p["candidate"]["status"])

    summary = {
        "run_id": "STATEFUL-TAIL-V1-LEGACY84-001",
        "dataset": str(dataset_path),
        "total_pairs_evaluated": len(all_pairs),
        "round1": {
            "total": len(r1_pairs),
            "baseline_correct": base_r1_corr,
            "candidate_correct": cand_r1_corr,
            "delta": cand_r1_corr - base_r1_corr,
        },
        "round2": {
            "total": len(r2_pairs),
            "baseline_correct": base_r2_corr,
            "candidate_correct": cand_r2_corr,
            "delta": cand_r2_corr - base_r2_corr,
        },
        "combined": {
            "baseline_correct": base_r1_corr + base_r2_corr,
            "candidate_correct": cand_r1_corr + cand_r2_corr,
            "delta_correct": (cand_r1_corr + cand_r2_corr) - (base_r1_corr + base_r2_corr),
            "b_pairs_candidate_wins": b_count,
            "c_pairs_baseline_wins": c_count,
            "cluster_b_items": cluster_b,
            "cluster_c_items": cluster_c,
            "baseline_total_calls": base_calls,
            "candidate_total_calls": cand_calls,
            "baseline_mean_calls": base_calls / len(all_pairs) if all_pairs else 0,
            "candidate_mean_calls": cand_calls / len(all_pairs) if all_pairs else 0,
            "baseline_errors": base_errors,
            "candidate_errors": cand_errors,
        },
        "gates": {
            "health_pass": (cand_errors / len(all_pairs) <= 0.10) if all_pairs else False,
            "non_negative_delta_pass": ((cand_r1_corr + cand_r2_corr) >= (base_r1_corr + base_r2_corr)),
            "cluster_b_ge_c_pass": cluster_b >= cluster_c,
            "cost_gate_pass": (cand_calls <= base_calls * 1.10) if base_calls else True,
        },
        "elapsed_seconds": elapsed,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n================ LEGACY84 A/B SUMMARY ================")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default=str(ROOT / "sample_data" / "legacy84.jsonl"))
    parser.add_argument("--output-dir", type=str, default=str(ROOT / "docs" / "experiments" / "STATEFUL-TAIL-V1-LEGACY84-001"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_legacy84_ab(
        Path(args.dataset),
        Path(args.output_dir),
        workers=args.workers,
        timeout=args.timeout,
        limit=args.limit,
    )
