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
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import InternChatClient
from user_agent import (
    SUBMISSION_CONFIG,
    ReasoningAgent,
    answer_equivalence,
    extract_answer_first,
    extract_final_answer,
)

POOLS_DIR = ROOT / "sample_data" / "external_hard_sets"
WRITE_LOCK = threading.Lock()
INTEGER_RE = re.compile(r"-?\d+")
SAMPLE_SIZE = 50
DOMAIN_FLOOR = 2

FAMILIES = {
    "set_a_olymmath_hard": "OlymMATH",
    "set_b_aime": "AIME",
    "set_c_hle_math": "HLE",
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


def normalize_answer(text: str) -> str:
    t = str(text or "").strip().strip("$").strip()
    t = t.replace("\\left", "").replace("\\right", "").replace("\\!", "").replace("\\,", "")
    t = t.replace("dfrac", "frac").replace("tfrac", "frac")
    t = re.sub(r"\\text\{[^}]*\}", "", t)
    t = re.sub(r"\s+", "", t)
    t = t.rstrip(".")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", t):
        t = t.replace(",", "")
    return t.lower()


def math_verify_ok(pred: str, gold: str) -> bool | None:
    """One-shot Math-Verify via the repo subprocess helper (Windows-safe)."""
    helper = ROOT / "scripts" / "_math_verify_once.py"
    payload = json.dumps({"pred": pred, "gold": gold})
    try:
        proc = subprocess.run(
            [sys.executable, str(helper), payload],
            capture_output=True, text=True, timeout=60, encoding="utf-8",
        )
        out = proc.stdout.strip()
        if not out:
            return None
        return bool(json.loads(out).get("ok"))
    except Exception:
        return None


def judge(pred: str, gold: str, family: str) -> dict[str, str]:
    """Official-style verdict: correct / incorrect / invalid + which check fired."""
    if not pred or pred.strip().upper() in {"UNKNOWN", "未能生成有效数学答案。"}:
        return {"verdict": "invalid", "detail": "empty_or_unknown"}
    if family == "AIME":
        matches = INTEGER_RE.findall(pred or "")
        if not matches:
            return {"verdict": "invalid", "detail": "pred_not_int"}
        try:
            ok = int(matches[-1]) == int(str(gold).strip())
        except ValueError:
            return {"verdict": "invalid", "detail": "gold_not_int"}
        return {"verdict": "correct" if ok else "incorrect", "detail": "aime_integer_exact"}
    if normalize_answer(pred) == normalize_answer(gold):
        return {"verdict": "correct", "detail": "normalized_string"}
    mv = math_verify_ok(pred, gold)
    if mv:
        return {"verdict": "correct", "detail": "math_verify"}
    if mv is None and re.fullmatch(r"-?\d+", normalize_answer(pred)) and normalize_answer(pred) == normalize_answer(gold):
        return {"verdict": "correct", "detail": "int_string"}
    equiv = answer_equivalence(pred, str(gold))
    if equiv == "EQUIVALENT":
        return {"verdict": "correct", "detail": "answer_equivalence"}
    return {"verdict": "incorrect", "detail": "no_check_matched"}


def contract_check(final_response: str, gold: str) -> dict[str, str]:
    """Strict submission-contract extraction on final_response only."""
    if not final_response or final_response.strip().upper() in {"UNKNOWN", "未能生成有效数学答案。"}:
        return {"verdict": "invalid"}
    extracted = extract_answer_first(final_response) or extract_final_answer(final_response) or ""
    if not extracted:
        return {"verdict": "invalid"}
    family_gold = str(gold)
    if normalize_answer(extracted) == normalize_answer(family_gold):
        return {"verdict": "correct"}
    mv = math_verify_ok(extracted, family_gold)
    if mv:
        return {"verdict": "correct"}
    equiv = answer_equivalence(extracted, family_gold)
    if equiv == "EQUIVALENT":
        return {"verdict": "correct"}
    return {"verdict": "incorrect"}


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
    "e_final_equals_d_candidate",
})

_STAGE_CLIENT_ERROR_CATEGORIES = frozenset({
    "model_error", "timeout", "rate_limit", "http_status", "request",
    "connectivity", "proxy", "tls", "configuration",
})


