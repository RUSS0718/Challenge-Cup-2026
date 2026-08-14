"""P0.1 token ladder experiment: truncation rate + resource gates per token cap.

Official logs showed ~98.7% finish_reason=length at 1024 tokens.  This tool runs
the single-call default path at 1536/2048/3072 (and more on request) and reports
the metrics that decide the lowest-cost cap that clears the gates:

  Gate 1 — resource/interface: nonempty final_response = 100%, total calls <= 224,
           avg calls <= 1.5, invalid <= 2%.
  Gate 2 — length: finish_reason=length (main call) <= 20% (target 10%),
           answer-marker coverage >= 95%.
  Gate 3 — accuracy: two independent A/B runs (this tool reports per-run accuracy).

Each tier is written to ``--output-file`` as soon as it finishes, so an
interrupted run keeps completed tiers.  One client per worker thread keeps the
finish_reason log per-question (each thread solves its questions serially).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from llm_client import InternChatClient  # noqa: E402
from user_agent import AgentConfig, ReasoningAgent, classify_problem_type  # noqa: E402
from scripts.evaluate_dev import load_items, judge_correct  # noqa: E402

DEFAULT_TOKENS = [1536, 2048, 3072]
DEFAULT_WORKERS = 8
# Gate 2 thresholds (official run measured ~98.7% length at 1024).
LENGTH_TARGET = 0.10
LENGTH_HARD_CAP = 0.20
MARKER_COVERAGE_TARGET = 0.95
# Gate 1 thresholds.
MAX_TOTAL_CALLS = 224
MAX_AVG_CALLS = 1.5
MAX_INVALID_RATE = 0.02

_local = threading.local()


def _worker_agent(token: int, timeout: int, retry: int) -> tuple[InternChatClient, ReasoningAgent]:
    if getattr(_local, "client", None) is None:
        client = InternChatClient(timeout=timeout, retry=retry)
        config = AgentConfig(max_tokens=token, l0_max_tokens=token)
        _local.client = client
        _local.agent = ReasoningAgent(client=client, config=config)
    return _local.client, _local.agent


def solve_one(agent: ReasoningAgent, client: InternChatClient, item: dict) -> dict:
    """Run one item and slice this item's finish_reasons from the client log.

    ``frs[0]`` is the main call, ``frs[1]`` (when present) the conditional retry.
    # ponytail: a failed network call appends no finish_reason but still counts a
    # budget call, so a rare failed-main-then-retry maps retry onto frs[0];
    # acceptable for a length-rate signal, upgrade to tagged calls if it matters.
    """
    before = len(client.finish_reasons)
    started = time.perf_counter()
    result = agent.solve(item["problem"], {"idx": item.get("idx")})
    elapsed = time.perf_counter() - started
    frs = client.finish_reasons[before:]
    trace = result.get("trace", [])
    final = next((e for e in reversed(trace) if e.get("step") == "finalize"), {})
    ptype = classify_problem_type(item["problem"])
    verdict = judge_correct(result.get("extracted_answer", "") or "", str(item["answer"]), ptype)
    return {
        "idx": item.get("idx"),
        "main_finish_reason": frs[0] if frs else None,
        "retry_finish_reason": frs[1] if len(frs) > 1 else None,
        "had_conditional_retry": any(e.get("step") == "conditional_retry" for e in trace),
        "final_response_nonempty": isinstance(result.get("final_response"), str) and bool(result["final_response"].strip()),
        "finalization_status": final.get("status"),
        "model_calls": final.get("model_calls", 0),
        "verdict": verdict,
        "extracted_answer": result.get("extracted_answer", "") or "",
        "expected": str(item["answer"]),
        "latency_seconds": round(elapsed, 3),
    }


def _length_rate(finish_reasons: list[str]) -> float:
    return sum(1 for f in finish_reasons if f == "length") / len(finish_reasons) if finish_reasons else 0.0


def _p95(sorted_values: list[float]) -> float:
    n = len(sorted_values)
    if n == 0:
        return 0.0
    idx = max(int(n * 0.95 + 0.999) - 1, 0)
    return sorted_values[min(idx, n - 1)]


def summarize(records: list[dict]) -> dict:
    total = len(records)
    main_frs = [r["main_finish_reason"] for r in records if r["main_finish_reason"]]
    retry_frs = [r["retry_finish_reason"] for r in records if r["retry_finish_reason"]]
    calls = sorted(r["model_calls"] for r in records)
    correct = sum(1 for r in records if r["verdict"] == "correct")
    decided = sum(1 for r in records if r["verdict"] in ("correct", "incorrect"))
    retried = sum(1 for r in records if r["had_conditional_retry"])
    return {
        "dataset_size": total,
        "main_finish_reason_counts": dict(Counter(main_frs)),
        "main_finish_reason_length_rate": _length_rate(main_frs),
        "retry_count": len(retry_frs),
        "retry_finish_reason_length_rate": _length_rate(retry_frs),
        "had_conditional_retry_count": retried,
        "answer_marker_coverage": (total - retried) / total if total else 0.0,
        "nonempty_final_response_rate": sum(1 for r in records if r["final_response_nonempty"]) / total if total else 0.0,
        "empty_final_response_count": sum(1 for r in records if not r["final_response_nonempty"]),
        "fallback_count": sum(1 for r in records if r["finalization_status"] == "fallback"),
        "total_model_calls": sum(r["model_calls"] for r in records),
        "average_model_calls": sum(r["model_calls"] for r in records) / total if total else 0.0,
        "p95_model_calls": _p95(calls),
        "max_model_calls": max(calls, default=0),
        "accuracy": correct / total if total else 0.0,
        "decided_accuracy": correct / decided if decided else None,
        "verdict_counts": dict(Counter(r["verdict"] for r in records)),
        "average_latency_seconds": sum(r["latency_seconds"] for r in records) / total if total else 0.0,
    }


def gate_check(report: dict) -> dict:
    """Map a summary report onto Gate 1/2 pass/fail.  Gate 3 needs a second run."""
    invalid_rate = (report["empty_final_response_count"] + report["fallback_count"]) / report["dataset_size"]
    checks = {
        "gate1_nonempty_100pct": report["nonempty_final_response_rate"] == 1.0,
        "gate1_total_calls_le_224": report["total_model_calls"] <= MAX_TOTAL_CALLS,
        "gate1_avg_calls_le_1.5": report["average_model_calls"] <= MAX_AVG_CALLS,
        "gate1_invalid_le_2pct": invalid_rate <= MAX_INVALID_RATE,
        "gate2_length_le_20pct": report["main_finish_reason_length_rate"] <= LENGTH_HARD_CAP,
        "gate2_length_target_10pct": report["main_finish_reason_length_rate"] <= LENGTH_TARGET,
        "gate2_marker_coverage_ge_95pct": report["answer_marker_coverage"] >= MARKER_COVERAGE_TARGET,
    }
    return {
        "checks": checks,
        "gate1_passed": all(checks[k] for k in ("gate1_nonempty_100pct", "gate1_total_calls_le_224", "gate1_avg_calls_le_1.5", "gate1_invalid_le_2pct")),
        "gate2_passed": checks["gate2_length_le_20pct"] and checks["gate2_marker_coverage_ge_95pct"],
        "invalid_rate": invalid_rate,
    }


def run_tier(token: int, items: list[dict], timeout: int, retry: int, workers: int) -> dict:
    def work(item):
        client, agent = _worker_agent(token, timeout, retry)
        return solve_one(agent, client, item)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        records = list(ex.map(work, items))
    report = summarize(records)
    report["token"] = token
    report["gate"] = gate_check(report)
    report["records"] = records
    return report


def fmt(report: dict) -> str:
    return (
        f"token={report['token']:>4} "
        f"len={report['main_finish_reason_length_rate']*100:5.1f}% "
        f"marker={report['answer_marker_coverage']*100:5.1f}% "
        f"nonempty={report['nonempty_final_response_rate']*100:5.1f}% "
        f"calls={report['average_model_calls']:.2f}(p95={report['p95_model_calls']:.0f}) "
        f"total={report['total_model_calls']} "
        f"acc={report['accuracy']*100:4.1f}% "
        f"lat={report['average_latency_seconds']:.1f}s "
        f"G1={report['gate']['gate1_passed']} G2={report['gate']['gate2_passed']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0.1 token ladder experiment.")
    parser.add_argument("--input-file", default="sample_data/public_regression_112.jsonl")
    parser.add_argument("--tokens", default=",".join(str(t) for t in DEFAULT_TOKENS),
                        help="Comma-separated token caps to scan.")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--output-file", help="JSON path for reports (rewritten after each tier).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = load_items(Path(args.input_file))
    tokens = [int(t) for t in args.tokens.split(",") if t.strip()]
    reports = []
    print(f"token ladder on {len(items)} items | tokens={tokens} | workers={args.workers} | timeout={args.timeout_seconds}s retry={args.retry_count}")
    for token in tokens:
        report = run_tier(token, items, args.timeout_seconds, args.retry_count, args.workers)
        reports.append(report)
        print(f"[tier] {fmt(report)}")
        if args.output_file:
            # ponytail: rewrite the whole file each tier so a crash keeps prior tiers.
            Path(args.output_file).write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_file:
        print(f"[done] reports -> {args.output_file}")


if __name__ == "__main__":
    main()
