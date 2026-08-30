"""PRE0-PARITY-001 per-face executor.

Runs inside a subprocess with --face-root inserted at sys.path[0], so
``import user_agent`` resolves to exactly one face (release monolith or
experiment package facade).  For each scenario it builds a fresh FakeClient
and a fresh agent (per-solve isolation), runs solve(), and dumps a behavior
signature: ordered transcript hashes, temperatures, max_tokens, final
response, extracted answer, and a full-trace hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


class FakeClient:
    """Deterministic scripted client; records every call's transcript."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if not self.script:
            raise AssertionError("FakeClient script exhausted — scenario design error")
        item = self.script.pop(0)
        if isinstance(item, dict) and "raise" in item:
            raise RuntimeError(item["raise"])
        return item


def signature(scenario: dict, agent, problem: str) -> dict:
    calls = []
    for call in agent.client.calls:
        calls.append({
            "prompt_sha256": hashlib.sha256(
                json.dumps(call["messages"], sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "temperature": call["temperature"],
            "max_tokens": call["max_tokens"],
        })
    result = agent.solve(problem, {"idx": 0})
    trace = result.get("trace", [])
    return {
        "scenario": scenario["name"],
        "call_count": len(calls),
        "calls": calls,
        "final_response": result.get("final_response"),
        "extracted_answer": result.get("extracted_answer"),
        "trace_sha256": hashlib.sha256(
            json.dumps(trace, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "trace_steps": [
            {"step": entry.get("step"), "status": entry.get("status"), "reason": entry.get("reason")}
            for entry in trace
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--face-root", required=True)
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    face_root = str(Path(args.face_root).resolve())
    sys.path.insert(0, face_root)
    import user_agent  # resolves against face_root only

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    signatures = []
    for scenario in scenarios:
        script = [
            RuntimeError(item["raise"]) if isinstance(item, dict) and "raise" in item else item
            for item in scenario["script"]
        ]
        client = FakeClient(script)
        agent = user_agent.ReasoningAgent(client=client, config=user_agent.AgentConfig(**scenario["config"]))
        agent.client = client  # ensure the harness observes the same client object
        signatures.append(signature(scenario, agent, scenario["problem"]))

    exports = sorted(name for name in dir(user_agent) if not name.startswith("_"))
    payload = {"face_root": face_root, "signatures": signatures, "exports": exports}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(signatures)} signatures for face {face_root}")


if __name__ == "__main__":
    main()