def compact_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: entry[k] for k in entry if k in TRACE_KEEP} for entry in trace]


def client_diagnostics(client: Any) -> dict[str, list[Any]]:
    """Per-task public client diagnostics (call-ordered, bounded).

    Each task owns its client, so the lists align with that task's calls even
    under workers=3.  Missing attributes degrade to empty lists instead of
    guessing from response text.
    """
    def bounded(name: str) -> list[Any]:
        values = getattr(client, name, None)
        if not isinstance(values, list):
            return []
        return list(values[:8])

    return {
        "finish_reasons": bounded("finish_reasons"),
        "completion_tokens": bounded("completion_tokens"),
    }


# ── Dual-arm support: same-window interleaved arms on the frozen pools ──
# `v1` is the untouched submission profile (FSDF v1 anchor).  `v2` turns on the
# four FSDF-RELIABILITY-V2 candidate flags on top of the same profile.  `v2hd`
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
)


def _arm_overrides(enabled: tuple[str, ...] = ()) -> dict[str, bool]:
    """Pin every candidate flag explicitly so arm semantics survive any
    future SUBMISSION_CONFIG drift (arms are defined relative to the
    submission profile with all candidate flags forced, not inherited)."""
    return {**{flag: False for flag in FSDF_CANDIDATE_FLAGS},
            **{flag: True for flag in enabled}}


ARM_DEFINITIONS: dict[str, dict[str, bool]] = {
    "v1": _arm_overrides(),
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
}


def arm_config(arm: str) -> Any:
    if arm not in ARM_DEFINITIONS:
        raise ValueError(f"unknown arm: {arm} (available: {', '.join(ARM_DEFINITIONS)})")
    return dataclasses.replace(SUBMISSION_CONFIG, **ARM_DEFINITIONS[arm])


