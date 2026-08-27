"""Independent A/B runner for the output-protocol experiments.

The variants deliberately change one concern at a time:

* ``current``: b8b78aa answer-first + adaptive k5/threshold-3 C0.
* ``current_refine`` / ``current_strict`` / ``current_refine_strict``: C0
  with bounded P3 revision, strict numeric salvage, or both.
* ``baseline86``: frozen 86b66d2-style answer-only prompt, 4096 tokens.
* ``A``: numeric answer-first prompt, no parser or token change.
* ``B``: strict numeric salvage, no prompt or token change.
* ``A+B``: prompt plus salvage, still one 4096-token retry policy.
* ``A+B+6144``: A+B and a single 6144-token retry only after no answer.
* ``gated_retry``: B1 verification-gated retry at 4096 tokens.
* ``gated_retry_8k``: the explicitly named B1+8k exploration arm.

Reports contain aggregate metrics and safe per-item diagnostics only.  Raw model
responses are inspected in memory for marker/truncation rates and discarded.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from user_agent import (  # noqa: E402
    ANSWER_ONLY_POLICY_PROMPT,
    POLICY_PROMPT,
    AgentConfig,
    ReasoningAgent,
    classify_problem_type,
)
from scripts.evaluate_dev import judge_correct, load_items  # noqa: E402

MARKER_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]", re.IGNORECASE)
DEFAULT_MAX_CONSECUTIVE_FAILURES = 8
_local = threading.local()


class CircuitBreaker:
    """Abort a batch after a streak of failed solves.

    Slow service windows (2026-08-23 throttle incident, the 5-second-timeout
    public112 burn) invalidate every record they touch; tripping early keeps
    the loss to a handful of items instead of a full overnight batch.
    """

    def __init__(self, max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES):
        self.threshold = max_consecutive_failures
        self.streak = 0
        self.max_streak = 0
        self.tripped = False

    def record(self, failed: bool) -> bool:
        """Feed one solve outcome; returns whether the breaker has tripped."""
        if not self.tripped:
            if failed:
                self.streak += 1
                self.max_streak = max(self.max_streak, self.streak)
                if self.streak >= self.threshold:
                    self.tripped = True
            else:
                self.streak = 0
        return self.tripped


def _record_failed(record: dict) -> bool:
    return "model_error" in (record.get("diagnostic_reasons") or [])


def _batch_failed(result) -> bool:
    if isinstance(result, dict):
        records = [result]
    else:
        records = [pair[1] if isinstance(pair, tuple) else pair for pair in result]
    return any(_record_failed(record) for record in records)


def _solve_jobs_bounded(jobs: list, workers: int, breaker: CircuitBreaker) -> list:
    """Run zero-argument jobs with at most ``workers`` in flight.

    Stops scheduling new jobs once ``breaker`` trips but still collects
    in-flight results, so completed work survives an abort.
    """
    results: list = []
    pending: set = set()
    next_index = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while (next_index < len(jobs) or pending) and not (breaker.tripped and not pending):
            while next_index < len(jobs) and len(pending) < workers and not breaker.tripped:
                pending.add(executor.submit(jobs[next_index]))
                next_index += 1
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                result = future.result()
                results.append(result)
                breaker.record(_batch_failed(result))
    return results


def _attach_void_state(report: dict, breaker: CircuitBreaker) -> None:
    report["void"] = breaker.tripped
    report["void_reason"] = "consecutive_model_errors" if breaker.tripped else None
    report["consecutive_failures_max"] = breaker.max_streak


@dataclass(frozen=True)
class Variant:
    name: str
    numeric_prompt: bool = False
    strict_salvage: bool = False
    token_retry: bool = False
    failure_backoff: bool = False
    answer_conflict_retry: bool = False
    gated_retry: bool = False
    max_tokens_override: int | None = None
    temperature: float | None = None
    adaptive_voting: bool = False
    vote_k_max: int = 3
    vote_agree_threshold: int = 2
    use_policy_prompt: bool = False
    refine: bool = False
    failure_salvage: bool = False
    heterogeneous: bool = False


VARIANTS = {
    # C0/C1/C2/C3: b8b78aa answer_first + adaptive k5, isolated from defaults.
    "current": Variant(
        "current", numeric_prompt=True, adaptive_voting=True,
        vote_k_max=5, vote_agree_threshold=3, max_tokens_override=4096,
        use_policy_prompt=True,
    ),
    "current_refine": Variant(
        "current_refine", numeric_prompt=True, adaptive_voting=True,
        vote_k_max=5, vote_agree_threshold=3, max_tokens_override=4096,
        use_policy_prompt=True, refine=True,
    ),
    # P1 invalid-reduction arm: C0 with failure-path salvage as the only delta.
    "current_salvage": Variant(
        "current_salvage", numeric_prompt=True, adaptive_voting=True,
        vote_k_max=5, vote_agree_threshold=3, max_tokens_override=4096,
        use_policy_prompt=True, failure_salvage=True,
    ),
    # Capability arm: C0 with heterogeneous reasoners as the only delta —
    # the k5 budget splits into 1 alternative-strategy + 4 direct calls.
    "hetero_k5": Variant(
        "hetero_k5", numeric_prompt=True, adaptive_voting=True,
        vote_k_max=5, vote_agree_threshold=3, max_tokens_override=4096,
        use_policy_prompt=True, heterogeneous=True,
    ),
    "current_strict": Variant(
        "current_strict", numeric_prompt=True, strict_salvage=True,
        adaptive_voting=True, vote_k_max=5, vote_agree_threshold=3,
        max_tokens_override=4096, use_policy_prompt=True,
    ),
    "current_refine_strict": Variant(
        "current_refine_strict", numeric_prompt=True, strict_salvage=True,
        adaptive_voting=True, vote_k_max=5, vote_agree_threshold=3,
        max_tokens_override=4096, use_policy_prompt=True, refine=True,
    ),
    "baseline86": Variant("baseline86"),
    "A": Variant("A", numeric_prompt=True),
    "B": Variant("B", strict_salvage=True),
    "A+B": Variant("A+B", numeric_prompt=True, strict_salvage=True),
    "A+B+6144": Variant("A+B+6144", numeric_prompt=True, strict_salvage=True, token_retry=True),
    "failure_backoff": Variant("failure_backoff", failure_backoff=True),
    "answer_conflict_retry": Variant("answer_conflict_retry", answer_conflict_retry=True),
    "gated_retry": Variant("gated_retry", gated_retry=True),
    "gated_retry_8k": Variant("gated_retry_8k", gated_retry=True, max_tokens_override=8192),
    # Exact G from the cost-frontier proposal: C0's answer-first/policy prompt
    # family with k5 voting replaced by verification-gated retry (fail-closed,
    # at most one recovery call). GR layers refine on top for the four-arm screen.
    "exact_g": Variant(
        "exact_g", numeric_prompt=True, gated_retry=True, use_policy_prompt=True,
    ),
    "exact_g_refine": Variant(
        "exact_g_refine", numeric_prompt=True, gated_retry=True,
        use_policy_prompt=True, refine=True,
    ),
    "temperature04": Variant("temperature04", temperature=0.4),
    "temperature08": Variant("temperature08", temperature=0.8),
    "adaptive_vote": Variant("adaptive_vote", adaptive_voting=True),
    "adaptive_vote08": Variant("adaptive_vote08", adaptive_voting=True, temperature=0.8),
    "adaptive_vote_k5": Variant("adaptive_vote_k5", adaptive_voting=True, vote_k_max=5, vote_agree_threshold=3),
}


def make_config(variant: Variant, temperature: float = 0.6) -> AgentConfig:
    """Build an isolated config; the promoted default is not mutated."""
    ceiling = variant.max_tokens_override or 4096
    return AgentConfig(
        policy_sample_times=1,
        verifier_voting_times=0,
        max_tokens=ceiling,
        l0_max_tokens=ceiling,
        max_model_calls=variant.vote_k_max if variant.adaptive_voting else 2,
        policy_prompt=POLICY_PROMPT if variant.use_policy_prompt else ANSWER_ONLY_POLICY_PROMPT,
        enable_task_aware_prompt=True,
        enable_dynamic_budget=False,
        enable_l0_extended_tokens=True,
        enable_time_convergence=True,
        enable_l2_routing=False,
        enable_local_repair=False,
        enable_uncertain_repair=False,
        enable_sympy_evidence=False,
        enable_method_rag=False,
        enable_deterministic_solver=False,
        enable_numeric_answer_only_prompt=not variant.numeric_prompt,
        enable_numeric_answer_first_prompt=variant.numeric_prompt,
        enable_strict_numeric_salvage=variant.strict_salvage,
        enable_conditional_token_retry=variant.token_retry,
        conditional_retry_max_tokens=6144,
        enable_failure_retry_backoff=variant.failure_backoff,
        enable_explicit_answer_conflict_retry=variant.answer_conflict_retry,
        enable_verification_gated_retry=variant.gated_retry,
        enable_truncation_recovery_prompt=False,
        enable_adaptive_voting=variant.adaptive_voting,
        vote_k_max=variant.vote_k_max if variant.adaptive_voting else 3,
        vote_agree_threshold=variant.vote_agree_threshold if variant.adaptive_voting else 2,
        enable_step_verification=variant.refine,
        enable_step_revision=variant.refine,
        p3_call_boost=3 if variant.refine else 0,
        enable_failure_salvage=variant.failure_salvage,
        enable_heterogeneous_reasoners=variant.heterogeneous,
        policy_temperature=variant.temperature if variant.temperature is not None else temperature,
    )


def budget_summary(variant: Variant, temperature: float = 0.6) -> dict:
    """Effective budget facts for the report; mirrors make_config exactly."""
    base_calls = variant.vote_k_max if variant.adaptive_voting else 2
    p3_call_boost = 3 if variant.refine else 0
    return {
        "max_tokens": variant.max_tokens_override or 4096,
        "l0_max_tokens": variant.max_tokens_override or 4096,
        "retry_max_tokens": 6144 if variant.token_retry else (variant.max_tokens_override or 4096),
        "max_model_calls": base_calls,
        "effective_max_model_calls": base_calls + p3_call_boost,
        "numeric_prompt": variant.numeric_prompt,
        "strict_salvage": variant.strict_salvage,
        "conditional_token_retry": variant.token_retry,
        "failure_retry_backoff": variant.failure_backoff,
        "explicit_answer_conflict_retry": variant.answer_conflict_retry,
        "verification_gated_retry": variant.gated_retry,
        "truncation_recovery_prompt": False,
        "adaptive_voting": variant.adaptive_voting,
        "vote_k_max": variant.vote_k_max if variant.adaptive_voting else 0,
        "vote_agree_threshold": variant.vote_agree_threshold if variant.adaptive_voting else 0,
        "use_policy_prompt": variant.use_policy_prompt,
        "enable_step_verification": variant.refine,
        "enable_step_revision": variant.refine,
        "p3_call_boost": p3_call_boost,
        "policy_temperature": variant.temperature if variant.temperature is not None else temperature,
    }


def _get_agent(variant: Variant, timeout: int, retry: int, temperature: float):
    key = (variant.name, timeout, retry, temperature)
    if getattr(_local, "key", None) != key:
        client = InternChatClient(timeout=timeout, retry=retry)
        _local.key = key
        _local.client = client
        _local.agent = ReasoningAgent(client=client, config=make_config(variant, temperature))
    return _local.client, _local.agent


def solve_one(variant: Variant, item: dict, timeout: int, retry: int, temperature: float) -> dict:
    client, agent = _get_agent(variant, timeout, retry, temperature)
    before = len(client.finish_reasons)
    started = time.perf_counter()
    result = agent.solve(item["problem"], {"idx": item.get("idx")})
    elapsed = time.perf_counter() - started
    finish = client.finish_reasons[before:]
    tokens = client.completion_tokens[before:]
    latencies = client.latencies[before:]
    trace = result.get("trace", [])
    final = next((entry for entry in reversed(trace) if entry.get("step") == "finalize"), {})
    extracted = result.get("extracted_answer", "") or ""
    diagnostic_reasons = list(final.get("diagnostic_reasons") or [])
    final_response_nonempty = isinstance(result.get("final_response"), str) and bool(result["final_response"].strip())
    result_status = (
        "error" if "model_error" in diagnostic_reasons else
        "invalid" if final.get("status") == "fallback" or not final_response_nonempty or not extracted.strip() else
        "ok"
    )
    route = next((entry for entry in trace if entry.get("step") == "route_budget"), {})
    p3_enabled = bool(agent.config.enable_step_verification)

    def trace_status(step: str) -> str:
        entries = [entry for entry in trace if entry.get("step") == step]
        return entries[-1].get("status") if entries else ("not_run" if p3_enabled else "disabled")

    ptype = classify_problem_type(item["problem"])
    verdict = judge_correct(extracted, str(item["answer"]), ptype)
    main_raw = client.raw_contents[before] if len(client.raw_contents) > before else ""
    verification_check = next((entry for entry in trace if entry.get("step") == "verification_check"), None)
    retry_event = next((entry for entry in trace if entry.get("step") == "conditional_retry"), None)
    gate_selection = next((entry for entry in trace if entry.get("step") == "verification_gate_selection"), None)
    gate_rejected = [entry for entry in trace if entry.get("step") == "gated_retry_rejected"]
    return {
        "idx": item.get("idx"),
        "problem_type": ptype,
        "main_finish_reason": finish[0] if finish else None,
        "retry_finish_reason": finish[1] if len(finish) > 1 else None,
        "main_marker": bool(MARKER_RE.search(main_raw)),
        "retry_used": any(entry.get("step") == "conditional_retry" for entry in trace),
        "retry_reason": retry_event.get("reason") if retry_event else None,
        "gate_short_circuit": bool(verification_check) and verification_check.get("status") == "pass",
        "gate_accepted": int(gate_selection.get("accepted", 0)) if gate_selection else 0,
        "gate_rejected": len(gate_rejected),
        "gate_rejected_modes": [entry.get("mode") for entry in gate_rejected if entry.get("mode")],
        "gate_kept_originals": bool(gate_selection.get("kept_originals")) if gate_selection else False,
        "final_response_nonempty": final_response_nonempty,
        "result_status": result_status,
        "finalization_status": final.get("status"),
        "extracted_present": bool(extracted.strip()),
        "extracted_answer": extracted,
        "verdict": verdict,
        "model_calls": final.get("model_calls", 0),
        "model_call_limit": route.get("max_model_calls"),
        "p3_verify_status": trace_status("verify"),
        "p3_revise_status": trace_status("revise"),
        "p3_reverify_status": trace_status("reverify"),
        "main_completion_tokens": tokens[0] if tokens else 0,
        "retry_completion_tokens": tokens[1] if len(tokens) > 1 else 0,
        "total_completion_tokens": sum(tokens),
        "latency_seconds": round(elapsed, 3),
        "main_latency_seconds": round(latencies[0], 3) if latencies else None,
        "retry_latency_seconds": round(latencies[1], 3) if len(latencies) > 1 else None,
        "diagnostic_reasons": diagnostic_reasons,
    }


def summarize_records(records: list[dict]) -> dict:
    total = len(records)
    verdicts = Counter(record.get("verdict", "unknown") for record in records)
    diagnostics = Counter(reason for record in records for reason in record.get("diagnostic_reasons", []))
    calls = [record["model_calls"] for record in records]
    latencies = sorted(record["latency_seconds"] for record in records)
    tokens = [record["total_completion_tokens"] for record in records]
    main_finish = [record["main_finish_reason"] for record in records if record["main_finish_reason"]]
    invalid = sum(
        record.get("result_status") == "invalid"
        or ("result_status" not in record and (record["finalization_status"] == "fallback" or not record["extracted_present"]))
        for record in records
    )
    result_statuses = Counter(record.get("result_status", "unknown") for record in records)

    def p95(values: list[float | int]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        return ordered[max(min(int(len(ordered) * 0.95 + 0.999) - 1, len(ordered) - 1), 0)]

    return {
        "dataset_size": total,
        "verdict_counts": dict(verdicts),
        "correct": verdicts.get("correct", 0),
        "incorrect": verdicts.get("incorrect", 0),
        "invalid": invalid,
        "error": result_statuses.get("error", 0),
        "result_status_counts": dict(result_statuses),
        "accuracy": verdicts.get("correct", 0) / total if total else 0.0,
        "final_response_nonempty_rate": sum(r["final_response_nonempty"] for r in records) / total if total else 0.0,
        "main_length_rate": sum(reason == "length" for reason in main_finish) / len(main_finish) if main_finish else 0.0,
        "main_marker_rate": sum(r["main_marker"] for r in records) / total if total else 0.0,
        "retry_count": sum(r["retry_used"] for r in records),
        "retry_reason_counts": dict(Counter(r.get("retry_reason") for r in records if r.get("retry_reason"))),
        "gate_short_circuit_count": sum(bool(r.get("gate_short_circuit")) for r in records),
        "gate_accepted_count": sum(int(r.get("gate_accepted") or 0) for r in records),
        "gate_rejected_count": sum(int(r.get("gate_rejected") or 0) for r in records),
        "gate_rejected_mode_counts": dict(Counter(
            mode for record in records for mode in record.get("gate_rejected_modes", [])
        )),
        "gate_kept_originals_count": sum(bool(r.get("gate_kept_originals")) for r in records),
        "average_model_calls": sum(calls) / total if total else 0.0,
        "p95_model_calls": p95(calls),
        "max_model_calls": max(calls, default=0),
        "average_completion_tokens": sum(tokens) / total if total else 0.0,
        "p95_completion_tokens": p95(tokens),
        "average_latency_seconds": sum(r["latency_seconds"] for r in records) / total if total else 0.0,
        "p95_latency_seconds": p95(latencies),
        "diagnostic_reason_counts": dict(diagnostics),
        "p3_verify_status_counts": dict(Counter(record.get("p3_verify_status", "unknown") for record in records)),
        "p3_revise_status_counts": dict(Counter(record.get("p3_revise_status", "unknown") for record in records)),
        "p3_reverify_status_counts": dict(Counter(record.get("p3_reverify_status", "unknown") for record in records)),
    }


def run_variant(variant: Variant, items: list[dict], timeout: int, retry: int, workers: int, temperature: float,
                save_answers_to: str | None = None, round_no: int | None = None, input_file: str | None = None,
                breaker: CircuitBreaker | None = None, solve_fn=None) -> dict:
    solve = solve_fn or (lambda item: solve_one(variant, item, timeout, retry, temperature))
    local_breaker = breaker or CircuitBreaker()
    jobs = [(lambda item=item: solve(item)) for item in items]
    records = _solve_jobs_bounded(jobs, workers, local_breaker)
    report = summarize_records(records)
    report["variant"] = variant.name
    report["items"] = records
    _attach_void_state(report, local_breaker)
    if save_answers_to and round_no is not None and input_file:
        append_answers(Path(save_answers_to), answer_rows(variant.name, round_no, input_file, records))
    report["budget_config"] = budget_summary(variant, temperature)
    return report


def answer_rows(variant_name: str, round_no: int, input_file: str, records: list[dict]) -> list[dict]:
    """Compact per-item rows for offline paired re-judging (no raw model text)."""
    rows = []
    for record in records:
        row = {
            "input_file": input_file,
            "round": round_no,
            "variant": variant_name,
            "idx": record.get("idx"),
            "extracted_answer": record.get("extracted_answer", ""),
            "verdict": record.get("verdict", "unknown"),
            "diagnostic_reasons": record.get("diagnostic_reasons", []),
            "latency_seconds": record.get("latency_seconds"),
            "main_finish_reason": record.get("main_finish_reason"),
        }
        for key in (
            "final_response_nonempty", "result_status", "model_calls", "model_call_limit",
            "p3_verify_status", "p3_revise_status", "p3_reverify_status",
        ):
            if key in record:
                row[key] = record[key]
        rows.append(row)
    return rows


def append_answers(path, rows: list[dict]) -> None:
    """Append JSONL rows atomically: rewrite existing+new through a temp file."""
    from json import dumps, loads

    path = Path(path)
    existing: list[str] = []
    if path.exists():
        existing = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    new_lines = [dumps(row, ensure_ascii=False) for row in rows]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(existing + new_lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def _interleave_order(index: int, variants: list[Variant]) -> list[Variant]:
    """Rotate which arm goes first per item so no arm owns an order bias."""
    offset = index % len(variants)
    return variants[offset:] + variants[:offset]


def run_interleaved(variants: list[Variant], items: list[dict], timeout: int, retry: int,
                    workers: int, temperature: float,
                    save_answers_to: str | None = None, round_no: int | None = None,
                    input_file: str | None = None, breaker: CircuitBreaker | None = None,
                    solve_fn=None) -> list[dict]:
    """Solve every arm back-to-back for each item (same-window pairing).

    Per-item temporal adjacency plus rotating first-arm order removes the
    window drift that invalidated cross-window comparisons on 2026-08-22.
    """
    if len(variants) < 2:
        raise SystemExit("--interleave-items needs at least two variants")
    if solve_fn is None:
        def solve_fn(variant: Variant, item: dict) -> dict:
            return solve_one(variant, item, timeout, retry, temperature)

    local_breaker = breaker or CircuitBreaker()
    records_by_variant: dict[str, list[dict]] = {variant.name: [] for variant in variants}

    def work(packed):
        index, item = packed
        return [(v.name, solve_fn(v, item)) for v in _interleave_order(index, variants)]

    jobs = [(lambda packed=packed: work(packed)) for packed in enumerate(items)]
    for solved in _solve_jobs_bounded(jobs, workers, local_breaker):
        for name, record in solved:
            records_by_variant[name].append(record)

    reports = []
    for variant in variants:
        records = records_by_variant[variant.name]
        report = summarize_records(records)
        report["variant"] = variant.name
        report["items"] = records
        report["budget_config"] = budget_summary(variant, temperature)
        report["interleaved"] = True
        _attach_void_state(report, local_breaker)
        if save_answers_to and round_no is not None and input_file:
            append_answers(Path(save_answers_to), answer_rows(variant.name, round_no, input_file, records))
        reports.append(report)
    return reports


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated output-protocol A/B experiments.")
    parser.add_argument("--input-files", nargs="+", default=[
        "sample_data/public_regression_112.jsonl",
        "sample_data/medium_capability_freeze_60.jsonl",
        "sample_data/complex_capability_freeze_48.jsonl",
    ])
    parser.add_argument("--variants", default=",".join(VARIANTS), help="Comma-separated variant names.")
    parser.add_argument("--variant", action="append", choices=sorted(VARIANTS),
                        help="Run one named variant; may be repeated.")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--round-start", type=int, default=1,
                        help="First round number to record; supports resumable single-round runs.")
    parser.add_argument("--round", action="append", type=int,
                        help="Run one numbered round; may be repeated.")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--force", action="store_true",
                        help="Allow sub-60s request timeouts for deliberate short-timeout probes.")
    parser.add_argument("--max-consecutive-failures", type=int, default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
                        help="Abort the batch after this many consecutive model_error solves.")
    parser.add_argument("--output-file")
    parser.add_argument("--save-answers-to",
                        help="Persist compact per-item answers (idx/extracted_answer/verdict) as JSONL.")
    parser.add_argument("--interleave-items", action="store_true",
                        help="With exactly two --variant arms, solve both arms per item for same-window pairing.")
    parser.add_argument("--append-output", action="store_true",
                        help="Append to an existing JSON report instead of replacing it.")
    args = parser.parse_args(argv)
    if args.variant:
        args.variants = args.variant
    if args.round:
        args.rounds = args.round
    if not 1 <= args.workers <= 3:
        parser.error("--workers must be between 1 and 3")
    if args.timeout_seconds < 60 and not args.force:
        parser.error(
            "--timeout-seconds below 60 burned whole batches in past slow-window incidents "
            "(105/112 public112 items invalid at 5s); use >=60 or pass --force deliberately."
        )
    if args.max_consecutive_failures < 1:
        parser.error("--max-consecutive-failures must be at least 1")
    return args


def write_reports(path: Path, reports: list[dict]) -> None:
    """Atomically persist completed aggregate rounds without raw model content."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    names = args.variants if isinstance(args.variants, list) else [name.strip() for name in args.variants.split(",") if name.strip()]
    unknown = [name for name in names if name not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variants: {', '.join(unknown)}")
    breaker = CircuitBreaker(args.max_consecutive_failures)
    reports = []
    if args.append_output and args.output_file and Path(args.output_file).exists():
        loaded = json.loads(Path(args.output_file).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise SystemExit("--append-output requires a JSON list report")
        reports = loaded
    for input_file in args.input_files:
        if breaker.tripped:
            break
        items = load_items(Path(input_file))
        round_numbers = args.rounds if isinstance(args.rounds, list) else range(args.round_start, args.round_start + args.rounds)
        for round_no in round_numbers:
            if args.interleave_items:
                round_reports = run_interleaved(
                    [VARIANTS[name] for name in names], items,
                    args.timeout_seconds, args.retry_count, args.workers, args.temperature,
                    save_answers_to=args.save_answers_to, round_no=round_no, input_file=input_file,
                    breaker=breaker,
                )
            else:
                round_reports = []
                for name in names:
                    if breaker.tripped:
                        break
                    report = run_variant(VARIANTS[name], items, args.timeout_seconds, args.retry_count, args.workers, args.temperature,
                                         save_answers_to=args.save_answers_to, round_no=round_no, input_file=input_file,
                                         breaker=breaker)
                    round_reports.append(report)
            for report in round_reports:
                report.update({"round": round_no, "input_file": input_file, "temperature": args.temperature})
                reports.append(report)
                print(json.dumps({k: report[k] for k in ("input_file", "round", "variant", "correct", "incorrect", "invalid", "accuracy", "main_length_rate", "retry_count", "average_model_calls", "void")}, ensure_ascii=False))
            if args.output_file:
                write_reports(Path(args.output_file), reports)
            if breaker.tripped:
                break
    if breaker.tripped:
        print(json.dumps({
            "aborted": "consecutive_model_errors",
            "consecutive_failures_max": breaker.max_streak,
            "hint": "service window looks unhealthy; re-run this batch later or lower --max-consecutive-failures",
        }, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
