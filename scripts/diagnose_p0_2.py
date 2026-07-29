"""P0.2.2: Per-item attribution for idx 9-22 under default 3-candidate path.

Produces per-item diagnostics distinguishing "model didn't produce a valid answer"
from "code lost a valid answer". Includes a 1024-token contrast call to detect
whether truncation is the root cause.

Totals: at most 14 * 6 + 14 = 98 calls. All raw model text is excluded from
the JSON report.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_dev import load_items, normalize
from user_agent import POLICY_PROMPT, AgentConfig, ReasoningAgent


def classify_item_failure(
    record: dict[str, Any],
    contrast_1024: dict[str, Any] | None,
) -> dict[str, str]:
    """Per-item attribution using agent trace + 1024-token contrast call."""
    basis_parts = []
    category = "unknown"

    generated = record["candidates_generated"]
    rejected = record["candidates_rejected"]
    all_rejected = record["all_candidates_rejected"]

    if all_rejected:
        category = "all_candidates_rejected"
        if rejected >= 2:
            basis_parts.append(f"All {rejected} candidates rejected; zero survived agent extraction.")
        else:
            basis_parts.append(f"Single candidate rejected; no candidate survived.")
    elif rejected > 0:
        category = "partial_rejection"
        basis_parts.append(f"{rejected}/{generated + rejected} candidates rejected; {generated} survived.")

    if contrast_1024:
        contrast_correct = contrast_1024.get("correct", False)
        contrast_category = contrast_1024.get("failure_category", "?")
        contrast_chars = contrast_1024.get("response_characters", 0)

        if contrast_correct:
            basis_parts.append(
                f"1024-token single call produced correct answer ({contrast_chars} chars). "
                "Evidence: model CAN solve this with enough output budget."
            )
        elif contrast_category == "format_placeholder_echo":
            basis_parts.append(
                f"1024-token call still produced placeholder echo ({contrast_chars} chars). "
                "Evidence: even 1024 tokens is insufficient OR prompt format is confusing the model."
            )
        elif contrast_category == "missing_final_marker":
            basis_parts.append(
                f"1024-token call missing final marker ({contrast_chars} chars). "
                "Evidence: model output still truncated even at 1024 tokens."
            )
        elif contrast_category == "incorrect_final_answer":
            basis_parts.append(
                f"1024-token call produced explicit but wrong answer ({contrast_chars} chars). "
                "Evidence: model has a solving error, not just output truncation."
            )
    else:
        basis_parts.append("No 1024-token contrast available.")

    # Distinguish model failure from code failure
    if all_rejected and contrast_1024 and contrast_1024.get("correct"):
        failure_type = "model_output_sufficient_but_agent_pipeline_lost_it"
    elif all_rejected:
        failure_type = "model_output_insufficient_under_256_tokens"
    elif record.get("correct", False):
        failure_type = "correct_final_answer"
    else:
        failure_type = "model_wrong_or_extraction_captured_noise"

    return {
        "category": category,
        "failure_type": failure_type,
        "basis": " ".join(basis_parts),
    }


def single_call_diagnose(client: Any, item: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """One raw model call, classified locally. Raw text excluded from output."""
    try:
        response = client.chat(
            messages=[
                {"role": "system", "content": POLICY_PROMPT},
                {"role": "user", "content": f"题目：\n{item['problem']}\n\n请给出完整解答。候选编号：0"},
            ],
            temperature=0.6,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        return {
            "correct": False,
            "failure_category": f"request_error:{getattr(exc, 'category', type(exc).__name__)}",
            "answer_extracted": "",
            "has_final_marker": False,
            "response_characters": 0,
        }
    from user_agent import extract_final_answer, is_placeholder_answer
    import re

    answer = extract_final_answer(response or "")
    marker_values = re.findall(r"(?:最终答案|final\s+answer)\s*[:：]\s*([^\n\r]+)", response or "", re.IGNORECASE)
    has_final_marker = bool(marker_values)
    correct = normalize(answer) == normalize(item["answer"])

    if correct:
        category = "correct"
    elif has_final_marker and any(is_placeholder_answer(v) for v in marker_values):
        category = "format_placeholder_echo"
    elif not has_final_marker:
        category = "missing_final_marker"
    else:
        category = "incorrect_final_answer"

    return {
        "correct": correct,
        "failure_category": category,
        "answer_extracted": answer,
        "has_final_marker": has_final_marker,
        "response_characters": len(response or ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P0.2.2 per-item attribution for idx 9-22.")
    parser.add_argument("--input-file", default="sample_data/dev.jsonl")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    from llm_client import InternChatClient

    items = load_items(Path(args.input_file))
    target_items = [item for item in items if 9 <= item.get("idx", -1) <= 22]

    config = AgentConfig(
        policy_sample_times=3,
        max_model_calls=6,
        max_tokens=256,
        enable_l0_extended_tokens=True,
    )
    client = InternChatClient(timeout=args.timeout_seconds, retry=args.retry_count)
    agent = ReasoningAgent(client=client, config=config)

    records = []
    for item in target_items:
        idx = item["idx"]
        started = time.perf_counter()

        # 1. Agent solve with default 3-candidate path
        result = agent.solve(item["problem"], {"idx": idx})
        elapsed = round(time.perf_counter() - started, 3)
        trace = result.get("trace", [])
        final_trace = next((e for e in reversed(trace) if e.get("step") == "finalize"), {})
        final_response = result.get("final_response", "")
        generation_steps = [e for e in trace if e.get("step") == "generate_candidate"]
        generated = sum(1 for e in generation_steps if e.get("status") == "ok")
        rejected = sum(1 for e in generation_steps if e.get("status") == "rejected")
        all_rejected = generated == 0 and rejected > 0
        failure_reasons = [
            e["reason"] for e in trace
            if e.get("reason") and e.get("status") in {"skipped", "rejected", "fallback"}
        ]

        # 2. Single 1024-token contrast call
        contrast_1024 = single_call_diagnose(client, item, max_tokens=1024)

        # 3. Attribution
        record = {
            "idx": idx,
            "subject": item["subject"],
            "correct": normalize(final_response) == normalize(item["answer"]),
            "final_response": final_response,
            "finalization_status": final_trace.get("status"),
            "latency_seconds": elapsed,
            "model_calls": final_trace.get("model_calls", 0),
            "candidates_generated": generated,
            "candidates_rejected": rejected,
            "all_candidates_rejected": all_rejected,
            "failure_reasons": failure_reasons,
            "contrast_1024": contrast_1024,
        }
        attribution = classify_item_failure(record, contrast_1024)
        record.update(attribution)
        records.append(record)

    # Summary
    by_failure_type = {}
    for r in records:
        ft = r["failure_type"]
        by_failure_type[ft] = by_failure_type.get(ft, 0) + 1

    report = {
        "dataset_size": len(records),
        "idx_range": "9-22",
        "agent_config": {
            "policy_sample_times": config.policy_sample_times,
            "max_model_calls": config.max_model_calls,
            "max_tokens": config.max_tokens,
            "l0_max_tokens": config.l0_max_tokens,
        },
        "failure_type_counts": by_failure_type,
        "correct_count": sum(1 for r in records if r["correct"]),
        "has_contrast_1024": True,
        "raw_model_output_included": False,
        "records": records,
    }
    Path(args.output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report saved to {args.output_file}")
    print(f"  Failure types: {by_failure_type}")
    print(f"  Correct: {sum(1 for r in records if r['correct'])}/{len(records)}")


if __name__ == "__main__":
    main()
