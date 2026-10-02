"""EXTERNAL-HARD-SETS-SMOKE-001: run the current submission method (FSDF v1) on
the frozen external hard pools with stratified seeded sampling.

Protocol mirrors V4/V5 hard20 runs:
  - workers=3 (official concurrency simulation), request timeout 300s,
  - per-problem time handled by the agent's own time convergence (<=20 min),
  - resume-capable answers.jsonl,
  - official-style judging: AIME integer exact, OlymMATH/HLE via Math-Verify +
    repo answer_equivalence + normalized string comparison,
  - contract check on final_response via the strict extractor.

Sampling rule (frozen before any model call):
  - per set: 50 items; per (set, domain) cell floor 2, remainder proportional
    to domain row counts; all randomness from a single recorded seed;
  - set_a samples at problem-group level (at most one language per group),
    with seeded per-group language choice balanced toward 50/50 ZH/EN.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import DEFAULT_MODEL, InternChatClient
from scripts.external_hard_sets_artifacts import (
    ExternalHardSetsArtifactStore,
    current_git_commit,
)
from user_agent import (
    COD_NUMERIC_PROMPT,
    SUBMISSION_CONFIG,
    ReasoningAgent,
    build_submission_config,
    extract_answer_first,
    extract_final_answer,
)
from scripts.external_hard_sets_reporting import (
    analyze,
    analyze_claim_dsl_qualification,
    analyze_skill_qualification,
    arm_v2_metrics,
    contract_check,
    extract_contract_answer,
    is_unknown_final,
    judge,
    math_verify_ok,
    normalize_answer,
    stage_health,
)

POOLS_DIR = ROOT / "sample_data" / "external_hard_sets"
WRITE_LOCK = threading.Lock()
SAMPLE_SIZE = 50
DOMAIN_FLOOR = 2

FAMILIES = {
    "set_a_olymmath_hard": "OlymMATH",
    "set_b_aime": "AIME",
    "set_c_hle_math": "HLE",
    # Dedicated, scorer-only Skill qualification fixture.  Its applicability
    # labels are never placed in model messages; they are used only below to
    # score route/artifact telemetry.
    "fesf_skill_qualification": "QUAL",
    "cod_numeric_parity": "COD-PARITY",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def sample_set(rows: list[dict[str, Any]], set_id: str, seed: int, size: int) -> list[dict[str, Any]]:
    """Stratified sample with per-domain floor; group-level for set_a."""
    if set_id in {"fesf_skill_qualification", "cod_numeric_parity"}:
        # These fixtures are already frozen. Sampling by domain would destroy
        # their recorded balance, so select the complete file in order.
        if len(rows) != size:
            raise ValueError(f"qualification fixture has {len(rows)} rows, expected {size}")
        return list(rows)
    rng = random.Random(f"{seed}:{set_id}")
    if set_id == "set_a_olymmath_hard":
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[r["problem_group_id"]].append(r)
        by_domain: dict[str, list[str]] = defaultdict(list)
        for gid, grows in groups.items():
            by_domain[grows[0]["domain"]].append(gid)
        for d in by_domain:
            rng.shuffle(by_domain[d])
        n_domains = len(by_domain)
        base = size // n_domains
        take: dict[str, int] = {d: base for d in by_domain}
        for d in sorted(by_domain, key=lambda x: rng.random())[: size - base * n_domains]:
            take[d] += 1
        chosen_groups: list[str] = []
        for d, count in take.items():
            count = max(count, DOMAIN_FLOOR)
            chosen_groups.extend(by_domain[d][:count])
        rng.shuffle(chosen_groups)
        zh_target = len(chosen_groups) // 2
        zh_assigned = 0
        picked: list[dict[str, Any]] = []
        for gid in chosen_groups:
            grows = groups[gid]
            want_zh = rng.random() < (zh_target - zh_assigned) / max(1, len(chosen_groups) - len(picked))
            row = next((g for g in grows if g["language"] == ("ZH" if want_zh else "EN")), grows[0])
            if row["language"] == "ZH":
                zh_assigned += 1
            picked.append(row)
        return picked[:size]
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_domain[r["domain"]].append(r)
    for d in by_domain:
        rng.shuffle(by_domain[d])
    base = size // len(by_domain)
    take = {d: base for d in by_domain}
    for d in sorted(by_domain, key=lambda x: rng.random())[: size - base * len(by_domain)]:
        take[d] += 1
    picked: list[dict[str, Any]] = []
    used: set[int] = set()
    for d, count in take.items():
        for r in by_domain[d][: max(count, min(DOMAIN_FLOOR, len(by_domain[d])))]:
            picked.append(r)
            used.add(id(r))
    # top up if small domains could not fill their quota
    if len(picked) < size:
        rest = [d for d in sorted(by_domain, key=lambda x: rng.random())]
        for d in rest:
            for r in by_domain[d]:
                if len(picked) >= size:
                    break
                if id(r) not in used:
                    picked.append(r)
                    used.add(id(r))
            if len(picked) >= size:
                break
    return picked[:size]


# P0 (FSDF-RELIABILITY-V2): keep stage/failure-category/fallback/budget fields
# in compacted traces so stage health stays attributable after serialization.
# Unknown keys are still dropped, so older baseline traces compact unchanged.
TRACE_KEEP = frozenset({
    "step", "status", "reason", "model_calls", "candidate_id", "schema_valid",
    "method", "generation_calls", "max_model_calls", "top_group_size", "plan_chars",
    "stage", "error_category", "fallback_source", "selected_branch", "max_tokens",
    "elapsed_bucket", "packet_present", "candidate_present", "final_present",
    "ideas_not_diverse", "handoff_missing_fields", "handoff_conflict_fields",
    "handoff_clipped", "finish_context_clipped", "token_usage", "finish_reason",
    "handoff_unknown_fields", "handoff_unclosed_fields", "handoff_field_states",
    "handoff_all_fields_present", "handoff_has_derived_content",
    "handoff_has_candidate_result", "d_candidate_visible_to_e",
    "e_final_equals_d_candidate", "selected_skill", "harness_route_id",
    "harness_steps_expected", "harness_steps_completed",
    "duration_seconds",
    "skill_name", "evidence_id", "claim_id", "supported_count",
    "auxiliary_count", "refuted_count", "unresolved_count", "skill_loaded",
    "skill_choice_parsed", "applicability", "error", "execution_status",
    "claim_known", "binding_ok", "tool_request_valid", "evidence_consumed",
    "protocol_error",
    # ARM-HARNESS-V1 bounded telemetry.  These fields contain only route,
    # budget, candidate metadata, and request lifecycle status; prompts and
    # response bodies are intentionally excluded.
    "arm_policy", "arm_escalation", "arm_lane", "initial_mode",
    "escalation_mode", "reasoning_mode", "requested_tokens", "from", "to",
    "candidate_ids", "lane",
    # ARM-HARNESS-V2 policy and runtime recovery telemetry.  Candidate values
    # are retained only through the bounded summary projection below.
    "profile", "max_calls", "token_budget", "allow_second_sample",
    "allow_resolver", "allow_thinking_on", "failure", "action",
})


def _compact_arm_v2_candidate(value: Any) -> dict[str, Any] | None:
    """Keep only bounded candidate metadata from the v2 summary event."""

    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    if "value" in value:
        result["value"] = str(value["value"] or "")[:256]
    if "valid" in value:
        result["valid"] = bool(value["valid"])
    if "trust" in value:
        result["trust"] = str(value["trust"] or "")[:32]
    if "trust_reason" in value:
        result["trust_reason"] = str(value["trust_reason"] or "")[:240]
    return result


def _compact_arm_v2_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Project v2 decision telemetry without retaining prompts or responses."""

    compacted: dict[str, Any] = {
        key: entry[key]
        for key in (
            "method", "stage", "profile", "early_stop", "second_sample_triggered",
            "agreement", "conflict", "resolver_triggered", "resolver_decision",
            "runtime_recovery_action", "final_source",
        )
        if key in entry
    }
    for key in ("candidate_a", "candidate_b"):
        if key in entry:
            candidate = _compact_arm_v2_candidate(entry[key])
            if candidate is not None:
                compacted[key] = candidate
    return compacted

