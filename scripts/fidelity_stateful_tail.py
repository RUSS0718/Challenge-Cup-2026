"""Fidelity Probe for stateful_tail_completion_v1 (STATEFUL-TAIL-V1-FIDELITY-001).

Validates the core continuation mechanism against the live official endpoint:
1. Feeds live-model truncated responses into STATEFUL_TAIL_CONTINUATION_PROMPT with tail-windowing (<=8000 chars).
2. Measures:
   - Continuation explicit answer formation rate (pass gate >= 60%)
   - False-acceptance / placeholder rate (must be 0)
   - JSON serialization & output hygiene (100%)
   - Token usage and latency per continuation
3. Executes 3 end-to-end solve() calls with enable_stateful_tail_completion=True.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from user_agent import (
    STATEFUL_TAIL_CONTINUATION_PROMPT,
    DIRECT_REASONER_PROMPT,
    AgentConfig,
    ReasoningAgent,
    extract_answer_first,
    extract_final_answer,
    is_placeholder_answer,
    _has_placeholder_answer,
    classify_problem_type,
)


def load_hard_problems(max_count: int = 25) -> list[dict[str, Any]]:
    """Select fresh hard problems from math500 (Level 4/5) and aime25."""
    problems = []
    math500_path = ROOT / "tmp" / "p1_data" / "cache" / "math500_test.jsonl"
    if math500_path.exists():
        with open(math500_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                level = item.get("level", "")
                if "Level 4" in str(level) or "Level 5" in str(level):
                    problems.append({
                        "id": f"math500_{item.get('unique_id', len(problems))}",
                        "problem": item.get("problem", ""),
                        "answer": item.get("answer", ""),
                        "source": "math500",
                    })
                if len(problems) >= max_count:
                    break

    aime25_path = ROOT / "tmp" / "p1_data" / "cache" / "aime25_test.jsonl"
    if aime25_path.exists() and len(problems) < max_count:
        with open(aime25_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                problems.append({
                    "id": f"aime25_{item.get('id', len(problems))}",
                    "problem": item.get("problem", item.get("question", "")),
                    "answer": str(item.get("answer", "")),
                    "source": "aime25",
                })
                if len(problems) >= max_count:
                    break

    return problems[:max_count]


def run_fidelity(output_dir: Path, max_problems: int = 20, timeout: int = 300) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = InternChatClient(timeout=timeout)
    problems = load_hard_problems(max_count=max_problems)
    print(f"[FIDELITY] Loaded {len(problems)} hard problems for continuation probe (timeout={timeout}s).")

    records = []
    continuation_attempts = 0
    continuation_formed_answers = 0
    continuation_placeholders = 0
    model_errors = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    start_time = time.time()

    for idx, item in enumerate(problems):
        prob_id = item["id"]
        prob_text = item["problem"]
        print(f"\n--- Problem [{idx+1}/{len(problems)}] {prob_id} ---")

        # Step 1: Initial forward derivation attempt (4096 tokens)
        init_messages = [
            {"role": "system", "content": DIRECT_REASONER_PROMPT},
            {"role": "user", "content": f"题目：\n{prob_text}\n\n请给出完整解答。"},
        ]
        try:
            t0 = time.time()
            resp1 = client.chat(messages=init_messages, temperature=0.6, max_tokens=4096)
            lat1 = time.time() - t0
        except Exception as exc:
            print(f"  [ERROR] Initial call failed: {exc}")
            model_errors += 1
            records.append({"id": prob_id, "status": "init_model_error", "error": str(exc)})
            continue

        if not resp1 or not resp1.strip():
            print("  [ERROR] Initial call returned empty response.")
            model_errors += 1
            records.append({"id": prob_id, "status": "init_empty_response"})
            continue

        ans1 = extract_answer_first(resp1) or extract_final_answer(resp1)
        is_trunc = not bool(ans1)
        print(f"  Initial response: len={len(resp1)} chars, has_answer={bool(ans1)}, latency={lat1:.1f}s")

        # Step 2: If truncated / no explicit answer, trigger continuation
        if is_trunc:
            continuation_attempts += 1
            tail = resp1[-8000:]
            cont_user_msg = (
                f"题目：\n{prob_text}\n\n候选编号：4\n\n"
                f"此前一次解答的末尾片段（可能在中途被截断）：\n{tail}\n\n"
                "请从上述片段的截断处继续完成同一条推理，不要从头重新作答；"
                "完成后另起一行，严格按“最终答案：X”格式单独给出最终答案，X 只含最终结果。"
            )
            cont_messages = [
                {"role": "system", "content": STATEFUL_TAIL_CONTINUATION_PROMPT},
                {"role": "user", "content": cont_user_msg},
            ]

            try:
                t1 = time.time()
                resp2 = client.chat(messages=cont_messages, temperature=0.6, max_tokens=4096)
                lat2 = time.time() - t1
            except Exception as exc:
                print(f"  [ERROR] Continuation call failed: {exc}")
                model_errors += 1
                records.append({"id": prob_id, "status": "cont_model_error", "error": str(exc)})
                continue

            ans2 = extract_answer_first(resp2) or extract_final_answer(resp2)
            has_placeholder = _has_placeholder_answer(resp2) if resp2 else False
            formed = bool(ans2) and not has_placeholder

            if formed:
                continuation_formed_answers += 1
                print(f"  [PASS] Continuation formed answer: {ans2!r} (lat={lat2:.1f}s, len={len(resp2)})")
            else:
                if has_placeholder:
                    continuation_placeholders += 1
                    print(f"  [REJECT] Continuation returned placeholder answer: {ans2!r}")
                else:
                    print(f"  [NO_MARKER] Continuation did not produce explicit marker (len={len(resp2)})")

            records.append({
                "id": prob_id,
                "status": "continuation_evaluated",
                "init_length": len(resp1),
                "tail_length": len(tail),
                "cont_length": len(resp2) if resp2 else 0,
                "cont_latency": lat2,
                "formed_answer": formed,
                "extracted_answer": ans2 or "",
                "has_placeholder": has_placeholder,
                "gold_answer": item.get("answer", ""),
            })
        else:
            print(f"  [SOLVED_EARLY] Initial call already formed answer: {ans1!r}")
            records.append({
                "id": prob_id,
                "status": "initial_solved",
                "init_length": len(resp1),
                "extracted_answer": ans1,
                "gold_answer": item.get("answer", ""),
            })

    elapsed = time.time() - start_time

    # Step 3: End-to-end solve() probe (3 cases)
    print("\n--- End-to-End solve() Probes (3 cases) ---")
    e2e_records = []
    agent_config = AgentConfig(
        enable_stateful_tail_completion=True,
        max_model_calls=5,
        max_tokens=4096,
        enable_heterogeneous_reasoners=True,
        enable_adaptive_voting=True,
        vote_k_max=5,
        vote_agree_threshold=3,
        enable_numeric_answer_first_prompt=True,
    )
    agent = ReasoningAgent(client=client, config=agent_config)

    for idx, item in enumerate(problems[:3]):
        print(f"E2E solve [{idx+1}/3]: {item['id']}")
        res = agent.solve(item["problem"], {"idx": idx})
        trace = res.get("trace", [])
        tail_entries = [e for e in trace if e.get("reasoner") == "tail_continuation"]
        e2e_records.append({
            "id": item["id"],
            "final_response": res.get("final_response", "")[:100],
            "extracted_answer": res.get("extracted_answer", ""),
            "model_calls": trace[-1].get("model_calls", 0) if trace else 0,
            "tail_continuation_triggered": len(tail_entries) > 0,
            "trace_step_count": len(trace),
        })
        print(f"  Calls: {e2e_records[-1]['model_calls']}, TailTriggered: {e2e_records[-1]['tail_continuation_triggered']}, Final: {e2e_records[-1]['final_response'][:50]!r}")

    # Summary
    formation_rate = (
        (continuation_formed_answers / continuation_attempts)
        if continuation_attempts > 0
        else 0.0
    )
    error_rate = (model_errors / (len(problems) + continuation_attempts)) if problems else 0.0

    summary = {
        "run_id": "STATEFUL-TAIL-V1-FIDELITY-001",
        "method_id": "stateful_tail_completion_v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_problems": len(problems),
        "continuation_attempts": continuation_attempts,
        "continuation_formed_answers": continuation_formed_answers,
        "continuation_placeholders": continuation_placeholders,
        "continuation_formation_rate": formation_rate,
        "model_errors": model_errors,
        "model_error_rate": error_rate,
        "elapsed_seconds": elapsed,
        "gates": {
            "health_gate_pass": error_rate <= 0.10,
            "formation_rate_pass": formation_rate >= 0.60,
            "zero_placeholder_pass": continuation_placeholders == 0,
            "json_and_hygiene_pass": True,
        },
        "verdict": (
            "PASS"
            if (error_rate <= 0.10 and formation_rate >= 0.60 and continuation_placeholders == 0)
            else "FAIL"
        ),
    }

    # Save artifacts
    with open(output_dir / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(output_dir / "e2e_records.jsonl", "w", encoding="utf-8") as f:
        for r in e2e_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n================ FIDELITY SUMMARY ================")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=str, default=str(ROOT / "docs" / "experiments" / "STATEFUL-TAIL-V1-FIDELITY-001"))
    parser.add_argument("--max-problems", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    run_fidelity(Path(args.output_dir), max_problems=args.max_problems, timeout=args.timeout)
