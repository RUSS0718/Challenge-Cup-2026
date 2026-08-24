"""Independent A/B runner for the output-protocol experiments.

The five variants deliberately change one concern at a time:

* ``baseline86``: frozen 86b66d2-style answer-only prompt, 4096 tokens.
* ``A``: numeric answer-first prompt, no parser or token change.
* ``B``: strict numeric salvage, no prompt or token change.
* ``A+B``: prompt plus salvage, still one 4096-token retry policy.
* ``A+B+6144``: A+B and a single 6144-token retry only after no answer.

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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from user_agent import (  # noqa: E402
    ANSWER_ONLY_POLICY_PROMPT,
    SUBMISSION_CONFIG,
    AgentConfig,
    ReasoningAgent,
    classify_problem_type,
)
from scripts.evaluate_dev import judge_correct, load_items  # noqa: E402

MARKER_RE = re.compile(r"(?:最终答案|final\s+answer|答案)\s*[:：]", re.IGNORECASE)
_local = threading.local()


@dataclass(frozen=True)
class Variant:
    name: str
    numeric_prompt: bool = False
    strict_salvage: bool = False
    token_retry: bool = False
    failure_backoff: bool = False
    answer_conflict_retry: bool = False
    temperature: float | None = None
    adaptive_voting: bool = False
    vote_k_max: int = 3
    vote_agree_threshold: int = 2
    submission_profile: bool = False
    single_call: bool = False
    vote_k: int | None = None


VARIANTS = {
    "baseline86": Variant("baseline86"),
    "A": Variant("A", numeric_prompt=True),
    "B": Variant("B", strict_salvage=True),
    "A+B": Variant("A+B", numeric_prompt=True, strict_salvage=True),
    "A+B+6144": Variant("A+B+6144", numeric_prompt=True, strict_salvage=True, token_retry=True),
    "failure_backoff": Variant("failure_backoff", failure_backoff=True),
    "answer_conflict_retry": Variant("answer_conflict_retry", answer_conflict_retry=True),
    "temperature04": Variant("temperature04", temperature=0.4),
    "temperature08": Variant("temperature08", temperature=0.8),
    "adaptive_vote": Variant("adaptive_vote", adaptive_voting=True),
    "adaptive_vote08": Variant("adaptive_vote08", adaptive_voting=True, temperature=0.8),
    "adaptive_vote_k5": Variant("adaptive_vote_k5", adaptive_voting=True, vote_k_max=5, vote_agree_threshold=3),
    "baseline8k_k2": Variant("baseline8k_k2", submission_profile=True),
    "single_8k_t0": Variant("single_8k_t0", submission_profile=True, single_call=True, temperature=0.0),
    "k3_8k": Variant("k3_8k", submission_profile=True, vote_k=3),
}


def make_config(variant: Variant, temperature: float = 0.6) -> AgentConfig:
    """Build an isolated config; the promoted default is not mutated."""
    if variant.submission_profile:
        config = SUBMISSION_CONFIG
        if variant.single_call:
            config = replace(config, enable_adaptive_voting=False, max_model_calls=1)
        elif variant.vote_k is not None:
            config = replace(config, vote_k_max=variant.vote_k, max_model_calls=variant.vote_k)
        if variant.temperature is not None:
            config = replace(config, policy_temperature=variant.temperature)
        return config
    return AgentConfig(
        max_tokens=4096,
        l0_max_tokens=4096,
        max_model_calls=variant.vote_k_max if variant.adaptive_voting else 2,
        policy_prompt=ANSWER_ONLY_POLICY_PROMPT,
        enable_task_aware_prompt=True,
        enable_numeric_answer_only_prompt=not variant.numeric_prompt,
        enable_numeric_answer_first_prompt=variant.numeric_prompt,
        enable_strict_numeric_salvage=variant.strict_salvage,
        enable_conditional_token_retry=variant.token_retry,
        conditional_retry_max_tokens=6144,
        enable_failure_retry_backoff=variant.failure_backoff,
        enable_explicit_answer_conflict_retry=variant.answer_conflict_retry,
        enable_adaptive_voting=variant.adaptive_voting,
        vote_k_max=variant.vote_k_max if variant.adaptive_voting else 3,
        vote_agree_threshold=variant.vote_agree_threshold if variant.adaptive_voting else 2,
        policy_temperature=variant.temperature if variant.temperature is not None else temperature,
    )


def budget_summary(variant: Variant, temperature: float = 0.6) -> dict:
    """Effective budget facts for the report; mirrors make_config exactly."""
    if variant.submission_profile:
        config = make_config(variant, temperature)
        return {
            "profile": "SUBMISSION_CONFIG",
            "max_tokens": config.max_tokens,
            "l0_max_tokens": config.l0_max_tokens,
            "retry_max_tokens": config.max_tokens,
            "max_model_calls": config.max_model_calls,
            "adaptive_voting": config.enable_adaptive_voting,
            "vote_k_max": config.vote_k_max if config.enable_adaptive_voting else 0,
            "policy_temperature": config.policy_temperature,
        }
    return {
        "max_tokens": 4096,
        "l0_max_tokens": 4096,
        "retry_max_tokens": 6144 if variant.token_retry else 4096,
        "max_model_calls": variant.vote_k_max if variant.adaptive_voting else 2,
        "numeric_prompt": variant.numeric_prompt,
        "strict_salvage": variant.strict_salvage,
        "conditional_token_retry": variant.token_retry,
        "failure_retry_backoff": variant.failure_backoff,
        "explicit_answer_conflict_retry": variant.answer_conflict_retry,
        "adaptive_voting": variant.adaptive_voting,
        "vote_k_max": variant.vote_k_max if variant.adaptive_voting else 0,
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
    ptype = classify_problem_type(item["problem"])
    verdict = judge_correct(extracted, str(item["answer"]), ptype)
    main_raw = client.raw_contents[before] if len(client.raw_contents) > before else ""
    return {
        "idx": item.get("idx"),
        "problem_type": ptype,
        "main_finish_reason": finish[0] if finish else None,
        "retry_finish_reason": finish[1] if len(finish) > 1 else None,
        "main_marker": bool(MARKER_RE.search(main_raw)),
        "retry_used": any(entry.get("step") == "conditional_retry" for entry in trace),
        "final_response_nonempty": isinstance(result.get("final_response"), str) and bool(result["final_response"].strip()),
        "finalization_status": final.get("status"),
        "extracted_present": bool(extracted.strip()),
        "extracted_answer": extracted,
        "verdict": verdict,
        "model_calls": final.get("model_calls", 0),
        "main_completion_tokens": tokens[0] if tokens else 0,
        "retry_completion_tokens": tokens[1] if len(tokens) > 1 else 0,
        "total_completion_tokens": sum(tokens),
        "latency_seconds": round(elapsed, 3),
        "main_latency_seconds": round(latencies[0], 3) if latencies else None,
        "retry_latency_seconds": round(latencies[1], 3) if len(latencies) > 1 else None,
        "diagnostic_reasons": list(final.get("diagnostic_reasons") or []),
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
        record["finalization_status"] == "fallback" or not record["extracted_present"]
        for record in records
    )

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
        "accuracy": verdicts.get("correct", 0) / total if total else 0.0,
        "final_response_nonempty_rate": sum(r["final_response_nonempty"] for r in records) / total if total else 0.0,
        "main_length_rate": sum(reason == "length" for reason in main_finish) / len(main_finish) if main_finish else 0.0,
        "main_marker_rate": sum(r["main_marker"] for r in records) / total if total else 0.0,
        "retry_count": sum(r["retry_used"] for r in records),
        "average_model_calls": sum(calls) / total if total else 0.0,
        "p95_model_calls": p95(calls),
        "max_model_calls": max(calls, default=0),
        "average_completion_tokens": sum(tokens) / total if total else 0.0,
        "p95_completion_tokens": p95(tokens),
        "average_latency_seconds": sum(r["latency_seconds"] for r in records) / total if total else 0.0,
        "p95_latency_seconds": p95(latencies),
        "diagnostic_reason_counts": dict(diagnostics),
    }


def run_variant(variant: Variant, items: list[dict], timeout: int, retry: int, workers: int, temperature: float,
                save_answers_to: str | None = None, round_no: int | None = None, input_file: str | None = None) -> dict:
    def work(item: dict) -> dict:
        return solve_one(variant, item, timeout, retry, temperature)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(executor.map(work, items))
    report = summarize_records(records)
    report["variant"] = variant.name
    if save_answers_to and round_no is not None and input_file:
        append_answers(Path(save_answers_to), answer_rows(variant.name, round_no, input_file, records))
    report["budget_config"] = budget_summary(variant, temperature)
    return report


def answer_rows(variant_name: str, round_no: int, input_file: str, records: list[dict]) -> list[dict]:
    """Compact per-item rows for offline paired re-judging (no raw model text)."""
    return [
        {
            "input_file": input_file,
            "round": round_no,
            "variant": variant_name,
            "idx": record.get("idx"),
            "extracted_answer": record.get("extracted_answer", ""),
            "verdict": record.get("verdict", "unknown"),
        }
        for record in records
    ]


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
                    input_file: str | None = None, solve_fn=None) -> list[dict]:
    """Solve every arm back-to-back for each item (same-window pairing).

    Per-item temporal adjacency plus rotating first-arm order removes the
    window drift that invalidated cross-window comparisons on 2026-08-22.
    """
    if len(variants) < 2:
        raise SystemExit("--interleave-items needs at least two variants")
    if solve_fn is None:
        def solve_fn(variant: Variant, item: dict) -> dict:
            return solve_one(variant, item, timeout, retry, temperature)

    records_by_variant: dict[str, list[dict]] = {variant.name: [] for variant in variants}

    def work(packed):
        index, item = packed
        return [(v.name, solve_fn(v, item)) for v in _interleave_order(index, variants)]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for solved in executor.map(work, enumerate(items)):
            for name, record in solved:
                records_by_variant[name].append(record)

    reports = []
    for variant in variants:
        records = records_by_variant[variant.name]
        report = summarize_records(records)
        report["variant"] = variant.name
        report["budget_config"] = budget_summary(variant, temperature)
        report["interleaved"] = True
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
    reports = []
    if args.append_output and args.output_file and Path(args.output_file).exists():
        loaded = json.loads(Path(args.output_file).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise SystemExit("--append-output requires a JSON list report")
        reports = loaded
    for input_file in args.input_files:
        items = load_items(Path(input_file))
        round_numbers = args.rounds if isinstance(args.rounds, list) else range(args.round_start, args.round_start + args.rounds)
        for round_no in round_numbers:
            if args.interleave_items:
                round_reports = run_interleaved(
                    [VARIANTS[name] for name in names], items,
                    args.timeout_seconds, args.retry_count, args.workers, args.temperature,
                    save_answers_to=args.save_answers_to, round_no=round_no, input_file=input_file,
                )
            else:
                round_reports = []
                for name in names:
                    report = run_variant(VARIANTS[name], items, args.timeout_seconds, args.retry_count, args.workers, args.temperature,
                                         save_answers_to=args.save_answers_to, round_no=round_no, input_file=input_file)
                    round_reports.append(report)
            for report in round_reports:
                report.update({"round": round_no, "input_file": input_file, "temperature": args.temperature})
                reports.append(report)
                print(json.dumps({k: report[k] for k in ("input_file", "round", "variant", "correct", "incorrect", "invalid", "accuracy", "main_length_rate", "retry_count", "average_model_calls")}, ensure_ascii=False))
            if args.output_file:
                write_reports(Path(args.output_file), reports)


if __name__ == "__main__":
    main()