# Per-arm client-level thinking switch: None = server default (env), False =
# thinking disabled for that arm's calls (see apply_thinking_mode probe:
# the default thinking pass consumed the whole completion budget inside the
# output stream).
ARM_THINKING_MODE: dict[str, bool | None] = {
    "v2hd_bs_hs_tkoff": False,
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

    The first arm rotates per item (item i starts with ``arms[i % k]``) so
    neither arm systematically runs first.  Resume keys already include the
    arm, so partial windows resume cleanly.
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
            paired.append(entry)
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
    contract = contract_check(final_response, item["answer"])
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
    format_ok = bool(
        isinstance(final_response, str) and final_response.strip()
        and final_response.strip().upper() != "UNKNOWN"
    )
    client_diag = client_diagnostics(client)
    return {
        "set_id": task["set_id"],
        "item_id": item["item_id"],
        "arm": arm,
        "pair_order": task.get("pair_order", ""),
        "thinking_mode": "off" if arm_thinking_mode(arm) is False else "default",
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
        "format_ok": format_ok,
        "json_serializable": serializable,
        "model_calls": calls,
        "duration_seconds": round(duration, 2),
        "trace": compact_trace_rows,
        "client_finish_reasons": client_diag["finish_reasons"],
        "client_completion_tokens": client_diag["completion_tokens"],
    }


def stage_health(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Separate counters for stage-level failures visible in compacted traces.

    A solve can return successfully while stages failed internally; these
    counts survive precisely because ``stage``/``error_category`` are kept in
    the compact trace.  Historical artifacts that already dropped fields are
    never back-filled.
    """
    counters = {
        "stage_client_errors": 0,
        "stage_invalid_responses": 0,
        "stage_protocol_failures": 0,
        "stage_skipped": 0,
        "handoff_missing": 0,
        "handoff_clipped": 0,
    }
    for row in rows:
        for event in row.get("trace") or []:
            status = event.get("status")
            category = event.get("error_category")
            if status == "failed":
                if category == "invalid_response":
                    counters["stage_invalid_responses"] += 1
                elif category in _STAGE_CLIENT_ERROR_CATEGORIES:
                    counters["stage_client_errors"] += 1
            elif status == "protocol_failed":
                counters["stage_protocol_failures"] += 1
            elif status == "skipped":
                counters["stage_skipped"] += 1
            if event.get("handoff_missing_fields"):
                counters["handoff_missing"] += 1
            if event.get("handoff_clipped"):
                counters["handoff_clipped"] += 1
    return counters


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"overall": {}, "by_set": {}}
    def stats(subset: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(subset)
        s: dict[str, Any] = {
            "n": n,
            "native_correct": sum(1 for r in subset if r["native"]["verdict"] == "correct"),
            "native_incorrect": sum(1 for r in subset if r["native"]["verdict"] == "incorrect"),
            "invalid": sum(1 for r in subset if r["native"]["verdict"] == "invalid"),
            "contract_correct": sum(1 for r in subset if r["contract"]["verdict"] == "correct"),
            "contract_incorrect": sum(1 for r in subset if r["contract"]["verdict"] == "incorrect"),
            "contract_invalid": sum(1 for r in subset if r["contract"]["verdict"] == "invalid"),
            "verdict_mismatch": sum(
                1 for r in subset
                if r.get("native", {}).get("verdict") != r.get("contract", {}).get("verdict")
            ),
            "format_ok": sum(1 for r in subset if r["format_ok"]),
            "serializable": sum(1 for r in subset if r["json_serializable"]),
            "model_error": sum(1 for r in subset if str(r["status"]).startswith("error")),
            "unknown_final": sum(
                1 for r in subset
                if str(r.get("final_response", "")).strip().upper() == "UNKNOWN"
            ),
            "mean_calls": round(sum(r["model_calls"] for r in subset) / n, 2) if n else 0,
            "max_calls": max((r["model_calls"] for r in subset), default=0),
            "mean_duration_s": round(sum(r["duration_seconds"] for r in subset) / n, 1) if n else 0,
            "p95_duration_s": round(sorted(r["duration_seconds"] for r in subset)[int(n * 0.95) - 1], 1) if n >= 20 else None,
        }
        s["native_accuracy"] = round(s["native_correct"] / n, 4) if n else 0
        # 完整判定对比：correct 数一致不代表逐题判定一致。
        s["correct_count_consistent"] = s["native_correct"] == s["contract_correct"]
        s.update(stage_health(subset))
        return s
    out["overall"] = stats(rows)
    out["judge_note"] = (
        "native 与 contract 均为本地近似判定（AIME 整数精确 / Math-Verify / 归一化字符串 / "
        "answer_equivalence / 严格抽取契约），不是真实官方 judger 的等价实现。"
    )
    arms = sorted({str(r.get("arm", "")) for r in rows} - {""})
    if arms:
        out["by_arm"] = {arm: stats([r for r in rows if str(r.get("arm")) == arm]) for arm in arms}
    by_domain: dict[str, dict[str, Any]] = {}
    for domain in sorted({r["domain"] for r in rows}):
        by_domain[domain] = stats([r for r in rows if r["domain"] == domain])
    out["by_domain"] = by_domain
    for set_id in sorted({r["set_id"] for r in rows}):
        subset = [r for r in rows if r["set_id"] == set_id]
        entry = stats(subset)
        entry["by_domain"] = {
            d: stats([r for r in subset if r["domain"] == d])
            for d in sorted({r["domain"] for r in subset})
        }
        entry["by_language"] = dict(Counter(r["language"] for r in subset))
        out["by_set"][set_id] = entry
    return out


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


def run(output_dir: Path, timeout: int, workers: int, seed: int, hard_stop_minutes: float,
        sample_size: int, sets: list[str], arms: list[str] | None = None,
        run_id: str = "EXTERNAL-HARD-SETS-SMOKE-001", pairing: str = "independent",
        thinking_mode: str = "default") -> None:
    arms = arms or ["v1"]
    for arm in arms:
        arm_config(arm)  # validate early
    if pairing not in ("independent", "paired"):
        raise SystemExit(f"unknown pairing mode: {pairing}")
    apply_thinking_mode(thinking_mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("INTERN_API_KEY", "")
    all_tasks: list[dict[str, Any]] = []
    sampled_manifest: dict[str, list[str]] = {}
    for set_id in sets:
        pool_path = POOLS_DIR / f"{set_id}.jsonl"
        rows = load_jsonl(pool_path)
        picked = sample_set(rows, set_id, seed, sample_size)
        if len(picked) != sample_size:
            raise SystemExit(f"{set_id}: sampled {len(picked)} != {sample_size}")
        sampled_manifest[set_id] = [r["item_id"] for r in picked]
        for i, item in enumerate(picked):
            all_tasks.append({"set_id": set_id, "item": item, "seed": seed, "task_idx": f"{set_id}-{i}"})
    rng = random.Random(seed)
    rng.shuffle(all_tasks)
    if pairing == "paired":
        all_tasks = assign_arms_paired(all_tasks, arms)
    else:
        assign_arms(all_tasks, arms)

    answers_path = output_dir / "answers.jsonl"
    done_keys: set[tuple[str, str, str]] = set()
    if answers_path.exists():
        for row in load_jsonl(answers_path):
            done_keys.add((row["set_id"], row["item_id"], str(row.get("arm", ""))))
    pending = [
        t for t in all_tasks
        if (t["set_id"], t["item"]["item_id"], t["arm"]) not in done_keys
    ]

    manifest = {
        "run_id": run_id,
        "pools_dir": str(POOLS_DIR.relative_to(ROOT)).replace("\\", "/"),
        "pool_sha256": {p.name: sha256_file(p) for p in sorted(POOLS_DIR.glob("*.jsonl"))},
        "seed": seed,
        "workers": workers,
        "request_timeout_seconds": timeout,
        "hard_stop_minutes": hard_stop_minutes,
        "sample_size_per_set": sample_size,
        "sampled_items": sampled_manifest,
        "arms": arms,
        "arm_assignment": "round_robin_over_seeded_shuffle",
        "pairing": pairing,
        "thinking_mode": thinking_mode,
        "arm_flags": {arm: dict(ARM_DEFINITIONS[arm]) for arm in arms},
        "method": (
            "SUBMISSION_CONFIG base (fork_select_deepen_finish_v1); arms add "
            "FSDF-RELIABILITY-V2 candidate flags (exploratory diagnostic, "
            "not per-variable attributable, no capability conclusion)"
        ),
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "start_unix": time.time(),
        "n_tasks": len(all_tasks),
        "n_pending": len(pending),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[EXT-SMOKE] run_id={run_id} pending={len(pending)} workers={workers} seed={seed} arms={','.join(arms)}", flush=True)

    start = time.time()

    def job(task: dict[str, Any]) -> dict[str, Any]:
        if (time.time() - start) > hard_stop_minutes * 60:
            return {"skipped": True, "reason": "hard_stop", "set_id": task["set_id"], "item_id": task["item"]["item_id"]}
        record = solve_one(task, timeout, api_key)
        with WRITE_LOCK:
            with answers_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
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
    summary["dataset_info"] = {"pools_dir": str(POOLS_DIR), "seed": seed, "sample_size_per_set": sample_size}
    summary["window_note"] = (
        "diagnostic window; thresholds unfrozen; combined v2 arm is exploratory "
        "and supports no capability conclusion or promotion"
    )
    (output_dir / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary.get("by_arm", summary["by_set"]), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "docs" / "experiments" / "EXTERNAL-HARD-SETS-SMOKE-001"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--hard-stop-minutes", type=float, default=300.0)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--sets", default="set_a_olymmath_hard,set_b_aime,set_c_hle_math")
    parser.add_argument("--arms", default="v1", help="comma list from: v1,v2,v2hd,v2hd_dre (interleaved round-robin)")
    parser.add_argument("--pairing", default="independent", choices=["independent", "paired"],
                        help="paired: every sampled item runs once per arm with rotated first arm")
    parser.add_argument("--thinking-mode", default="default", choices=["default", "false", "true"],
                        help="client-side thinking switch (default = server default)")
    parser.add_argument("--run-id", default="EXTERNAL-HARD-SETS-SMOKE-001")
    args = parser.parse_args()
    run(
        Path(args.output_dir), args.timeout, args.workers, args.seed,
        args.hard_stop_minutes, args.sample_size,
        [s.strip() for s in args.sets.split(",") if s.strip()],
        arms=[a.strip() for a in args.arms.split(",") if a.strip()],
        run_id=args.run_id,
        pairing=args.pairing,
        thinking_mode=args.thinking_mode,
    )
