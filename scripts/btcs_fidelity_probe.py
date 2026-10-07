"""Run the bounded BTCS fidelity probe with safe, compact diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from user_agent import AgentConfig, ReasoningAgent
from tests.support.replay_client import ReplayClient, load_cases


_SOLVER_LABELS = {"direct", "independent_checker", "independent_solver"}
_V2_FIDELITY_INPUT_SHA256 = (
    "57f78259c185623beb144cde29d1c0acad15915404736163481a35e119f25c0e"
)


def _btcs_config(protocol_mode: str = "btcs_frame_v2") -> AgentConfig:
    return AgentConfig(
        protocol_mode=protocol_mode,
        policy_temperature=0.6,
        enable_time_convergence=False,
        btcs_max_model_calls=4,
        btcs_solver_max_tokens=4096,
        btcs_arbiter_max_tokens=256,
        btcs_continuation_max_tokens=256,
        btcs_retry_limit=1,
        btcs_retry_base_delay_seconds=0.25,
    )


def _replay_invariants(protocol_mode: str) -> dict[str, bool | int]:
    cases = load_cases()
    arbiter_client = ReplayClient(cases["numeric_arbiter"])
    arbiter_result = ReasoningAgent(
        arbiter_client, _btcs_config(protocol_mode)
    ).solve("计算 3+4。", {})
    arbiter_event = next(
        (
            entry
            for entry in arbiter_result["trace"]
            if entry.get("step") == "btcs_arbiter"
        ),
        {},
    )

    unknown_client = ReplayClient(cases["numeric_continuation_unknown"])
    unknown_result = ReasoningAgent(
        unknown_client, _btcs_config(protocol_mode)
    ).solve("计算 3+4。", {})

    final = next(
        (entry for entry in reversed(arbiter_result["trace"])
         if entry.get("step") == "finalize"),
        {},
    )
    return {
        "arbiter_existing_only": (
            arbiter_event.get("status") == "selected_existing"
            and arbiter_result.get("extracted_answer") == "2"
        ),
        "continuation_unknown_fail_closed": (
            unknown_result.get("extracted_answer") == ""
            and unknown_result.get("final_response") == "未能生成有效数学答案。"
        ),
        "replay_logical_calls_within_cap": int(final.get("logical_calls", 0)) <= 4,
        "replay_http_attempts_within_cap": int(final.get("http_attempts", 0)) <= 5,
        "arbiter_replay_calls": len(arbiter_client.calls),
        "continuation_replay_calls": len(unknown_client.calls),
    }


def _load_items(path: Path, count: int, protocol_mode: str) -> list[dict]:
    items = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if protocol_mode == "btcs_frame_v2":
        if count != 10:
            raise ValueError("v2_fidelity_count_must_be_10")
        if hashlib.sha256(path.read_bytes()).hexdigest() != _V2_FIDELITY_INPUT_SHA256:
            raise ValueError("dataset_sha256_mismatch")
        items = sorted(
            items,
            key=lambda item: hashlib.sha256(
                str(item.get("problem", "")).encode("utf-8")
            ).hexdigest(),
        )
    return items[: max(0, count)]


def _raw_parse_gate(
    solver_requests: int, parsed_packets: int
) -> tuple[bool, float, bool | None]:
    rate = parsed_packets / solver_requests if solver_requests else 0.0
    applicable = solver_requests >= 20
    return applicable, rate, rate >= 0.95 if applicable else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", default="sample_data/complex_capability_freeze_48.jsonl"
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--deadline", type=float, default=360.0)
    parser.add_argument(
        "--protocol-mode",
        choices=("btcs_frame_v2",),
        default="btcs_frame_v2",
    )
    args = parser.parse_args()

    items = _load_items(Path(args.input), args.count, args.protocol_mode)
    client = InternChatClient(
        timeout=args.timeout,
        retry=1,
        request_deadline=args.deadline,
    )
    agent = ReasoningAgent(
        client=client, config=_btcs_config(args.protocol_mode)
    )
    rows: list[dict] = []
    started = time.perf_counter()
    for item in items:
        before_deadline = client.deadline_exceeded_count
        before_orphan = client.orphan_completions
        item_started = time.perf_counter()
        result = agent.solve(str(item["problem"]), {"idx": item.get("idx")})
        trace = result.get("trace", [])
        final = next(
            (entry for entry in reversed(trace) if entry.get("step") == "finalize"),
            {},
        )
        requests = [
            entry
            for entry in trace
            if entry.get("step") == "btcs_request"
            and entry.get("label") in _SOLVER_LABELS
            and entry.get("status") != "skipped"
        ]
        packets = [
            entry
            for entry in trace
            if entry.get("step") == "btcs_packet"
            and entry.get("source") in _SOLVER_LABELS
            and entry.get("status") == "accepted"
        ]
        deadline_delta = client.deadline_exceeded_count - before_deadline
        orphan_delta = client.orphan_completions - before_orphan
        rows.append(
            {
                "idx": item.get("idx"),
                "status": "error" if any(
                    entry.get("status") == "failed" for entry in requests
                ) else "ok",
                "final_response_nonempty": bool(
                    isinstance(result.get("final_response"), str)
                    and result["final_response"].strip()
                ),
                "extracted_present": bool(
                    isinstance(result.get("extracted_answer"), str)
                    and result["extracted_answer"].strip()
                ),
                "per_solve_final_success": bool(
                    final.get("per_solve_final_success")
                ),
                "selection_source": final.get("selection_source", "none"),
                "solver_requests": len(requests),
                "parsed_solver_packets": len(packets),
                "raw_packet_parse_rate": float(
                    final.get("raw_packet_parse_rate", 0.0)
                ),
                "packet_diagnostics": dict(
                    final.get("packet_diagnostics", {})
                ),
                "logical_calls": int(final.get("logical_calls", 0)),
                "http_attempts": int(final.get("http_attempts", 0)),
                "retry_count": int(final.get("retry_count", 0)),
                "deadline_exceeded_count": deadline_delta,
                "orphan_completions": orphan_delta,
                "latency_seconds": round(time.perf_counter() - item_started, 3),
            }
        )
        if rows[-1]["status"] == "error":
            break

    solver_requests = sum(row["solver_requests"] for row in rows)
    parsed_packets = sum(row["parsed_solver_packets"] for row in rows)
    raw_gate_applicable, frame_rate, raw_parse_gate = _raw_parse_gate(
        solver_requests, parsed_packets
    )
    packet_diagnostics = {
        key: sum(row["packet_diagnostics"].get(key, 0) for row in rows)
        for key in (
            "accepted",
            "no_final",
            "unknown_final",
            "placeholder_final",
            "conflicting_final",
            "missing_body",
        )
    }
    final_success_count = sum(
        row["per_solve_final_success"] for row in rows
    )
    final_success_rate = (
        final_success_count / len(rows) if rows else 0.0
    )
    caps_ok = all(
        row["logical_calls"] <= 4 and row["http_attempts"] <= 5 for row in rows
    )
    health_ok = (
        len(rows) == len(items)
        and all(row["status"] == "ok" for row in rows)
        and sum(row["deadline_exceeded_count"] for row in rows) == 0
        and sum(row["orphan_completions"] for row in rows) == 0
    )
    replay = _replay_invariants(args.protocol_mode)
    replay_ok = all(
        value for key, value in replay.items()
        if key.endswith("_only")
        or key.endswith("fail_closed")
        or key.endswith("within_cap")
    )
    safety_gate = (
        health_ok
        and final_success_rate == 1.0
        and caps_ok
        and replay_ok
    )
    if args.protocol_mode == "btcs_frame_v2" and not raw_gate_applicable:
        status = "RAW_SAMPLE_INSUFFICIENT" if safety_gate else "VOID"
    else:
        status = "PASS" if safety_gate and raw_parse_gate else "VOID"
    report = {
        "run_id": "BTCS-FRAME-V2-FIDELITY-001",
        "method_id": args.protocol_mode,
        "protocol_mode": args.protocol_mode,
        "status": status,
        "count": len(rows),
        "expected_count": len(items),
        "rows": rows,
        "solver_requests": solver_requests,
        "parsed_solver_packets": parsed_packets,
        "frame_parse_rate": round(frame_rate, 6),
        "frame_parse_gate_applicable": raw_gate_applicable,
        "raw_sample_status": "SUFFICIENT" if raw_gate_applicable else "RAW_SAMPLE_INSUFFICIENT",
        "frame_parse_gate": raw_parse_gate,
        "packet_diagnostics": packet_diagnostics,
        "per_solve_final_success_count": final_success_count,
        "per_solve_final_success_rate": round(final_success_rate, 6),
        "per_solve_final_success_gate": final_success_rate == 1.0,
        "health_gate": health_ok,
        "caps_gate": caps_ok,
        "safety_gate": safety_gate,
        "replay_invariants": replay,
        "replay_gate": replay_ok,
        "deadline_exceeded_count": client.deadline_exceeded_count,
        "orphan_completions": client.orphan_completions,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "capability_conclusion": None,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
