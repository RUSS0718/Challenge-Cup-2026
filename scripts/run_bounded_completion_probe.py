"""Run the BCOMP-001 zero-model dry-run.

The default command only validates a concrete preregistration and writes a
plan; it never constructs a network client.  A real endpoint run requires the
explicit ``--allow-real-model-calls`` switch and is intentionally not part of
this Issue's acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient  # noqa: E402
from reasoning_agent.bounded_completion import (  # noqa: E402
    BCOMP_VERSION,
    BoundaryPolicy,
    BoundedProbeRunner,
    METHOD_ID,
    ProbeArm,
    ProbeConfig,
    ProbeItem,
    default_candidate_protocol,
    sha256_file,
    sha256_text,
)
from reasoning_agent.math_harness import HarnessConfig  # noqa: E402
from user_agent import AgentConfig, ReasoningAgent  # noqa: E402


RUN_ID = "BCOMP-001-ZERO-MODEL-001"
FIXTURE = Path("sample_data/bcomp_dry_run_fixture.jsonl")
DEFAULT_OUTPUT = Path("docs/experiments/BCOMP-001-BOUNDED-COMPLETION-FOUNDATIONS-001")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def load_items(path: Path = ROOT / FIXTURE) -> list[ProbeItem]:
    items: list[ProbeItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("fixture_item_must_be_object")
        forbidden = {str(key).lower() for key in value} & {
            "answer",
            "answers",
            "gold",
            "gold_answer",
            "reference_answer",
            "solution",
        }
        if forbidden:
            raise ValueError("dry_run_fixture_contains_answer_data")
        items.append(
            ProbeItem(
                item_id=str(value["item_id"]),
                problem=str(value["problem"]),
                source_family=str(value.get("source_family", "")),
                domain=str(value.get("domain", "")),
                language=str(value.get("language", "")),
                answer_type=str(value.get("answer_type", "")),
            )
        )
    return items


def build_config(items: list[ProbeItem]) -> ProbeConfig:
    fixture_path = ROOT / FIXTURE
    protocol = json.dumps(default_candidate_protocol(), ensure_ascii=False, sort_keys=True)
    code_payload = "\n".join(
        (ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "reasoning_agent/bounded_completion.py",
            "reasoning_agent/math_harness.py",
            "user_agent.py",
            "scripts/run_bounded_completion_probe.py",
        )
    )
    config = ProbeConfig(
        run_id=RUN_ID,
        method_id=METHOD_ID,
        code_sha256=sha256_text(code_payload),
        protocol_sha256=sha256_text(protocol),
        model_id="official-client-deferred",
        endpoint_id="official-endpoint-deferred",
        dataset_path=FIXTURE.as_posix(),
        dataset_sha256=sha256_file(fixture_path),
        seed=20260912,
        prompt_id="bcomp_ordinary_free_format_formation_v1",
        system_prompt=(
            "Solve the problem in ordinary free-form prose. Give a concise, "
            "complete conclusion that matches the requested answer shape."
        ),
        user_prompt_prefix="Problem:\n",
        parser_version="host_parser_v1",
        scorer_version="host_side_gold_v1",
        actual_route="constraint_fit_direct_probe",
        bank_mode="off",
        temperature=0.6,
        boundary=BoundaryPolicy(
            per_item_seconds=1200.0,
            window_seconds=21600.0,
            call_wait_seconds=900.0,
            finalization_allowance_seconds=30.0,
            max_workers=3,
            max_calls_per_item=1,
            max_requested_tokens_per_item=16384,
        ),
        arms=(
            ProbeArm(
                "formation",
                8192,
                "fixed ordinary free-format answer formation",
                "Do not use a special candidate marker or expose hidden answer data.",
            ),
        ),
        planned_items=len(items),
        arm_order_policy="fixed",
        gold_location="host_only",
        isolation_verified=True,
        max_retries=0,
        stop_rules={
            "void_on_incomplete_records": True,
            "void_on_unstable_endpoint": True,
            "first_three_formed_zero": True,
            "max_model_error_rate": 0.10,
        },
    )
    config.validate()
    return config


class _ScriptedClient:
    def chat(self, messages: Any, temperature: float, max_tokens: int) -> str:
        return "Final answer: 4"


def interface_checks() -> dict[str, Any]:
    signature = inspect.signature(InternChatClient.chat)
    names = list(signature.parameters)
    client = _ScriptedClient()
    agent = ReasoningAgent(
        client,
        AgentConfig(
            enable_constraint_fit_harness=True,
            enable_constraint_fit_deep_lane=False,
            enable_constraint_fit_hybrid_router=False,
            enable_temporary_answer_bank=False,
        ),
    )
    result = agent.solve("计算 2+2", {"idx": "bcomp-interface"})
    json.dumps(result, ensure_ascii=False)
    return {
        "public_client_signature": names,
        "public_client_contract_ok": names[:4] == ["self", "messages", "temperature", "max_tokens"],
        "reasoning_agent_constructed": True,
        "solve_nonempty_final_response": isinstance(result.get("final_response"), str)
        and bool(result["final_response"].strip()),
        "solve_json_serializable": True,
        "real_client_constructed": False,
        "real_client_reason": "credentials and endpoint intentionally not used in zero-model acceptance",
    }


def run(output_dir: Path = ROOT / DEFAULT_OUTPUT) -> dict[str, Any]:
    items = load_items()
    config = build_config(items)
    report = BoundedProbeRunner(config, output_dir=output_dir).run(items, dry_run=True)
    checks = interface_checks()
    report["interface_checks"] = checks
    report["zero_model_acceptance"] = bool(
        report["zero_model_calls"]
        and report["planned_requests"] == len(items)
        and report["dispatched_requests"] == 0
        and report["skipped_requests"] == len(items)
        and report["capacity_checks"]["per_item_token_budget_ok"]
        and report["capacity_checks"]["window_capacity_ok"]
        and report["capacity_checks"]["stop_rules_frozen"]
        and checks["public_client_contract_ok"]
        and checks["solve_nonempty_final_response"]
        and checks["solve_json_serializable"]
    )
    report["disposition"] = (
        "CODE_ACCEPTED_ZERO_MODEL_NO_CAPABILITY_CONCLUSION"
        if report["zero_model_acceptance"]
        else "CODE_ACCEPTANCE_FAILED"
    )
    manifest_path = output_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "completed",
            "ended_at_utc": _now(),
            "zero_model_acceptance": report["zero_model_acceptance"],
            "disposition": report["disposition"],
            "report": report,
        }
    )
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "zero_model_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(
        output_dir / "result.md",
        (
            f"# {RUN_ID}\n\n"
            f"结论：`{report['disposition']}`\n\n"
            f"计划请求：{report['planned_requests']}；实际 dispatch：{report['dispatched_requests']}；"
            f"skipped：{report['skipped_requests']}；计划 token 上限：{report['planned_requested_tokens']}；"
            "真实模型调用：0。\n\n"
            "本报告只证明边界、配置、接口和零模型 dry-run；不产生端点健康、数学能力或默认路径结论。\n"
        ),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / DEFAULT_OUTPUT))
    parser.add_argument(
        "--allow-real-model-calls",
        action="store_true",
        help="reserved for a separately authorized future window; this script still runs dry-run only",
    )
    args = parser.parse_args()
    if args.allow_real_model_calls:
        raise SystemExit("BCOMP-001 acceptance is zero-model only; create a new preregistered run")
    print(json.dumps(run(Path(args.output_dir)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
