"""Run a local development-set baseline without exposing answers to the agent."""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Allow both `python -m scripts.evaluate_dev` and the documented
# `python scripts/evaluate_dev.py` invocation from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from user_agent import (
    ANSWER_FIRST_POLICY_PROMPT,
    ANSWER_ONLY_POLICY_PROMPT,
    AgentConfig,
    ReasoningAgent,
    classify_problem_type,
)


SUBJECT_FAMILIES = {
    "离散数学": "离散—代数—优化", "抽象代数": "离散—代数—优化",
    "高等代数": "离散—代数—优化", "运筹学": "离散—代数—优化",
    "测度积分": "连续纯数学", "微分几何": "连续纯数学", "复分析": "连续纯数学",
    "泛函分析": "连续纯数学", "数学分析": "连续纯数学", "拓扑学": "连续纯数学",
    "数值分析": "数值—微分方程", "常微分方程": "数值—微分方程",
    "偏微分方程": "数值—微分方程", "概率论": "概率—统计",
    "随机过程": "概率—统计", "统计推断": "概率—统计", "线性回归": "概率—统计",
    "非基础及进阶课程": "通用高级",
}
EXPECTED_SUBJECT_COUNTS = {
    "离散数学": 24, "数值分析": 13, "测度积分": 11, "微分几何": 9,
    "概率论": 8, "抽象代数": 8, "随机过程": 7, "复分析": 7,
    "常微分方程": 5, "统计推断": 4, "泛函分析": 4, "线性回归": 3,
    "偏微分方程": 3, "非基础及进阶课程": 2, "高等代数": 1,
    "运筹学": 1, "数学分析": 1, "拓扑学": 1,
}


def normalize(answer: str) -> str:
    return "".join(answer.split()).rstrip("。；;.").lower()


def load_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def validate_regression_items(items: list[dict[str, Any]]) -> list[str]:
    errors = []
    if len(items) != 112:
        errors.append(f"dataset_size:{len(items)}")
    for position, item in enumerate(items):
        for field in (
            "problem", "answer", "subject", "source", "source_url",
            "source_ref", "adaptation", "verification",
        ):
            if not str(item.get(field, "")).strip():
                errors.append(f"empty_{field}:{item.get('idx', position)}")
        source_url = str(item.get("source_url", ""))
        if source_url and not source_url.startswith("https://"):
            errors.append(f"invalid_source_url:{item.get('idx', position)}")
    indexes = [item.get("idx") for item in items]
    if not all(isinstance(idx, int) for idx in indexes):
        errors.append("invalid_idx")
    elif len(set(indexes)) != len(indexes):
        errors.append("duplicate_idx")
    problems = [str(item.get("problem", "")).strip() for item in items]
    if len(set(problems)) != len(problems):
        errors.append("duplicate_problem")
    if Counter(item.get("subject") for item in items) != Counter(EXPECTED_SUBJECT_COUNTS):
        errors.append("subject_distribution_mismatch")
    return errors


