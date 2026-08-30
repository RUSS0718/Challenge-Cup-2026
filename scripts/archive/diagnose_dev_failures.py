"""Classify one UTF-8 model response per local development item.

This is a local diagnostic only.  It never passes sample answers to the agent
or model, and it excludes raw model text from the JSON report by default.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.evaluate_dev import load_items, normalize
from user_agent import POLICY_PROMPT, extract_final_answer, is_placeholder_answer


def classify_response(response: str | None, expected_answer: str, error: str | None = None) -> dict[str, Any]:
    """Return a compact local-only diagnosis without preserving model text."""
    if error:
        return {
            "correct": False,
            "failure_category": f"request_error:{error}",
            "basis": "The local client request failed before any answer was returned.",
            "answer_extracted": "",
            "has_final_marker": False,
            "starts_thinking_process": False,
            "response_characters": 0,
        }

    response = response or ""
    answer = extract_final_answer(response)
    marker_values = re.findall(r"(?:最终答案|final\s+answer)\s*[:：]\s*([^\n\r]+)", response, re.IGNORECASE)
    has_final_marker = bool(marker_values)
    correct = normalize(answer) == normalize(expected_answer)
    if correct:
        category = "correct"
        basis = "The extracted final answer matches the local scoring answer after normalization."
    elif has_final_marker and any(is_placeholder_answer(value) for value in marker_values):
        category = "format_placeholder_echo"
        basis = "The response repeats an output-format placeholder instead of supplying a mathematical answer."
    elif not has_final_marker:
        category = "missing_final_marker"
        basis = "The response contains no explicit final-answer marker, so the requested answer was not produced."
    else:
        category = "incorrect_final_answer"
        basis = "An explicit final answer was extracted, but it differs from the local scoring answer."
    return {
        "correct": correct,
        "failure_category": category,
        "basis": basis,
        "answer_extracted": answer,
        "has_final_marker": has_final_marker,
        "starts_thinking_process": response.lstrip().lower().startswith("thinking process:"),
        "response_characters": len(response),
    }


def diagnose(client: Any, items: list[dict[str, Any]], max_tokens: int = 256) -> dict[str, Any]:
    records = []
    for item in items:
        try:
            response = client.chat(
                messages=[
                    {"role": "system", "content": POLICY_PROMPT},
                    {"role": "user", "content": f"题目：\n{item['problem']}\n\n请给出完整解答。候选编号：0"},
                ],
                temperature=0.6,
                max_tokens=max_tokens,
            )
            diagnosis = classify_response(response, item["answer"])
        except Exception as exc:
            diagnosis = classify_response(None, item["answer"], getattr(exc, "category", type(exc).__name__))
        records.append({"idx": item.get("idx"), "subject": item.get("subject"), **diagnosis})
    categories = {
        category: sum(record["failure_category"] == category for record in records)
        for category in sorted({record["failure_category"] for record in records})
    }
    return {
        "dataset_size": len(records),
        "max_tokens": max_tokens,
        "raw_model_output_included": False,
        "category_counts": categories,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose local development-set output failures.")
    parser.add_argument("--input-file", default="sample_data/dev.jsonl")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    from llm_client import InternChatClient

    report = diagnose(
        InternChatClient(timeout=args.timeout_seconds, retry=args.retry_count),
        load_items(Path(args.input_file)),
        args.max_tokens,
    )
    Path(args.output_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