_STAGE_CLIENT_ERROR_CATEGORIES = frozenset({
    "model_error", "timeout", "rate_limit", "http_status", "request",
    "connectivity", "proxy", "tls", "configuration",
})


def compact_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted = []
    for entry in trace:
        if entry.get("stage") == "evidence_ledger":
            # Project the ARM ledger onto a small allowlist. In particular,
            # omit candidate values, parser response text, and any unbounded
            # objects while retaining mode, budget, and lifecycle evidence.
            ledger: dict[str, Any] = {
                key: entry[key]
                for key in ("method", "harness_version", "stage")
                if key in entry
            }
            ledger["candidates"] = [
                {
                    key: candidate[key]
                    for key in (
                        "candidate_id", "source", "reasoning_mode",
                        "answer_type", "extraction_status", "verification_status",
                    )
                    if key in candidate
                }
                for candidate in entry.get("candidates") or []
                if isinstance(candidate, dict)
            ]
            ledger["calls"] = [
                {
                    key: call[key]
                    for key in (
                        "call_number", "stage", "requested_tokens", "completion_tokens",
                        "finish_reason", "duration_ms", "status", "error_category",
                        "reasoning_mode",
                    )
                    if key in call
                }
                for call in entry.get("calls") or []
                if isinstance(call, dict)
            ]
            budget = entry.get("budget")
            if isinstance(budget, dict):
                ledger["budget"] = {
                    key: budget[key]
                    for key in (
                        "calls", "call_limit", "requested_tokens", "token_limit",
                        "remaining_requested_tokens", "actual_completion_tokens",
                        "actual_token_records", "budget_violated",
                    )
                    if key in budget
                }
            compacted.append(ledger)
        elif entry.get("stage") == "arm_v2_summary":
            compacted.append(_compact_arm_v2_summary(entry))
        else:
            compacted.append({k: entry[k] for k in entry if k in TRACE_KEEP})
    return compacted


def client_diagnostics(
    client: Any,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, list[Any]]:
    """Per-task public client diagnostics (call-ordered, bounded).

    Each task owns its client, so the lists align with that task's calls even
    under workers=3.  Missing attributes degrade to empty lists instead of
    guessing from response text.
    """
    def bounded(name: str, limit: int = 8) -> list[Any]:
        values = getattr(client, name, None)
        if not isinstance(values, list):
            return []
        return list(values[:limit])

    # The client deliberately does not receive stage labels.  Join its
    # logical-call index to the solve-local budget ledger, which uses the same
    # one-based order, without retaining prompts or response content.
    stages: dict[int, str] = {}
    for event in trace or []:
        if event.get("stage") != "evidence_ledger":
            continue
        for call in event.get("calls") or []:
            try:
                stages[int(call.get("call_number"))] = str(call.get("stage") or "")
            except (TypeError, ValueError):
                continue
        break
    request_events = bounded("request_diagnostics", 16)
    requests: list[dict[str, Any]] = []
    for event in request_events:
        if not isinstance(event, dict):
            continue
        try:
            logical_index = int(event.get("logical_call_index"))
        except (TypeError, ValueError):
            logical_index = -1
        requests.append({
            "logical_call_index": logical_index,
            "request_sequence": event.get("request_sequence"),
            "stage": stages.get(logical_index + 1, ""),
            "reasoning_mode": event.get("reasoning_mode"),
            "thinking_mode": event.get("thinking_mode"),
            "status": event.get("status"),
            "requested_tokens": event.get("max_tokens"),
            "completion_tokens": event.get("completion_tokens"),
            "finish_reason": event.get("finish_reason"),
            "duration_seconds": event.get("duration_seconds"),
            "error_category": event.get("error_category"),
        })

    return {
        "finish_reasons": bounded("finish_reasons"),
        "completion_tokens": bounded("completion_tokens"),
        "latencies": bounded("latencies"),
        "requests": requests,
    }


