"""Run one bounded real-model v1.1 baseline with v1.3 host replay.

Each item receives one ordinary v1.1 ``solve`` invocation.  The candidate arm
is derived in-process from that same response by the gold-free v1.3 host
pipeline, so the experiment measures parser/incumbent recovery without adding
an unregistered model call or changing the submission profile.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from reasoning_agent.artifacts import ArtifactManager, RunContext
from reasoning_agent.grh_v13 import recover_response
from scripts.evaluate_dev import judge_correct
from scripts.external_hard_sets_judging import extract_contract_answer
from user_agent import SUBMISSION_CONFIG, SUBMISSION_MODE, ReasoningAgent, classify_problem_type


EXPECTED = 221
WORKERS = 3
REQUEST_TIMEOUT_SECONDS = 600
MAX_WALL_SECONDS = 21_600


def sha256(path: Path) -> str:
    """Hash exact bytes for the run manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_items(path: Path) -> list[dict]:
    """Load and validate the frozen 221-item input before any model call."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED or len({str(row.get("idx")) for row in rows}) != EXPECTED:
        raise ValueError("dataset_requires_221_unique_items")
    if any(not str(row.get("problem", "")).strip() or not str(row.get("answer", "")).strip() for row in rows):
        raise ValueError("dataset_requires_problem_and_local_gold")
    return rows


def _trace_stage(trace: list[dict], stage: str) -> dict:
    """Return the last compact trace stage with a given name."""
    return next((entry for entry in reversed(trace) if isinstance(entry, dict) and entry.get("stage") == stage), {})


def _compact_trace(trace: object) -> list[dict]:
    """Keep bounded diagnostics while removing raw prompt/response fields."""
    if not isinstance(trace, list):
        return []
    blocked = {"prompt", "content", "response", "solution", "problem"}
    return [{str(key): value for key, value in entry.items() if key not in blocked} for entry in trace if isinstance(entry, dict)]


def solve_one(item: dict) -> dict:
    """Run one isolated baseline solve and derive the host candidate locally."""
    started = time.monotonic()
    raw = "UNKNOWN"
    trace: list[dict] = []
    error_category = None
    try:
        client = InternChatClient(timeout=REQUEST_TIMEOUT_SECONDS, retry=1, thinking_mode=None)
        result = ReasoningAgent(client=client).solve(str(item["problem"]), {"idx": str(item["idx"])})
        raw = result.get("final_response") if isinstance(result.get("final_response"), str) else "UNKNOWN"
        trace = _compact_trace(result.get("trace", []))
    except Exception as exc:
        error_category = str(getattr(exc, "category", type(exc).__name__))

    problem_type = classify_problem_type(str(item["problem"]))
    baseline_answer = extract_contract_answer(raw)
    baseline_verdict = judge_correct(baseline_answer, str(item["answer"]), problem_type, str(item["problem"]))
    ledger = _trace_stage(trace, "evidence_ledger")
    budget = ledger.get("budget") if isinstance(ledger.get("budget"), dict) else {}
    row_for_recovery = {
        "item_id": str(item["idx"]), "final_response": raw, "verdict": baseline_verdict,
        "outcome": baseline_verdict, "candidate_count": len(ledger.get("candidates", [])) if isinstance(ledger.get("candidates"), list) else 0,
        "trace": trace, "model_error": error_category is not None,
        "timeout": any(call.get("error_category") == "timeout" for call in ledger.get("calls", []) if isinstance(call, dict)),
        "finish_reasons": [call.get("finish_reason") for call in ledger.get("calls", []) if isinstance(call, dict)],
    }
    recovered = recover_response(str(item["problem"]), raw, row_for_recovery)
    candidate = recovered.get("candidate") or {}
    candidate_answer = str(candidate.get("canonical_value") or candidate.get("value") or "")
    candidate_verdict = judge_correct(candidate_answer, str(item["answer"]), problem_type, str(item["problem"])) if candidate_answer else "unknown"
    return {
        "item_id": str(item["idx"]), "problem_type": problem_type,
        "baseline_verdict": baseline_verdict, "candidate_verdict": candidate_verdict,
        "baseline_answer": baseline_answer, "candidate_answer": candidate_answer,
        "transition": f"{baseline_verdict} → {candidate_verdict}",
        "recovery": recovered["recovery"], "verification": recovered["verification"],
        "parser_source": recovered["parser_source"], "parser_rejection": recovered["parser_rejection"],
        "model_error": error_category is not None, "error_category": error_category,
        "duration_seconds": round(time.monotonic() - started, 3),
        "model_calls": budget.get("calls") if isinstance(budget, dict) else None,
        "requested_tokens": budget.get("requested_tokens") if isinstance(budget, dict) else None,
        "finish_reasons": row_for_recovery["finish_reasons"], "trace": trace,
    }


def run(dataset: Path, output: Path) -> dict:
    """Run preflight then all 221 items, preserving every completed result."""
    if output.exists():
        raise ValueError("real_ab_output_already_exists")
    items = read_items(dataset)
    manager = ArtifactManager(output)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    context = RunContext(output.name, "grh-v13-real-host-replay", dataset.name, "configured-model", git_commit=commit)
    manager.save_manifest(context, status="running", dataset_sha256=sha256(dataset), expected_records=EXPECTED,
                          workers=WORKERS, per_item_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                          max_wall_seconds=MAX_WALL_SECONDS, max_model_calls=3,
                          max_requested_tokens=16_384, submission_mode=SUBMISSION_MODE,
                          resolved_config=asdict(SUBMISSION_CONFIG), gold_passed_to_agent=False,
                          candidate_calls_added=0, experiment="P1_REAL_MODEL_HOST_REPLAY")
    preflight: list[dict] = []
    probe_client = InternChatClient(timeout=30, retry=1, thinking_mode=None)
    for index in range(3):
        started = time.monotonic()
        try:
            response = probe_client.chat([{"role": "user", "content": "Calculate 1+1. Final answer only."}], temperature=0, max_tokens=32, reasoning_mode="off", timeout_seconds=30)
            preflight.append({"probe": index + 1, "pass": extract_contract_answer(response) == "2", "seconds": round(time.monotonic() - started, 3)})
        except Exception as exc:
            preflight.append({"probe": index + 1, "pass": False, "error_category": str(getattr(exc, "category", type(exc).__name__)), "seconds": round(time.monotonic() - started, 3)})
    manager.save_json("preflight.json", preflight)
    if not all(row["pass"] for row in preflight):
        report = {"disposition": "VOID_PREFLIGHT", "records": 0, "expected_records": EXPECTED, "preflight": preflight, "remote_model_calls": len(preflight), "capability_conclusion": "NONE"}
        manager.save_report(report)
        manager.save_manifest(context, status="completed", disposition=report["disposition"], records=0, remote_model_calls=len(preflight))
        return report

    started = time.monotonic()
    rows: list[dict] = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pending = {pool.submit(solve_one, item): item for item in items}
        while pending:
            done, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = {"item_id": str(item["idx"]), "baseline_verdict": "unknown", "candidate_verdict": "unknown", "transition": "unknown → unknown", "model_error": True, "error_category": "runner_" + type(exc).__name__, "duration_seconds": None, "model_calls": None, "requested_tokens": None, "finish_reasons": [], "trace": [], "recovery": {"action": "unknown"}, "verification": {"status": "unknown"}, "parser_source": "none", "parser_rejection": "runner_error", "baseline_answer": "", "candidate_answer": "", "problem_type": "unknown"}
                with lock:
                    rows.append(row)
                    manager.append_answer(row)
                    print(f"completed={len(rows)}/{EXPECTED} item={row['item_id']} baseline={row['baseline_verdict']} candidate={row['candidate_verdict']} transition={row['transition']}", flush=True)
            if time.monotonic() - started > MAX_WALL_SECONDS:
                for future in pending:
                    future.cancel()
                break
    transitions = Counter(row["transition"] for row in rows)
    report = {
        "disposition": "REAL_MODEL_HOST_REPLAY_COMPLETE" if len(rows) == EXPECTED else "REAL_MODEL_HOST_REPLAY_INCOMPLETE",
        "records": len(rows), "expected_records": EXPECTED, "preflight": preflight,
        "baseline_verdicts": dict(Counter(row["baseline_verdict"] for row in rows)),
        "candidate_verdicts": dict(Counter(row["candidate_verdict"] for row in rows)),
        "transitions": dict(transitions),
        "invalid_rescue": transitions.get("unknown → correct", 0),
        "invalid_damage": transitions.get("unknown → incorrect", 0),
        "correct_damage": transitions.get("correct → incorrect", 0) + transitions.get("correct → unknown", 0),
        "net_correct_gain": transitions.get("unknown → correct", 0) - transitions.get("correct → unknown", 0) - transitions.get("correct → incorrect", 0),
        "model_errors": sum(bool(row.get("model_error")) for row in rows),
        "average_model_calls": sum(row["model_calls"] for row in rows if isinstance(row.get("model_calls"), int)) / max(1, sum(isinstance(row.get("model_calls"), int) for row in rows)),
        "remote_model_calls": len(preflight) + sum(row["model_calls"] for row in rows if isinstance(row.get("model_calls"), int)),
        "gold_passed_to_agent": False, "candidate_calls_added": 0, "capability_conclusion": "NONE",
    }
    manager.save_report(report)
    manager.save_manifest(context, status="completed", records=len(rows), remote_model_calls=report["remote_model_calls"], disposition=report["disposition"], report_sha256=sha256(output / "report.json"))
    return report


def main() -> None:
    """Require explicit dataset and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