def summarize_breakdown(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    result = {}
    for value in dict.fromkeys(record.get(field) for record in records):
        if value is None:
            continue
        grouped = [record for record in records if record.get(field) == value]
        correct = sum(record["correct"] for record in grouped)
        result[value] = {"count": len(grouped), "correct": correct, "accuracy": correct / len(grouped)}
    return result


def not_run_record(item: dict[str, Any]) -> dict[str, Any]:
    """Record for an item skipped because the evaluation total timeout was exhausted."""
    subject = item.get("subject")
    return {
        "idx": item.get("idx"),
        "subject": subject,
        "strategy_family": SUBJECT_FAMILIES.get(subject),
        "problem_type": classify_problem_type(item["problem"]),
        "correct": False,
        "latency_seconds": 0.0,
        "model_calls": 0,
        "finalization_status": "not_run",
        "failure_reasons": ["evaluation_total_timeout_exhausted"],
        "timed_out": True,
        "empty_response": False,
        "empty_final_response": True,
        "answer_not_extractable": False,
        "controlled_tool_calls": 0,
        "controlled_tool_supported": 0,
        "controlled_tool_refuted": 0,
        "controlled_tool_unknown": 0,
        "grouped_audit_calls": 0,
        "repair_attempts": 0,
        "l2_escalations": 0,
        "uncertain_repair_attempts": 0,
        "failed": True,
        "candidates_generated": 0,
        "candidates_rejected": 0,
        "all_candidates_rejected": False,
    }


def evaluate_item_record(agent: ReasoningAgent, item: dict[str, Any]) -> dict[str, Any]:
    """Solve one item and produce the same per-item record schema as ``evaluate``.

    The agent never receives the sample ``answer``; it is only used locally for
    scoring, matching the privacy boundary required by the competition rules.
    """
    started_at = time.perf_counter()
    result = agent.solve(item["problem"], {"idx": item.get("idx")})
    elapsed_seconds = time.perf_counter() - started_at
    final_response = result.get("final_response")
    trace = result.get("trace", [])
    final_trace = next(
        (entry for entry in reversed(trace) if entry.get("step") == "finalize"), {}
    )
    reasons = [
        entry["reason"]
        for entry in trace
        if entry.get("reason")
        and entry.get("status") in {"skipped", "rejected", "fallback", "not_run"}
    ]
    is_timeout = any("Timeout" in reason or "timeout" in reason for reason in reasons)
    is_empty = any(reason == "empty_model_response" for reason in reasons)
    answer_not_extractable = any(reason == "answer_not_extractable" for reason in reasons)
    # P0.2.1: per-item candidate generation/rejection counts from trace
    generation_steps = [entry for entry in trace if entry.get("step") == "generate_candidate"]
    candidates_generated = sum(1 for entry in generation_steps if entry.get("status") == "ok")
    candidates_rejected = sum(1 for entry in generation_steps if entry.get("status") == "rejected")
    # ponytail: all-rejected means one or more attempts, zero survivors
    all_candidates_rejected = candidates_generated == 0 and candidates_rejected > 0
    controlled_tool_calls = sum(entry.get("step") == "controlled_tool" for entry in trace)
    tool_claim_statuses = [
        entry["claim_status"]
        for entry in trace
        if entry.get("step") == "controlled_tool" and entry.get("claim_status")
    ]
    grouped_audit_calls = sum(entry.get("step") == "audit_answer_group" for entry in trace)
    repair_attempts = sum(entry.get("step") == "repair_candidate" for entry in trace)
    l2_escalations = sum(entry.get("step") == "route_budget" and entry.get("level") == "L2" for entry in trace)
    uncertain_repair_attempts = sum(entry.get("step") == "repair_candidate" and entry.get("trigger") == "uncertain_without_pass" for entry in trace)
    # A failed sampling or audit attempt is diagnostic evidence, not a failed
    # item when finalization still selected a valid answer.
    failed = final_trace.get("status") in {"fallback", "not_run"}
    subject = item.get("subject")
    return {
        "idx": item.get("idx"),
        "subject": subject,
        "strategy_family": SUBJECT_FAMILIES.get(subject),
        "problem_type": classify_problem_type(item["problem"]),
        "correct": normalize(final_response or "") == normalize(item["answer"]),
        "latency_seconds": round(elapsed_seconds, 3),
        "model_calls": final_trace.get("model_calls", 0),
        "finalization_status": final_trace.get("status"),
        "failure_reasons": reasons,
        "timed_out": is_timeout,
        "empty_response": is_empty,
        "empty_final_response": not isinstance(final_response, str) or not final_response.strip(),
        "answer_not_extractable": answer_not_extractable,
        "controlled_tool_calls": controlled_tool_calls,
        "controlled_tool_supported": tool_claim_statuses.count("SUPPORTED"),
        "controlled_tool_refuted": tool_claim_statuses.count("REFUTED"),
        "controlled_tool_unknown": tool_claim_statuses.count("UNKNOWN"),
        "grouped_audit_calls": grouped_audit_calls,
        "repair_attempts": repair_attempts,
        "l2_escalations": l2_escalations,
        "uncertain_repair_attempts": uncertain_repair_attempts,
        "failed": failed,
        "candidates_generated": candidates_generated,
        "candidates_rejected": candidates_rejected,
        "all_candidates_rejected": all_candidates_rejected,
    }


def evaluate(
    agent: ReasoningAgent,
    items: list[dict[str, Any]],
    total_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    records = []
    total_started_at = time.perf_counter()
    for item in items:
        if total_timeout_seconds is not None and time.perf_counter() - total_started_at >= total_timeout_seconds:
            records.append(not_run_record(item))
            continue
        records.append(evaluate_item_record(agent, item))

    total = len(records)
    strategy_families = summarize_breakdown(records, "strategy_family")
    subjects = summarize_breakdown(records, "subject")
    problem_types = summarize_breakdown(records, "problem_type")
    return {
        "dataset_size": total,
        "accuracy": sum(record["correct"] for record in records) / total if total else 0.0,
        "average_model_calls": (
            sum(record["model_calls"] for record in records) / total if total else 0.0
        ),
        "average_latency_seconds": (
            sum(record["latency_seconds"] for record in records) / total if total else 0.0
        ),
        "timeout_count": sum(record["timed_out"] for record in records),
        "empty_response_count": sum(record["empty_response"] for record in records),
        "empty_final_response_count": sum(record["empty_final_response"] for record in records),
        "answer_not_extractable_count": sum(record["answer_not_extractable"] for record in records),
        "answer_not_extractable_rate": (
            sum(record["answer_not_extractable"] for record in records) / total if total else 0.0
        ),
        "controlled_tool_call_count": sum(record["controlled_tool_calls"] for record in records),
        "controlled_tool_supported_count": sum(record["controlled_tool_supported"] for record in records),
        "controlled_tool_refuted_count": sum(record["controlled_tool_refuted"] for record in records),
        "controlled_tool_unknown_count": sum(record["controlled_tool_unknown"] for record in records),
        "grouped_audit_call_count": sum(record["grouped_audit_calls"] for record in records),
        "repair_attempt_count": sum(record["repair_attempts"] for record in records),
        "l2_escalation_count": sum(record["l2_escalations"] for record in records),
        "uncertain_repair_attempt_count": sum(record["uncertain_repair_attempts"] for record in records),
        "failed_item_ids": [record["idx"] for record in records if record["failed"]],
        # P0.2.1: candidate-level extraction breakdown
        "candidates_generated_total": sum(record["candidates_generated"] for record in records),
        "candidates_rejected_total": sum(record["candidates_rejected"] for record in records),
        "items_with_partial_rejection_count": sum(bool(record["answer_not_extractable"]) for record in records),
        "items_with_all_candidates_rejected_count": sum(bool(record["all_candidates_rejected"]) for record in records),
        "all_candidates_rejected_ids": [record["idx"] for record in records if record["all_candidates_rejected"]],
        "total_elapsed_seconds": round(time.perf_counter() - total_started_at, 3),
        "configured_total_timeout_seconds": total_timeout_seconds,
        "max_actual_model_calls": max((record["model_calls"] for record in records), default=0),
        "budget_config": summarize_budget_config(agent),
        "strategy_families": strategy_families,
        "strategy_family_macro_accuracy": macro_accuracy(strategy_families),
        "subjects": subjects,
        "subject_macro_accuracy": macro_accuracy(subjects),
        "problem_types": problem_types,
        "problem_type_macro_accuracy": macro_accuracy(problem_types),
        "records": records,
    }


def macro_accuracy(groups: dict[str, dict[str, Any]]) -> float:
    return sum(group["accuracy"] for group in groups.values()) / len(groups) if groups else 0.0


def within_call_cap(report: dict[str, Any]) -> bool:
    """Return True when every item's actual calls stayed within the tier hard cap.

    The agent enforces the cap internally, but this gives an auditable check that
    no exception path, answer-group count, or parse outcome produced more calls
    than the declared per-question hard limit for the tier.
    """
    cap = (report.get("budget_config") or {}).get("max_model_calls")
    if cap is None:
        return True
    return report.get("max_actual_model_calls", 0) <= cap



def summarize_budget_config(agent: ReasoningAgent) -> dict[str, Any]:
    """Expose the call-budget configuration carried by the agent, if any.

    Used by local budget scans so each report declares the tier it represents.
    Falls back to an empty dict when the agent does not expose a config (e.g. a
    test double), keeping ``evaluate`` usable without a real agent.
    """
    config = getattr(agent, "config", None)
    if config is None:
        return {}
    return {
        "policy_sample_times": getattr(config, "policy_sample_times", None),
        "max_model_calls": getattr(config, "max_model_calls", None),
        "verifier_voting_times": getattr(config, "verifier_voting_times", None),
        "max_tokens": getattr(config, "max_tokens", None),
        "max_tokens": getattr(config, "max_tokens", None),
        "l0_max_tokens": getattr(config, "l0_max_tokens", None),
        "enable_l0_extended_tokens": getattr(config, "enable_l0_extended_tokens", None),
        "enable_sympy_evidence": getattr(config, "enable_sympy_evidence", None),
        "enable_dynamic_budget": getattr(config, "enable_dynamic_budget", None),
        "enable_l2_routing": getattr(config, "enable_l2_routing", None),
        "enable_local_repair": getattr(config, "enable_local_repair", None),
        "enable_uncertain_repair": getattr(config, "enable_uncertain_repair", None),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the agent on a local development JSONL.")
    parser.add_argument("--input-file", default="sample_data/dev.jsonl")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--total-timeout-seconds", type=float)
    parser.add_argument("--enable-sympy-evidence", action="store_true")
    parser.add_argument("--enable-dynamic-budget", action="store_true")
    parser.add_argument("--enable-l0-extended-tokens", dest="enable_l0_extended_tokens", action="store_true")
    parser.add_argument("--disable-l0-extended-tokens", dest="enable_l0_extended_tokens", action="store_false")
    parser.set_defaults(enable_l0_extended_tokens=True)
    parser.add_argument("--enable-l2-routing", action="store_true")
    parser.add_argument("--enable-local-repair", action="store_true")
    parser.add_argument("--enable-uncertain-repair", action="store_true")
    parser.add_argument("--answer-only-prompt", action="store_true")
    parser.add_argument("--answer-first-prompt", action="store_true")
    parser.add_argument("--policy-sample-times", type=int, help="Number of candidate generations for the non-L0 path (budget scan).")
    parser.add_argument("--max-model-calls", type=int, help="Per-question hard cap on model calls (budget scan).")
    parser.add_argument("--max-tokens", type=int, help="Non-L0 generation max tokens (default 1024). L0 always uses l0_max_tokens=1024.")
    parser.add_argument("--validate-regression-dataset", action="store_true")
    parser.add_argument("--output-file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from llm_client import InternChatClient

        items = load_items(Path(args.input_file))
        validation_errors = validate_regression_items(items) if args.validate_regression_dataset else []
        if validation_errors:
            raise ValueError(",".join(validation_errors))
        config = AgentConfig(
            enable_sympy_evidence=args.enable_sympy_evidence,
            enable_dynamic_budget=args.enable_dynamic_budget,
            enable_l0_extended_tokens=args.enable_l0_extended_tokens,
            enable_l2_routing=args.enable_l2_routing,
            enable_local_repair=args.enable_local_repair,
            enable_uncertain_repair=args.enable_uncertain_repair,
            policy_sample_times=args.policy_sample_times if args.policy_sample_times is not None else AgentConfig.policy_sample_times,
            max_model_calls=args.max_model_calls if args.max_model_calls is not None else AgentConfig.max_model_calls,
            max_tokens=args.max_tokens if args.max_tokens is not None else AgentConfig.max_tokens,
            policy_prompt=(ANSWER_FIRST_POLICY_PROMPT if args.answer_first_prompt else (ANSWER_ONLY_POLICY_PROMPT if args.answer_only_prompt else AgentConfig.policy_prompt)),
        )
        agent = ReasoningAgent(client=InternChatClient(timeout=args.timeout_seconds, retry=args.retry_count), config=config)
        total_timeout = args.total_timeout_seconds
        if total_timeout is None:
            total_timeout = len(items) * config.max_model_calls * args.timeout_seconds * args.retry_count
        report = evaluate(agent, items, total_timeout)
        report["within_call_cap"] = within_call_cap(report)
        report["status"] = "ok"
        report["sympy_evidence_enabled"] = args.enable_sympy_evidence
        report["dynamic_budget_enabled"] = args.enable_dynamic_budget
        report["l0_extended_tokens_enabled"] = args.enable_l0_extended_tokens
        report["l2_routing_enabled"] = args.enable_l2_routing
        report["local_repair_enabled"] = args.enable_local_repair
        report["uncertain_repair_enabled"] = args.enable_uncertain_repair
        report["answer_only_prompt_enabled"] = args.answer_only_prompt
        report["answer_first_prompt_enabled"] = args.answer_first_prompt
        report["regression_dataset_valid"] = True if args.validate_regression_dataset else None
    except Exception as exc:
        report = {
            "status": "error",
            "failure_reason": f"evaluation_setup_failed:{type(exc).__name__}",
        }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_file:
        Path(args.output_file).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