# ── Dual-arm support: same-window interleaved arms on the frozen pools ──
# `v1` is the explicit FSDF v1 anchor.  `v2` turns on the four
# FSDF-RELIABILITY-V2 candidate flags on top of the same profile.  `v2hd`
# additionally turns on fsdf_handoff_first_d_v1 (D prompt only).  These are
# exploratory diagnostic arms; combined arms are NOT attributable per variable
# and produce no capability conclusion by themselves.
FSDF_V2_FLAGS = (
    "enable_fsdf_diagnostics_v2",
    "enable_fsdf_multiline_handoff_v2",
    "enable_fsdf_final_confirmation_v2",
    "enable_fsdf_finish_prompt_v2",
)
FSDF_CANDIDATE_FLAGS = (
    *FSDF_V2_FLAGS,
    "enable_fsdf_handoff_first_d",
    "enable_fsdf_d_result_to_e",
    "enable_fsdf_de_budget_swap",
    "enable_fsdf_finish_compact_final",
    "enable_fsdf_mandatory_final_d",
    "enable_fsdf_finish_handoff_share",
    "enable_fsdf_handoff_open_first_e",
    "enable_fsdf_finish_handoff_share_v2",
    "enable_fsdf_e_budget_up",
    "enable_fsdf_deep_candidate_fallback",
    "enable_fsdf_skill_routes",
    "enable_fsdf_skill_harness",
    # FESF is a separate opt-in path; pin both switches in every arm so a
    # future submission-profile change cannot silently alter an experiment.
    "enable_fesf_v1",
    "enable_fesf_exact_eval",
    "enable_fesf_claim_dsl",
)


def _arm_overrides(enabled: tuple[str, ...] = ()) -> dict[str, bool]:
    """Pin every candidate flag so historical arms stay independent."""
    return {"enable_current_cod_numeric": False,
            **{flag: False for flag in FSDF_CANDIDATE_FLAGS},
            **{flag: True for flag in enabled}}


ARM_DEFINITIONS: dict[str, dict[str, Any]] = {
    "v1": _arm_overrides(),
    # C0/legacy baseline and its single prompt-only CoD candidate.  Both arms
    # are explicitly bank-off and keep the non-FSDF answering path.
    "current_c0": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": False,
        "enable_temporary_answer_bank": False,
        "enable_current_cod_numeric": False,
        "enable_contextual_answer_reconstruction": False,
        "enable_heterogeneous_reasoners": False,
        "enable_adaptive_voting": True,
        "max_model_calls": 5,
        "max_tokens": 4096,
        "l0_max_tokens": 4096,
        "enable_numeric_answer_first_prompt": False,
        "enable_numeric_answer_only_prompt": True,
    },
    "current_cod_numeric": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": False,
        "enable_temporary_answer_bank": False,
        "enable_current_cod_numeric": True,
        "enable_contextual_answer_reconstruction": False,
        "enable_heterogeneous_reasoners": False,
        "enable_adaptive_voting": True,
        "max_model_calls": 5,
        "max_tokens": 4096,
        "l0_max_tokens": 4096,
        "enable_numeric_answer_first_prompt": False,
        "enable_numeric_answer_only_prompt": True,
    },
    # Protocol-stability baseline/candidate: both arms are explicitly bank-off
    # and diagnostics-on; the candidate changes only multi-line D→E handoff.
    "fsdf_protocol_v1": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": True,
        "enable_temporary_answer_bank": False,
        "enable_contextual_answer_reconstruction": False,
        "enable_fsdf_diagnostics_v2": True,
    },
    "fsdf_multiline_handoff_v2": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": True,
        "enable_temporary_answer_bank": False,
        "enable_contextual_answer_reconstruction": False,
        "enable_fsdf_diagnostics_v2": True,
        "enable_fsdf_multiline_handoff_v2": True,
    },
    # Explicit names used by the FESF v1 qualification/A-B protocol.
    "fsdf_v1_tkoff": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": True,
        "enable_fesf_v1": False,
        "enable_fesf_exact_eval": False,
    },
    "fesf_v1_tkoff_exact_eval": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": False,
        "enable_fesf_v1": True,
        "enable_fesf_exact_eval": True,
    },
    # Current FESF plus Claim DSL (single variable vs fesf_v1_tkoff_exact_eval).
    "fesf_v1_tkoff_claim_dsl": {
        **_arm_overrides(),
        "enable_fork_select_deepen_finish": False,
        "enable_fesf_v1": True,
        "enable_fesf_exact_eval": True,
        "enable_fesf_claim_dsl": True,
    },
    "v2": _arm_overrides(FSDF_V2_FLAGS),
    "v2hd": _arm_overrides((*FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d")),
    # v2hd + fsdf_d_result_to_e_v1: single variable = FINAL_D visible to E.
    "v2hd_dre": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d", "enable_fsdf_d_result_to_e",
    )),
    # v2hd + fsdf_de_budget_swap_v1: single variable = D/E budget swap.
    "v2hd_bs": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d", "enable_fsdf_de_budget_swap",
    )),
    # v2hd_bs + fsdf_finish_compact_final_v1: single variable = E compact prompt.
    "v2hd_bs_cf": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_compact_final",
    )),
    # v2hd_bs + fsdf_mandatory_final_d_v1: single variable = mandatory early
    # FINAL_D in D (activates the deep_final fallback for E-failed runs).
    "v2hd_bs_mfd": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_mandatory_final_d",
    )),
    # v2hd_bs + fsdf_finish_handoff_share_v1: single variable = E-input
    # composition (drop selected-idea block, handoff reserve 3000 -> 4600).
    "v2hd_bs_hs": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
    )),
    # v2hd_bs_hs + fsdf_handoff_open_first_e_v1: single variable = E-side
    # handoff rendering order (OPEN before DERIVED).
    "v2hd_hs_of": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_handoff_open_first_e",
    )),
    # v2hd_hs + fsdf_finish_handoff_share_v2: single variable = share-mode
    # composition drops the A-summary block too; handoff reserve 4600 -> 6050.
    # v2hd_hs + fsdf_finish_handoff_share_v2: single variable = share-mode
    # composition drops the A-summary block too; handoff reserve 4600 -> 6050.
    "v2hd_hs_sv2": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_handoff_open_first_e", "enable_fsdf_finish_handoff_share_v2",
    )),
    # v2hd_hs + fsdf_e_budget_up_v1: single variable = E budget 8192 -> 9728
    # (total 18432 -> 19968); no donor stage exists.
    "v2hd_hs_eu": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_handoff_open_first_e", "enable_fsdf_e_budget_up",
    )),
    # v2hd_bs_hs + fsdf_deep_candidate_fallback_v1: single variable = adopt a
    # content-state CANDIDATE_D when E fails (E-failure-only, program-side).
    "v2hd_bs_hs_dcf": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_deep_candidate_fallback",
    )),
    # v2hd_bs_hs + client thinking off (fsdf_thinking_off_v1): single variable
    # is the client-level thinking switch (ARM_THINKING_MODE); the AgentConfig
    # is identical to the frontier.
    "v2hd_bs_hs_tkoff": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
    )),
    # v2hd_hs + skill routes, thinking off (fsdf_skill_routes_v1): candidate
    # for the skills experiment — frontier composition + host-filtered route
    # layer + client thinking disabled.
    "v2hd_hs_sr": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_skill_routes",
    )),
    # v2hd_hs + fsdf_skill_harness_v1, thinking off: forced route-execution
    # harness per the user directive (raise constraints so the model follows
    # the skill).
    "v2hd_hs_tkh": _arm_overrides((
        *FSDF_V2_FLAGS, "enable_fsdf_handoff_first_d",
        "enable_fsdf_de_budget_swap", "enable_fsdf_finish_handoff_share",
        "enable_fsdf_skill_harness",
    )),
}

