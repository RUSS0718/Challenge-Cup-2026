"""Run a local development-set baseline without exposing answers to the agent."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow both `python -m scripts.evaluate_dev` and the documented
# `python scripts/evaluate_dev.py` invocation from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from user_agent import ANSWER_ONLY_POLICY_PROMPT, AgentConfig, ReasoningAgent


def normalize(answer: str) -> str:
    return "".join(answer.split()).rstrip("。；;.").lower()


def load_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def evaluate(
    agent: ReasoningAgent,
    items: list[dict[str, Any]],
    total_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    records = []
    total_started_at = time.perf_counter()
    for item in items:
        if total_timeout_seconds is not None and time.perf_counter() - total_started_at >= total_timeout_seconds:
            records.append({"idx": item.get("idx"), "correct": False, "latency_seconds": 0.0, "model_calls": 0, "finalization_status": "not_run", "failure_reasons": ["evaluation_total_timeout_exhausted"], "timed_out": True, "empty_response": False, "answer_not_extractable": False, "controlled_tool_calls": 0, "controlled_tool_supported": 0, "controlled_tool_refuted": 0, "controlled_tool_unknown": 0, "grouped_audit_calls": 0, "repair_attempts": 0, "l2_escalations": 0, "uncertain_repair_attempts": 0, "failed": True})
            continue
        started_at = time.perf_counter()
        result = agent.solve(item["problem"], {"idx": item.get("idx")})
        elapsed_seconds = time.perf_counter() - started_at
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
        records.append(
            {
                "idx": item.get("idx"),
                "correct": normalize(result["final_response"]) == normalize(item["answer"]),
                "latency_seconds": round(elapsed_seconds, 3),
                "model_calls": final_trace.get("model_calls", 0),
                "finalization_status": final_trace.get("status"),
                "failure_reasons": reasons,
                "timed_out": is_timeout,
                "empty_response": is_empty,
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
            }
        )

    total = len(records)
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
        "total_elapsed_seconds": round(time.perf_counter() - total_started_at, 3),
        "configured_total_timeout_seconds": total_timeout_seconds,
        "records": records,
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
    parser.add_argument("--output-file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from llm_client import InternChatClient

        items = load_items(Path(args.input_file))
        config = AgentConfig(
            enable_sympy_evidence=args.enable_sympy_evidence,
            enable_dynamic_budget=args.enable_dynamic_budget,
            enable_l0_extended_tokens=args.enable_l0_extended_tokens,
            enable_l2_routing=args.enable_l2_routing,
            enable_local_repair=args.enable_local_repair,
            enable_uncertain_repair=args.enable_uncertain_repair,
            policy_prompt=ANSWER_ONLY_POLICY_PROMPT if args.answer_only_prompt else AgentConfig.policy_prompt,
        )
        agent = ReasoningAgent(client=InternChatClient(timeout=args.timeout_seconds, retry=args.retry_count), config=config)
        total_timeout = args.total_timeout_seconds
        if total_timeout is None:
            total_timeout = len(items) * config.max_model_calls * args.timeout_seconds * args.retry_count
        report = evaluate(agent, items, total_timeout)
        report["status"] = "ok"
        report["sympy_evidence_enabled"] = args.enable_sympy_evidence
        report["dynamic_budget_enabled"] = args.enable_dynamic_budget
        report["l0_extended_tokens_enabled"] = args.enable_l0_extended_tokens
        report["l2_routing_enabled"] = args.enable_l2_routing
        report["local_repair_enabled"] = args.enable_local_repair
        report["uncertain_repair_enabled"] = args.enable_uncertain_repair
        report["answer_only_prompt_enabled"] = args.answer_only_prompt
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
