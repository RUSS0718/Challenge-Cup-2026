"""V4-HARD20-DUAL-001 runner: KCV vs PS-C, workers=3, no baseline arm."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import comb
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
    extract_answer_first,
    extract_final_answer,
)

_write_lock = threading.Lock()
INTEGER_RE = re.compile(r"-?\d+")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def arm_config(name: str) -> AgentConfig:
    if name == "kcv":
        return dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_condition_checked_selection=True,
            enable_plan_solve_compact=False,
            enable_stateful_tail_completion=False,
            enable_adaptive_voting=False,
            enable_heterogeneous_reasoners=True,
            max_model_calls=4,
            max_tokens=4096,
        )
    if name == "psc":
        return dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_condition_checked_selection=False,
            enable_plan_solve_compact=True,
            enable_stateful_tail_completion=False,
            enable_adaptive_voting=False,
            max_model_calls=2,
            max_tokens=3072,
        )
    raise ValueError(name)


def extract_for_judge(result: dict[str, Any]) -> str:
    extracted = str(result.get("extracted_answer") or "").strip()
    final = str(result.get("final_response") or "").strip()
    if extracted and extracted.upper() != "UNKNOWN":
        return extracted
    return extract_answer_first(final) or extract_final_answer(final) or final


def aime_int(text: str) -> int | None:
    matches = INTEGER_RE.findall(text or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def native_score(pred: str, gold: str, family: str) -> dict[str, Any]:
    if not pred or pred.strip().upper() in {"UNKNOWN", "未能生成有效数学答案。"}:
        return {"verdict": "invalid", "detail": "empty_or_unknown"}
    if family == "AIME":
        got = aime_int(pred)
        try:
            expected = int(str(gold).strip())
        except ValueError:
            return {"verdict": "invalid", "detail": "gold_not_int"}
        if got is None:
            return {"verdict": "invalid", "detail": "pred_not_int"}
        return {"verdict": "correct" if got == expected else "incorrect", "detail": f"{got} vs {expected}"}
    equiv = answer_equivalence(pred, str(gold))
    if equiv == "EQUIVALENT":
        return {"verdict": "correct", "detail": "contract_equivalent"}
    if equiv == "NOT_EQUIVALENT":
        return {"verdict": "incorrect", "detail": "contract_not_equivalent"}
    return {"verdict": "invalid", "detail": "unparseable"}


def contract_score(pred: str, gold: str) -> dict[str, Any]:
    if not pred or pred.strip().upper() in {"UNKNOWN", "未能生成有效数学答案。"}:
        return {"verdict": "invalid"}
    extracted = extract_answer_first(pred) or extract_final_answer(pred) or pred
    equiv = answer_equivalence(extracted, str(gold))
    if equiv == "EQUIVALENT":
        return {"verdict": "correct"}
    if equiv == "NOT_EQUIVALENT":
        return {"verdict": "incorrect"}
    return {"verdict": "invalid"}


def binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    p_obs = comb(n, k) * (0.5 ** n)
    total = sum(comb(n, i) * (0.5 ** n) for i in range(n + 1) if comb(n, i) * (0.5 ** n) <= p_obs + 1e-15)
    return min(1.0, total)


def solve_one(item: dict[str, Any], arm: str, timeout: int) -> dict[str, Any]:
    client = InternChatClient(timeout=timeout)
    agent = ReasoningAgent(client=client, config=arm_config(arm))
    t0 = time.time()
    status = "ok"
    try:
        result = agent.solve(item["problem"], {"idx": item.get("item_id")})
    except Exception as exc:
        status = f"error:{getattr(exc, 'category', type(exc).__name__)}"
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": [{"step": "error", "reason": status}]}
    duration = time.time() - t0
    trace = result.get("trace") or []
    calls = int(trace[-1].get("model_calls") or 0) if trace else 0
    pred = extract_for_judge(result)
    native = native_score(pred, item["answer"], item["source_family"])
    contract = contract_score(result.get("final_response", ""), item["answer"])
    invalid = native["verdict"] == "invalid" or str(result.get("final_response", "")).strip() in {
        "", "UNKNOWN", "未能生成有效数学答案。"
    }
    model_error = status.startswith("error")
    compact_trace = []
    keep = {
        "step", "status", "reason", "model_calls", "candidate_id", "schema_valid",
        "method", "generation_calls", "max_model_calls", "top_group_size", "plan_chars",
    }
    for entry in trace:
        compact_trace.append({k: entry[k] for k in entry if k in keep})
    return {
        "arm": arm,
        "item_id": item["item_id"],
        "source_family": item["source_family"],
        "language": item["language"],
        "subject": item["subject"],
        "status": status,
        "final_response": result.get("final_response", ""),
        "extracted_answer": result.get("extracted_answer", ""),
        "pred": pred,
        "native": native,
        "contract": contract,
        "invalid": invalid,
        "model_error": model_error,
        "model_calls": calls,
        "duration_seconds": duration,
        "trace": compact_trace,
        "gold": item["answer"],
    }


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm = {"kcv": [r for r in rows if r["arm"] == "kcv"], "psc": [r for r in rows if r["arm"] == "psc"]}
    stats: dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        stats[arm] = {
            "n": len(arm_rows),
            "native_correct": sum(1 for r in arm_rows if r["native"]["verdict"] == "correct"),
            "native_incorrect": sum(1 for r in arm_rows if r["native"]["verdict"] == "incorrect"),
            "invalid": sum(1 for r in arm_rows if r["invalid"]),
            "model_error": sum(1 for r in arm_rows if r["model_error"] or str(r["status"]).startswith("error")),
            "mean_calls": (sum(r["model_calls"] for r in arm_rows) / len(arm_rows)) if arm_rows else 0,
            "mean_duration": (sum(r["duration_seconds"] for r in arm_rows) / len(arm_rows)) if arm_rows else 0,
        }
        for family in ("OlymMATH", "AIME"):
            subset = [r for r in arm_rows if r["source_family"] == family]
            stats[arm][family] = {
                "n": len(subset),
                "native_correct": sum(1 for r in subset if r["native"]["verdict"] == "correct"),
            }
    paired: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        paired.setdefault(row["item_id"], {})[row["arm"]] = row
    b = c = 0
    for pair in paired.values():
        if "kcv" not in pair or "psc" not in pair:
            continue
        a_ok = pair["kcv"]["native"]["verdict"] == "correct"
        b_ok = pair["psc"]["native"]["verdict"] == "correct"
        if a_ok and not b_ok:
            b += 1
        elif b_ok and not a_ok:
            c += 1
    delta_correct = stats["kcv"]["native_correct"] - stats["psc"]["native_correct"]
    p_value = binom_two_sided(min(b, c), b + c)
    winner = None
    if (
        stats["kcv"]["native_correct"] >= stats["psc"]["native_correct"]
        and delta_correct >= 2
        and stats["kcv"]["invalid"] + stats["kcv"]["model_error"] <= stats["psc"]["invalid"] + stats["psc"]["model_error"] + 2
        and stats["kcv"]["mean_calls"] <= stats["psc"]["mean_calls"] * 1.10 + 1e-9
    ):
        winner = "kcv"
    elif (
        stats["psc"]["native_correct"] >= stats["kcv"]["native_correct"]
        and (stats["psc"]["native_correct"] - stats["kcv"]["native_correct"]) >= 2
        and stats["psc"]["invalid"] + stats["psc"]["model_error"] <= stats["kcv"]["invalid"] + stats["kcv"]["model_error"] + 2
        and stats["psc"]["mean_calls"] <= stats["kcv"]["mean_calls"] * 1.10 + 1e-9
    ):
        winner = "psc"
    n = max(stats["kcv"]["n"], 1)
    health_ok = stats["kcv"]["model_error"] / n <= 0.10 and stats["psc"]["model_error"] / n <= 0.10
    complete = stats["kcv"]["n"] == 20 and stats["psc"]["n"] == 20
    if not complete or not health_ok:
        verdict = "VOID"
    elif winner:
        verdict = "WINNER_" + winner.upper()
    else:
        verdict = "EXPLORATORY_NO_WINNER"
    return {
        "stats": stats,
        "b_kcv_wins": b,
        "c_psc_wins": c,
        "sign_test_p": p_value,
        "delta_correct_kcv_minus_psc": delta_correct,
        "winner": winner,
        "health_ok": health_ok,
        "complete": complete,
        "verdict": verdict,
    }


def run(output_dir: Path, timeout: int, workers: int, seed: int, hard_stop: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "official_like_hard20_v1.jsonl"
    answers_path = output_dir / "answers.jsonl"
    items = load_jsonl(dataset_path)
    if len(items) != 20:
        raise SystemExit(f"dataset n={len(items)}")
    dataset_sha = sha256_file(dataset_path)
    completed = set()
    if answers_path.exists():
        for row in load_jsonl(answers_path):
            completed.add((row["arm"], row["item_id"]))

    rng = random.Random(seed)
    order = list(range(20))
    rng.shuffle(order)
    tasks = []
    for idx in order:
        item = items[idx]
        first = "kcv" if rng.random() < 0.5 else "psc"
        second = "psc" if first == "kcv" else "kcv"
        for arm in (first, second):
            if (arm, item["item_id"]) not in completed:
                tasks.append((arm, item))

    manifest = {
        "run_id": "V4-HARD20-DUAL-001",
        "dataset_sha256": dataset_sha,
        "seed": seed,
        "workers": workers,
        "timeout_seconds": timeout,
        "hard_stop_seconds": hard_stop,
        "arms": ["condition_checked_selection_v1", "plan_solve_compact_v1"],
        "n_items": 20,
        "expected_solves": 40,
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "start_unix": time.time(),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[V4-HARD20] pending solves={len(tasks)} dataset={dataset_sha[:12]} workers={workers}", flush=True)

    start = time.time()

    def job(task):
        if time.time() - start > hard_stop:
            return {"skipped": True, "reason": "hard_stop"}
        arm, item = task
        record = solve_one(item, arm, timeout)
        record["round"] = 1
        with _write_lock:
            with answers_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
        print(
            f"[{arm}] {item['item_id']} native={record['native']['verdict']} "
            f"calls={record['model_calls']} dur={record['duration_seconds']:.0f}s",
            flush=True,
        )
        return record

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, t) for t in tasks]
        for fut in as_completed(futures):
            fut.result()

    rows = load_jsonl(answers_path)
    summary = analyze(rows)
    summary["elapsed_seconds"] = time.time() - start
    summary["dataset_sha256"] = dataset_sha
    (output_dir / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "docs" / "experiments" / "V4-HARD20-DUAL-001"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--hard-stop-seconds", type=float, default=180 * 60)
    args = parser.parse_args()
    run(Path(args.output_dir), args.timeout, args.workers, args.seed, args.hard_stop_seconds)