# ARM-HARNESS-V1 profiles.  They share the same outer harness and bank-off
# policy; only the request-level reasoning-mode lane differs.  Keeping these
# definitions here lets the runner clone the explicit FSDF baseline without
# mutating or inheriting the official submission path.
ARM_HARNESS_BASE = {
    **_arm_overrides(),
    "enable_constraint_fit_harness": True,
    "enable_constraint_fit_deep_lane": True,
    "enable_constraint_fit_hybrid_router": False,
    "enable_arm_harness": True,
    "enable_fork_select_deepen_finish": False,
    "enable_adaptive_candidate_first": False,
    "enable_adaptive_dual_candidate_consensus": False,
    "enable_adaptive_voting": False,
    "enable_heterogeneous_reasoners": False,
    "enable_numeric_answer_first_prompt": False,
    "enable_contextual_answer_reconstruction": False,
    "enable_typed_answer_capsule": False,
    "enable_condition_checked_selection": False,
    "enable_plan_solve_compact": False,
    "enable_fesf_v1": False,
    "enable_fesf_exact_eval": False,
    "enable_fesf_claim_dsl": False,
    "enable_method_rag": False,
    "enable_reference_rag": False,
    "enable_reference_skills": False,
    "enable_host_intake": False,
    "enable_bounded_obligation_extractor": False,
    "enable_constraint_fit_migration_hardening": False,
    "enable_constraint_fit_deterministic_playoff": False,
    "enable_constraint_fit_process_audit": False,
    "enable_constraint_fit_prefill": False,
    "harness_bank_mode": "off",
    "enable_temporary_answer_bank": False,
}
ARM_DEFINITIONS.update({
    "arm-off": {
        **ARM_HARNESS_BASE,
        "arm_allow_thinking_on": False,
        "arm_default_lane": "adaptive",
    },
    "arm-on": {
        **ARM_HARNESS_BASE,
        "arm_allow_thinking_on": True,
        "arm_default_lane": "deep_on",
    },
    "arm-static": {
        **ARM_HARNESS_BASE,
        "arm_allow_thinking_on": True,
        "arm_default_lane": "static",
    },
    "arm-adaptive": {
        **ARM_HARNESS_BASE,
        "arm_allow_thinking_on": True,
        "arm_default_lane": "adaptive",
    },
})

# ARM-HARNESS-V2 experiment arms.  They use the same bank-off harness base as
# v1, but pin the v2 compute/recovery policy so an experiment cannot inherit a
# future submission-profile change.
ARM_DEFINITIONS.update({
    "arm-v2-single": {
        **ARM_HARNESS_BASE,
        "arm_harness_version": "v2",
        "arm_v2_mode": "single",
        "arm_timeout_recovery_mode": "none",
        "arm_primary_timeout_seconds": None,
        "arm_allow_thinking_on": False,
        "arm_default_lane": "adaptive",
    },
    "arm-v2-selective": {
        **ARM_HARNESS_BASE,
        "arm_harness_version": "v2",
        "arm_v2_mode": "selective",
        "arm_timeout_recovery_mode": "none",
        "arm_primary_timeout_seconds": None,
        "arm_allow_thinking_on": False,
        "arm_default_lane": "adaptive",
    },
    "arm-v2-long-timeout": {
        **ARM_HARNESS_BASE,
        "arm_harness_version": "v2",
        "arm_v2_mode": "long_timeout",
        "arm_timeout_recovery_mode": "none",
        "arm_primary_timeout_seconds": 60,
        "arm_allow_thinking_on": False,
        "arm_default_lane": "adaptive",
    },
    "arm-v2-salvage": {
        **ARM_HARNESS_BASE,
        "arm_harness_version": "v2",
        "arm_v2_mode": "salvage",
        "arm_timeout_recovery_mode": "compact_salvage",
        "arm_primary_timeout_seconds": 30,
        "arm_allow_thinking_on": False,
        "arm_default_lane": "adaptive",
    },
})


def arm_config(arm: str) -> Any:
    if arm not in ARM_DEFINITIONS:
        raise ValueError(f"unknown arm: {arm} (available: {', '.join(ARM_DEFINITIONS)})")
    base = build_submission_config("fsdf")
    return dataclasses.replace(base, **ARM_DEFINITIONS[arm])


