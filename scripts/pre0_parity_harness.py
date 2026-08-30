"""PRE0-PARITY-001 harness: release face vs experiment face behavior signatures.

Zero model calls.  Defines the 13 preregistered scenarios, executes both faces
in isolated subprocesses (twice each, to catch hidden nondeterminism), and
compares signatures.  The only preregistered allowed divergence is the
reverify-undecided semantics on scenarios reverify_skipped / reverify_inconclusive
(release keeps the revision; experiment rolls back, 2b4ba30 semantics).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-PARITY-001"
RELEASE_ROOT = REPO_ROOT
EXPERIMENT_ROOT = REPO_ROOT / ".worktrees" / "main-integration-20260829"
RUNNER = REPO_ROOT / "scripts" / "pre0_parity_runner.py"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

EXPECTED_DIVERGENT = {"reverify_skipped", "reverify_inconclusive"}
# Frozen semantics direction: release keeps the revised answer, the experiment
# face rolls back to the original (2b4ba30).  Values come from the scenario
# scripts above (3 identical gen votes -> original; revise call -> revised).
SCENARIO_EXPECTATIONS = {
    "reverify_skipped": {"original_final": "5", "revised_final": "6"},
    "reverify_inconclusive": {"original_final": "5", "revised_final": "6"},
}

CONFIG_BASE = {
    "policy_sample_times": 1,
    "verifier_voting_times": 0,
    "enable_dynamic_budget": False,
    "enable_l0_extended_tokens": True,
    "enable_task_aware_prompt": True,
    "enable_time_convergence": True,
    "enable_adaptive_voting": True,
    "vote_k_max": 5,
    "vote_agree_threshold": 3,
    "max_model_calls": 5,
    "max_tokens": 4096,
    "l0_max_tokens": 4096,
    "enable_heterogeneous_reasoners": True,
    "enable_step_verification": False,
    "enable_step_revision": False,
    "p3_call_boost": 0,
    "enable_answer_dual_form": False,
    "enable_numeric_answer_first_prompt": True,
    "enable_numeric_answer_only_prompt": False,
}
REFINE = {"enable_step_verification": True, "enable_step_revision": True, "p3_call_boost": 3}
ARH = {"enable_answer_dual_form": True}

RAISE = lambda message: {"raise": message}  # noqa: E731

CALC = "已知 a=1，b=2，求 a+b 的值。"
L0 = "计算 12 + 34 ?"
PROOF = "证明：等腰三角形两底角相等。"

REJECT_TEXT = "这道题目超出了我当前能够处理的范围。"
PROOF_TEXT = ("证明：设三角形ABC中AB=AC。由等边对等角定理，可得∠B=∠C。"
              "因此两底角相等，证明完毕。\n最终答案：证毕")


def scenarios() -> list[dict]:
    base = dict(CONFIG_BASE)
    refine = {**CONFIG_BASE, **REFINE}
    arh = {**refine, **ARH}
    return [
        {"name": "l0_direct", "problem": L0, "config": base,
         "script": ["12 + 34 = 46\n最终答案：46"]},
        {"name": "hetero_early_consensus", "problem": CALC, "config": base,
         "script": ["第一步直接相加得和。\n最终答案：3",
                    "换角度验证：1与2之和。\n最终答案：3",
                    "第三次确认一致。\n最终答案：3"]},
        {"name": "k5_full", "problem": CALC, "config": base,
         "script": ["最终答案：1", "最终答案：2", "最终答案：3", "最终答案：4", "最终答案：5"]},
        {"name": "model_error_recovery", "problem": CALC, "config": base,
         "script": [RAISE("server_down"), "最终答案：7", "最终答案：7", "最终答案：7"]},
        {"name": "fallback_all_rejected", "problem": CALC, "config": base,
         "script": [REJECT_TEXT] * 5},
        {"name": "verify_all_clear", "problem": CALC, "config": refine,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5", "ALL_OK:COMPLETE"]},
        {"name": "verify_revise", "problem": CALC, "config": refine,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5",
                    "ERROR: 第二步: 符号写反\nERROR: 第三步: 漏掉一项",
                    "修改后的完整解答如下。\n最终答案：6",
                    "ALL_OK:COMPLETE"]},
        {"name": "reverify_pass", "problem": CALC, "config": refine,
         "script": ["最终答案：9", "最终答案：9", "最终答案：9",
                    "ERROR: 首步: 计算失误",
                    "重算后的完整解答如下。\n最终答案：10",
                    "ALL_OK:COMPLETE"]},
        {"name": "reverify_fail", "problem": CALC, "config": refine,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5",
                    "ERROR: 第二步: 推导错误",
                    "试图修复的完整解答。\n最终答案：6",
                    "ERROR: 第二步: 修复不完整"]},
        {"name": "reverify_skipped", "problem": CALC, "config": refine,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5",
                    "ERROR: 第二步: 推导错误",
                    "修正后的完整解答。\n最终答案：6",
                    RAISE("verify_endpoint_down")]},
        {"name": "reverify_inconclusive", "problem": CALC, "config": refine,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5",
                    "ERROR: 第二步: 推导错误",
                    "修正后的完整解答。\n最终答案：6",
                    "我觉得这个解答整体看起来没有问题。"]},
        {"name": "arh_dual_form", "problem": CALC, "config": arh,
         "script": ["最终答案：5", "最终答案：5", "最终答案：5", "ALL_OK:COMPLETE"]},
        {"name": "non_numeric_output", "problem": PROOF, "config": base,
         "script": [PROOF_TEXT] * 5},
    ]


def run_face(face_root: Path, scenarios_path: Path, output_path: Path) -> dict:
    completed = subprocess.run(
        [str(VENV_PYTHON), str(RUNNER),
         "--face-root", str(face_root),
         "--scenarios", str(scenarios_path),
         "--output", str(output_path)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"face {face_root} failed:\n{completed.stdout}\n{completed.stderr}")
    return json.loads(output_path.read_text(encoding="utf-8"))


def compare(release: dict, experiment: dict) -> dict:
    rel_sigs = {sig["scenario"]: sig for sig in release["signatures"]}
    exp_sigs = {sig["scenario"]: sig for sig in experiment["signatures"]}
    scenario_names = [scenario["name"] for scenario in scenarios()]
    scenario_expectations = SCENARIO_EXPECTATIONS
    results = []
    for name in scenario_names:
        rel, exp = rel_sigs.get(name), exp_sigs.get(name)
        if rel is None or exp is None:
            results.append({"scenario": name, "passed": False, "detail": "missing face signature"})
            continue
        if name in EXPECTED_DIVERGENT:
            # Frozen semantics (prereg §3): release keeps the revision, the
            # experiment face rolls back.  The rollback is silent on the
            # skipped/inconclusive paths, so traces may stay identical; the
            # required divergence is the final answer, in this exact direction.
            calls_equal = rel["call_count"] == exp["call_count"] and rel["calls"] == exp["calls"]
            direction_ok = (
                rel["final_response"] == scenario_expectations[name]["revised_final"]
                and exp["final_response"] == scenario_expectations[name]["original_final"]
            )
            results.append({
                "scenario": name, "kind": "expected_divergence",
                "passed": calls_equal and direction_ok,
                "detail": (f"calls_equal={calls_equal} direction_ok={direction_ok} "
                           f"release_final={rel['final_response']!r} experiment_final={exp['final_response']!r}"),
            })
        else:
            fields_equal = (
                rel["call_count"] == exp["call_count"]
                and rel["calls"] == exp["calls"]
                and rel["final_response"] == exp["final_response"]
                and rel["extracted_answer"] == exp["extracted_answer"]
                and rel["trace_sha256"] == exp["trace_sha256"]
            )
            detail = ""
            if not fields_equal:
                diff_field = next(
                    (field for field in ("call_count", "calls", "final_response", "extracted_answer", "trace_sha256")
                     if rel[field] != exp[field]), "?")
                detail = f"first_diff_field={diff_field}"
                if diff_field == "final_response":
                    detail += f" release={rel['final_response']!r} experiment={exp['final_response']!r}"
                elif diff_field == "extracted_answer":
                    detail += f" release={rel['extracted_answer']!r} experiment={exp['extracted_answer']!r}"
            results.append({"scenario": name, "kind": "strict", "passed": fields_equal, "detail": detail})

    required_exports = {"ReasoningAgent", "AgentConfig", "SUBMISSION_CONFIG", "classify_problem_type",
                        "extract_final_answer", "normalize_answer", "POLICY_PROMPT",
                        "ANSWER_ONLY_POLICY_PROMPT"}
    exports_ok = required_exports.issubset(set(experiment.get("exports", [])))
    all_pass = all(item["passed"] for item in results) and exports_ok
    return {
        "all_passed": all_pass,
        "scenario_results": results,
        "facade_exports_ok": exports_ok,
        "missing_exports": sorted(required_exports - set(experiment.get("exports", []))),
    }


def main() -> None:
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    scenarios_payload = scenarios()
    assert len(scenarios_payload) == 13
    scenarios_path = EXPERIMENT_DIR / "parity_scenarios.json"
    scenarios_path.write_text(json.dumps(scenarios_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    scenarios_sha = hashlib.sha256(scenarios_path.read_bytes()).hexdigest()

    outputs = {}
    for face_name, face_root in (("release", RELEASE_ROOT), ("experiment", EXPERIMENT_ROOT)):
        for run_no in (1, 2):
            output_path = EXPERIMENT_DIR / f"signatures_{face_name}_run{run_no}.json"
            outputs[(face_name, run_no)] = run_face(face_root, scenarios_path, output_path)

    # determinism guard: two runs of the same face must be identical
    deterministic = {}
    for face_name in ("release", "experiment"):
        deterministic[face_name] = (
            json.dumps(outputs[(face_name, 1)]["signatures"], sort_keys=True)
            == json.dumps(outputs[(face_name, 2)]["signatures"], sort_keys=True)
        )

    comparison = compare(outputs[("release", 1)], outputs[("experiment", 1)])

    result = {
        "experiment": "PRE0-PARITY-001",
        "run_started_utc": datetime.now(timezone.utc).isoformat(),
        "model_calls": 0,
        "release_face": {"root": str(RELEASE_ROOT), "git_head": "46c08dd (main, user_agent.py unmodified)"},
        "experiment_face": {"root": str(EXPERIMENT_ROOT), "git_head": "39fcd12 + uncommitted 2b4ba30 restore patch"},
        "scenarios_sha256": scenarios_sha,
        "faces_deterministic": deterministic,
        **comparison,
    }
    (EXPERIMENT_DIR / "parity_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("all_passed", "faces_deterministic", "facade_exports_ok",
                                             "missing_exports")}, ensure_ascii=False))
    for item in comparison["scenario_results"]:
        print(f"[{'PASS' if item['passed'] else 'FAIL'}] {item['scenario']} ({item['kind']}) {item['detail']}")
    sys.exit(0 if result["all_passed"] and all(deterministic.values()) else 1)


if __name__ == "__main__":
    main()