# Per-arm client-level thinking switch: None = server default (env), False =
# thinking disabled for that arm's calls (see apply_thinking_mode probe:
# the default thinking pass consumed the whole completion budget inside the
# output stream).
ARM_THINKING_MODE: dict[str, bool | None] = {
    "fsdf_v1_tkoff": False,
    "fesf_v1_tkoff_exact_eval": False,
    "fesf_v1_tkoff_claim_dsl": False,
    "v2hd_bs_hs_tkoff": False,
    "v2hd_hs_sr": False,
    "v2hd_hs_tkh": False,
    # ARM controls thinking per request through reasoning_mode.  Keeping the
    # client default at None prevents a process-level switch from contaminating
    # the paired window.
    "arm-off": None,
    "arm-on": None,
    "arm-static": None,
    "arm-adaptive": None,
    "arm-v2-single": None,
    "arm-v2-selective": None,
    "arm-v2-long-timeout": None,
    "arm-v2-salvage": None,
}


def arm_thinking_mode(arm: str) -> bool | None:
    return ARM_THINKING_MODE.get(arm)


def assign_arms(tasks: list[dict[str, Any]], arms: list[str]) -> None:
    """Deterministically interleave arms over the seeded-shuffled task list."""
    if not arms:
        raise ValueError("arms must not be empty")
    for index, task in enumerate(tasks):
        task["arm"] = arms[index % len(arms)]


def assign_arms_paired(tasks: list[dict[str, Any]], arms: list[str]) -> list[dict[str, Any]]:
    """Same-question pairing: every task runs once per arm.

    The first arm rotates per item (item i starts with ``arms[i % k]``) AND the
    returned list is ordered so actual execution alternates arms
    (pair-order-major), instead of always running the baseline arm of each
    item first.
    """
    if not arms:
        raise ValueError("arms must not be empty")
    paired: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        rotation = index % len(arms)
        for offset, arm in enumerate(arms):
            entry = dict(task)
            entry["arm"] = arm
            entry["pair_order"] = (offset - rotation) % len(arms)
            entry["item_seq"] = index
            paired.append(entry)
    # Execution order: alternate arms across items (pair-order-major).
    paired.sort(key=lambda e: (e["pair_order"], e["item_seq"]))
    return paired


def extract_for_judge(result: dict[str, Any]) -> str:
    extracted = str(result.get("extracted_answer") or "").strip()
    final = str(result.get("final_response") or "").strip()
    if extracted and extracted.upper() != "UNKNOWN":
        return extracted
    return extract_answer_first(final) or extract_final_answer(final) or final


def solve_one(task: dict[str, Any], timeout: int, api_key: str) -> dict[str, Any]:
    item = task["item"]
    arm = task.get("arm", "v1")
    config = arm_config(arm)
    client = InternChatClient(timeout=timeout, thinking_mode=arm_thinking_mode(arm))
    agent = ReasoningAgent(client=client, config=config)
    status = "ok"
    t0 = time.time()
    try:
        result = agent.solve(item["problem"], {"idx": task["task_idx"]})
    except Exception as exc:
        status = f"error:{getattr(exc, 'category', type(exc).__name__)}"
        result = {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
    duration = time.time() - t0
    trace = result.get("trace") or []
    calls = int(trace[-1].get("model_calls") or 0) if trace else 0
    final_response = result.get("final_response", "")
    pred = extract_for_judge(result)
    family = FAMILIES[task["set_id"]]
    native = judge(pred, item["answer"], family)
    contract = contract_check(final_response, item["answer"], family)
    compact_trace_rows = compact_trace(trace)
    # trace hygiene: the API key must never appear anywhere in the serialized result
    serializable = True
    try:
        blob = json.dumps({"final_response": final_response, "trace": compact_trace_rows}, ensure_ascii=False)
        json.loads(blob)
        if api_key and api_key in blob:
            serializable = False
            status = status if status != "ok" else "error:trace_hygiene"
    except (TypeError, ValueError):
        serializable = False
        status = status if status != "ok" else "error:not_serializable"
    nonempty_final = isinstance(final_response, str) and bool(final_response.strip())
    contract_extractable = bool(extract_contract_answer(final_response, family))
    format_ok = contract_extractable
    client_diag = client_diagnostics(client, compact_trace_rows)
    arm_policy = next(
        (event for event in compact_trace_rows if event.get("stage") == "arm_policy"),
        {},
    )
    arm_escalations = [
        event for event in compact_trace_rows
        if event.get("stage") == "arm_escalation"
    ]
    v2_summary = next(
        (event for event in compact_trace_rows if event.get("stage") == "arm_v2_summary"),
        {},
    )
    v2_candidate_a = v2_summary.get("candidate_a") or {}
    v2_candidate_b = v2_summary.get("candidate_b") or {}
    evidence = next(
        (event for event in compact_trace_rows if event.get("stage") == "evidence_ledger"),
        {},
    )
    candidates = [
        {
            key: candidate[key]
            for key in ("candidate_id", "source", "reasoning_mode", "extraction_status", "verification_status")
            if key in candidate
        }
        for candidate in evidence.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    request_modes = [
        request.get("reasoning_mode")
        for request in client_diag["requests"]
        if request.get("reasoning_mode") in {"off", "on", "inherit"}
    ]
    request_errors = [
        request.get("error_category")
        for request in client_diag["requests"]
        if request.get("status") == "error" and request.get("error_category")
    ]
    if status == "ok" and request_errors and is_unknown_final(final_response):
        # A request error is a request-level diagnostic.  It becomes a final
        # solve error only when no usable final response survived.
        status = f"error:{request_errors[-1]}"
    record = {
        "set_id": task["set_id"],
        "item_id": item["item_id"],
        "arm": arm,
        "pair_order": task.get("pair_order", ""),
        "thinking_mode": (
            "request_scoped" if arm.startswith("arm-")
            else "off" if arm_thinking_mode(arm) is False
            else "default"
        ),
        "arm_lane": arm_policy.get("lane", ""),
        "arm_policy": arm_policy,
        "arm_escalation": arm_escalations,
        "arm_v2_summary": v2_summary,
        "candidate_a": v2_candidate_a.get("value"),
        "candidate_a_valid": v2_candidate_a.get("valid"),
        "candidate_a_trust": v2_candidate_a.get("trust"),
        "candidate_b": v2_candidate_b.get("value"),
        "candidate_b_valid": v2_candidate_b.get("valid"),
        "candidate_b_trust": v2_candidate_b.get("trust"),
        "early_stop": bool(v2_summary.get("early_stop")),
        "second_sample_triggered": bool(v2_summary.get("second_sample_triggered")),
        "agreement": bool(v2_summary.get("agreement")),
        "conflict": bool(v2_summary.get("conflict")),
        "resolver_triggered": bool(v2_summary.get("resolver_triggered")),
        "resolver_decision": v2_summary.get("resolver_decision"),
        "runtime_recovery_action": v2_summary.get("runtime_recovery_action"),
        "final_source": v2_summary.get("final_source"),
        "initial_mode": arm_policy.get("initial_mode", ""),
        "escalation_mode": arm_policy.get("escalation_mode", ""),
        "reasoning_modes": request_modes,
        "candidate_telemetry": candidates,
        "candidate_count": len(candidates),
        "token_budget": arm_policy.get("token_budget"),
        "problem_group_id": item.get("problem_group_id", ""),
        "language": item.get("language", ""),
        "domain": item["domain"],
        "source_family": family,
        "seed": task["seed"],
        "status": status,
        "final_response": final_response,
        "extracted_answer": result.get("extracted_answer", ""),
        "pred": pred,
        "gold": item["answer"],
        "native": native,
        "contract": contract,
        "verdict_match": native["verdict"] == contract["verdict"],
        "nonempty_final": nonempty_final,
        "contract_extractable": contract_extractable,
        "format_ok": format_ok,
        "json_serializable": serializable,
        "model_calls": calls,
        "duration_seconds": round(duration, 2),
        "trace": compact_trace_rows,
        "client_finish_reasons": client_diag["finish_reasons"],
        "client_completion_tokens": client_diag["completion_tokens"],
        "client_request_diagnostics": client_diag["requests"],
        "request_error_categories": request_errors,
    }
    # Qualification labels are scorer-only metadata.  ``solve`` above only
    # receives problem text and an index, so this field cannot enter any model
    # request; keeping it in the answer record makes the gate reproducible.
    if "applicable" in item:
        route_event = next((e for e in compact_trace_rows if e.get("stage") == "route"), {})
        tool_events = [e for e in compact_trace_rows if e.get("stage") == "tool_exact_eval"]
        record.update({
            "qualification_applicable": bool(item.get("applicable")),
            "skill_selected": route_event.get("skill_name") == "exact-evaluation",
            "skill_choice_parsed": bool(route_event.get("skill_choice_parsed")),
            "route_applicability": str(route_event.get("applicability") or "UNKNOWN"),
            "tool_request_count": len(tool_events),
            "tool_events": tool_events,
        })
    claim_events = [e for e in compact_trace_rows if e.get("stage") == "tool_claim_dsl"]
    if claim_events:
        record["claim_dsl_events"] = claim_events
    return record


def apply_thinking_mode(mode: str) -> None:
    """Set the client-side thinking-mode switch for this process.

    ``default`` leaves the environment untouched (server-side default).
    ``false``/``true`` set INTERN_THINKING_MODE which InternChatClient
    forwards in the request payload.  Iteration-loop probe (2026-09-06) showed
    the default thinking pass consumes the completion budget inside the
    output stream: same problem/budget went length/2048 tokens (zero protocol
    fields) -> stop/178 tokens with all fields emitted.
    """
    if mode == "default":
        return
    os.environ["INTERN_THINKING_MODE"] = mode


def run_preflight(
    output_dir: Path | None,
    timeout: int = 240,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run three bounded resource requests before a CoD qualification window."""
    artifacts = ExternalHardSetsArtifactStore.create(
        root=ROOT,
        output_dir=output_dir,
        run_id=run_id,
        config="external-hard-sets-preflight",
        dataset="endpoint-health-preflight",
        model=os.environ.get("INTERN_MODEL", DEFAULT_MODEL),
        git_commit=current_git_commit(ROOT),
    )
    output_dir = artifacts.run_dir
    requests: list[dict[str, Any]] = []
    for index in range(3):
        started = time.perf_counter()
        client = None
        status = "ok"
        error_category = None
        try:
            client = InternChatClient(timeout=timeout, retry=1)
            response = client.chat(
                [{"role": "user", "content": "Resource preflight. Return exactly PREFLIGHT_OK."}],
                temperature=0.0,
                max_tokens=2048,
            )
            if not isinstance(response, str) or not response.strip():
                status = "invalid_response"
                error_category = "invalid_response"
        except Exception as exc:
            status = "error"
            error_category = getattr(exc, "category", type(exc).__name__)
        requests.append({
            "request_index": index + 1,
            "status": status,
            "error_category": error_category,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "finish_reason": client.finish_reasons[-1] if client and client.finish_reasons else None,
            "completion_tokens": client.completion_tokens[-1] if client and client.completion_tokens else None,
        })
    report = {
        "phase": "P1_resource_preflight",
        "requests": requests,
        "success_count": sum(item["status"] == "ok" for item in requests),
        "client_errors": sum(item["status"] == "error" for item in requests),
        "timeouts": sum(item["error_category"] == "timeout" for item in requests),
        "invalid_responses": sum(item["status"] == "invalid_response" for item in requests),
        "pass": all(item["status"] == "ok" for item in requests),
        "thinking_mode": "official_default / client thinking_mode=None",
        "max_tokens": 2048,
        "request_timeout_seconds": timeout,
        "run_id": artifacts.context.run_id,
    }
    artifacts.save_preflight(report)
    artifacts.save_manifest(
        {
            "phase": report["phase"],
            "request_timeout_seconds": timeout,
            "preflight_pass": report["pass"],
        },
        status="completed" if report["pass"] else "failed",
    )
    return report


def run(output_dir: Path | None, timeout: int, workers: int, seed: int, hard_stop_minutes: float,
        sample_size: int, sets: list[str], arms: list[str] | None = None,
        run_id: str | None = None, pairing: str = "independent",
        thinking_mode: str = "default", sample_sizes: dict[str, int] | None = None,
        fixed_items: dict[str, list[str]] | None = None) -> None:
    """Run a resumable hard-set window and persist it below one run directory."""
    arms = arms or ["v1"]
    for arm in arms:
        arm_config(arm)  # validate early
    if pairing not in ("independent", "paired"):
        raise SystemExit(f"unknown pairing mode: {pairing}")
    apply_thinking_mode(thinking_mode)
    artifacts = ExternalHardSetsArtifactStore.create(
        root=ROOT,
        output_dir=output_dir,
        run_id=run_id,
        config="external-hard-sets-smoke",
        dataset=",".join(sets),
        model=os.environ.get("INTERN_MODEL", DEFAULT_MODEL),
        git_commit=current_git_commit(ROOT),
    )
    output_dir = artifacts.run_dir
    if set(arms).intersection({"current_c0", "current_cod_numeric"}):
        preflight_path = output_dir / "preflight.json"
        if not preflight_path.exists():
            raise SystemExit("CoD qualification requires a passing preflight.json")
        if not json.loads(preflight_path.read_text(encoding="utf-8")).get("pass"):
            raise SystemExit("CoD qualification preflight did not pass")
    api_key = os.environ.get("INTERN_API_KEY", "")
    all_tasks: list[dict[str, Any]] = []
    sampled_manifest: dict[str, list[str]] = {}
    effective_sample_sizes: dict[str, int] = {}
    for set_id in sets:
        pool_path = (
            ROOT / "sample_data" / "fesf_skill_qualification.jsonl"
            if set_id == "fesf_skill_qualification"
            else ROOT / "sample_data" / "cod_numeric_parity.jsonl"
            if set_id == "cod_numeric_parity"
            else POOLS_DIR / f"{set_id}.jsonl"
        )
        rows = load_jsonl(pool_path)
        size = (sample_sizes or {}).get(set_id, sample_size)
        if fixed_items and set_id in fixed_items:
            ids = fixed_items[set_id]
            if len(ids) != len(set(ids)):
                raise SystemExit(f"{set_id}: fixed item ids must be unique")
            by_id = {str(row.get("item_id")): row for row in rows}
            missing = [item_id for item_id in ids if item_id not in by_id]
            if missing:
                raise SystemExit(f"{set_id}: fixed item is missing: {missing}")
            picked = [by_id[item_id] for item_id in ids]
            size = len(picked)
        else:
            picked = sample_set(rows, set_id, seed, size)
        if len(picked) != size:
            raise SystemExit(f"{set_id}: sampled {len(picked)} != {size}")
        sampled_manifest[set_id] = [r["item_id"] for r in picked]
        effective_sample_sizes[set_id] = len(picked)
        for i, item in enumerate(picked):
            all_tasks.append({"set_id": set_id, "item": item, "seed": seed, "task_idx": f"{set_id}-{i}"})
    rng = random.Random(seed)
    rng.shuffle(all_tasks)
    if pairing == "paired":
        all_tasks = assign_arms_paired(all_tasks, arms)
    else:
        assign_arms(all_tasks, arms)

    answers_path = artifacts.answers_path
    done_keys: set[tuple[str, str, str]] = set()
    if answers_path.exists():
        for row in load_jsonl(answers_path):
            done_keys.add((row["set_id"], row["item_id"], str(row.get("arm", ""))))
    pending = [
        t for t in all_tasks
        if (t["set_id"], t["item"]["item_id"], t["arm"]) not in done_keys
    ]

    manifest = {
        "run_id": artifacts.context.run_id,
        "pools_dir": str(POOLS_DIR.relative_to(ROOT)).replace("\\", "/"),
        "pool_sha256": {p.name: sha256_file(p) for p in sorted(POOLS_DIR.glob("*.jsonl"))},
        "custom_pool_sha256": {
            "cod_numeric_parity.jsonl": sha256_file(ROOT / "sample_data" / "cod_numeric_parity.jsonl")
            if "cod_numeric_parity" in sets else None,
        },
        "qualification_file": (
            "sample_data/fesf_skill_qualification.jsonl"
            if "fesf_skill_qualification" in sets else None
        ),
        "qualification_sha256": (
            sha256_file(ROOT / "sample_data" / "fesf_skill_qualification.jsonl")
            if "fesf_skill_qualification" in sets else None
        ),
        "seed": seed,
        "workers": workers,
        "request_timeout_seconds": timeout,
        "hard_stop_minutes": hard_stop_minutes,
        "sample_size_per_set": sample_size,
        "sample_sizes": effective_sample_sizes,
        "fixed_items": fixed_items,
        "sampled_items": sampled_manifest,
        "arms": arms,
        "arm_assignment": "round_robin_over_seeded_shuffle",
        "pairing": pairing,
        "thinking_mode": thinking_mode,
        "prompt_hashes": {
            "cod_numeric": hashlib.sha256(COD_NUMERIC_PROMPT.encode("utf-8")).hexdigest(),
        },
        "preflight_sha256": sha256_file(output_dir / "preflight.json")
        if set(arms).intersection({"current_c0", "current_cod_numeric"}) else None,
        "arm_flags": {arm: dict(ARM_DEFINITIONS[arm]) for arm in arms},
        "arm_thinking_modes": {
            arm: (
                "request_scoped" if arm.startswith("arm-")
                else "off" if arm_thinking_mode(arm) is False
                else "default"
            )
            for arm in arms
        },
        "fesf_skill_sha256": {
            "reasoning_agent/fesf_skills/exact-evaluation/SKILL.md": sha256_file(
                ROOT / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "SKILL.md"
            ) if (ROOT / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "SKILL.md").exists() else "missing",
            "reasoning_agent/fesf_skills/exact-evaluation/cases.jsonl": sha256_file(
                ROOT / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "cases.jsonl"
            ) if (ROOT / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "cases.jsonl").exists() else "missing",
        },
        "method": (
            "Explicit arm definitions: fsdf_v1_tkoff is the FSDF v1 anchor; "
            "fesf_v1_tkoff_exact_eval is FESF v1 plus the independently "
            "qualified exact-evaluation Skill; fesf_v1_tkoff_claim_dsl adds "
            "opt-in Claim DSL on that FESF path. Existing v2 arms remain "
            "exploratory diagnostics and are not capability conclusions."
        ),
        "git_head": artifacts.context.git_commit or "",
        "source_sha256": {
            path: sha256_file(ROOT / path)
            for path in (
                "reasoning_agent/fork_evidence_synthesize_finish.py",
                "reasoning_agent/fesf_memory/solve_state.py",
                "reasoning_agent/fesf_verifiers/claim_dsl.py",
                "reasoning_agent/fesf_verifiers/claim_executor.py",
                "scripts/run_external_hard_sets_smoke.py",
                "user_agent.py",
            )
        },
        "worktree_snapshot": "dirty_changes_hashed_above; .git is read-only in this runner",
        "start_unix": time.time(),
        "n_tasks": len(all_tasks),
        "n_pending": len(pending),
    }
    artifacts.save_manifest(manifest, status="running")
    print(f"[EXT-SMOKE] run_id={run_id} pending={len(pending)} workers={workers} seed={seed} arms={','.join(arms)}", flush=True)

    start = time.time()

    def job(task: dict[str, Any]) -> dict[str, Any]:
        if (time.time() - start) > hard_stop_minutes * 60:
            return {"skipped": True, "reason": "hard_stop", "set_id": task["set_id"], "item_id": task["item"]["item_id"]}
        record = solve_one(task, timeout, api_key)
        with WRITE_LOCK:
            artifacts.append_answer(record)
        print(
            f"[{task['set_id'][:10]}][{record['arm']}] {record['item_id']} {record['native']['verdict']}"
            f" calls={record['model_calls']} dur={record['duration_seconds']:.0f}s"
            f" status={record['status']}",
            flush=True,
        )
        return record

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, t) for t in pending]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                print(f"[runner] job crashed: {type(exc).__name__}: {exc}", flush=True)

    rows = load_jsonl(answers_path)
    rows = [r for r in rows if r.get("set_id") in sets]
    summary = analyze(rows)
    summary["elapsed_seconds"] = round(time.time() - start, 1)
    summary["dataset_info"] = {
        "pools_dir": str(POOLS_DIR),
        "seed": seed,
        "sample_size_per_set": sample_size,
        "sample_sizes": effective_sample_sizes,
    }
    if "skill_qualification" in summary:
        summary["status"] = (
            "SKILL_QUALIFICATION_GO"
            if summary["skill_qualification"]["qualification_pass"]
            else "SKILL_QUALIFICATION_NO_GO"
        )
    summary["window_note"] = (
        "diagnostic window; thresholds unfrozen; combined v2 arm is exploratory "
        "and supports no capability conclusion or promotion"
    )
    artifacts.save_report(summary)
    manifest["status"] = "completed"
    artifacts.save_manifest(manifest)
    print(json.dumps(summary.get("by_arm", summary["by_set"]), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        help="output directory (default: artifacts/<unique-run-id>)",
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260905)
    # FESF qualification + two capability windows share a strict 180-minute
    # local budget; callers may still pass a smaller stop for a smoke run.
    parser.add_argument("--hard-stop-minutes", type=float, default=180.0)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--sample-sizes", help="Optional comma list such as set_a_olymmath_hard=10,cod_numeric_parity=3")
    parser.add_argument("--fixed-items-file", help="JSON mapping of set id to frozen item-id lists")
    parser.add_argument("--preflight-only", action="store_true", help="Run only the three-request resource preflight")
    parser.add_argument("--sets", default="set_a_olymmath_hard,set_b_aime,set_c_hle_math")
    parser.add_argument("--arms", default="v1", help="comma list including fesf_v1_tkoff_claim_dsl (interleaved round-robin)")
    parser.add_argument("--pairing", default="independent", choices=["independent", "paired"],
                        help="paired: every sampled item runs once per arm with rotated first arm")
    parser.add_argument("--thinking-mode", default="default", choices=["default", "false", "true"],
                        help="client-side thinking switch (default = server default)")
    parser.add_argument("--run-id", help="explicit run id; omitted runs receive a unique timestamped id")
    args = parser.parse_args()
    if args.preflight_only:
        output_dir = Path(args.output_dir) if args.output_dir else None
        report = run_preflight(output_dir, args.timeout, args.run_id)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(0 if report["pass"] else 1)
    sample_sizes = {}
    if args.sample_sizes:
        for item in args.sample_sizes.split(","):
            name, sep, raw_size = item.partition("=")
            if not sep or not name.strip() or not raw_size.strip().isdigit() or int(raw_size) <= 0:
                parser.error("--sample-sizes expects name=positive_int pairs")
            sample_sizes[name.strip()] = int(raw_size)
    fixed_items = None
    if args.fixed_items_file:
        fixed_items = json.loads(Path(args.fixed_items_file).read_text(encoding="utf-8"))
        if not isinstance(fixed_items, dict) or any(
            not isinstance(key, str) or not isinstance(value, list)
            or not all(isinstance(item_id, str) for item_id in value)
            for key, value in fixed_items.items()
        ):
            parser.error("--fixed-items-file must contain a JSON object of string lists")
    run(
        Path(args.output_dir) if args.output_dir else None, args.timeout, args.workers, args.seed,
        args.hard_stop_minutes, args.sample_size,
        [s.strip() for s in args.sets.split(",") if s.strip()],
        arms=[a.strip() for a in args.arms.split(",") if a.strip()],
        run_id=args.run_id,
        pairing=args.pairing,
        thinking_mode=args.thinking_mode,
        sample_sizes=sample_sizes,
        fixed_items=fixed_items,
    )
