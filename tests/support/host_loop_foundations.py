"""Shared evaluators for Host Loop foundations contract cases."""

from __future__ import annotations

import json
import random
import time
from typing import Any

from reasoning_agent.fesf_obligations import extract_bounded_obligations
from reasoning_agent.fesf_verifiers import (
    CounterexampleAdapter,
    FiniteDomainAdapter,
    SymbolicConstraintAdapter,
    VerificationResult,
)
from reasoning_agent.host_intake import (
    build_host_intake,
    estimate_complexity,
    normalize_problem,
    sanitize_metadata,
)
from tests.support.host_loop_foundations_cases import (
    COUNTEREXAMPLE_CASES,
    FINITE_CASES,
    INTAKE_CASES,
    OBLIGATION_CASES,
    SEED,
    SYMBOLIC_CASES,
)

ALLOWED_STATUSES = frozenset({"EXACT", "REFUTED", "UNKNOWN"})


def evaluate_intake_case(case: dict[str, Any]) -> dict[str, Any]:
    kind = case.get("kind")
    if kind == "normalize":
        actual = normalize_problem(case["problem"])
        return {"id": case["id"], "ok": actual == case["expect"], "expected": case["expect"], "actual": actual}
    if kind == "error":
        fn = case.get("fn", "normalize")
        try:
            if fn == "normalize":
                normalize_problem(case["problem"])
            elif fn == "complexity":
                estimate_complexity(case["problem"])
            else:
                build_host_intake(case["problem"], answer_type=case.get("answer_type", ""))
        except Exception as exc:
            actual = str(exc)
            return {"id": case["id"], "ok": actual == case["error"], "expected": case["error"], "actual": actual}
        return {"id": case["id"], "ok": False, "expected": case["error"], "actual": "no_error"}
    if kind == "metadata":
        clean, reasons = sanitize_metadata(case["metadata"])
        if "expect_keys" in case and set(clean) != set(case["expect_keys"]):
            return {"id": case["id"], "ok": False, "expected": sorted(case["expect_keys"]), "actual": sorted(clean)}
        if "expect_reasons" in case and list(reasons) != list(case["expect_reasons"]):
            return {"id": case["id"], "ok": False, "expected": case["expect_reasons"], "actual": list(reasons)}
        if "expect_reasons_contains" in case and case["expect_reasons_contains"] not in reasons:
            return {"id": case["id"], "ok": False, "expected": case["expect_reasons_contains"], "actual": list(reasons)}
        forbidden = case.get("forbidden")
        blob = json.dumps({"metadata": clean, "reasons": reasons}, ensure_ascii=False)
        if forbidden and forbidden in blob:
            return {"id": case["id"], "ok": False, "expected": "no_secret", "actual": blob}
        return {"id": case["id"], "ok": True, "actual": {"metadata": clean, "reasons": list(reasons)}}
    if kind == "intake_profile":
        intake = build_host_intake(case["problem"], {})
        actual = {
            "profile": intake.complexity.profile,
            "proof": intake.complexity.has_proof_language,
            "universal": intake.complexity.has_universal_language,
            "parts": intake.complexity.has_multiple_parts,
        }
        expected = {
            "profile": case["profile"],
            "proof": case.get("proof", False),
            "universal": case.get("universal", False),
            "parts": case.get("parts", False),
        }
        return {"id": case["id"], "ok": actual == expected, "expected": expected, "actual": actual}
    if kind == "intake_secret":
        blob = json.dumps(build_host_intake(case["problem"], case["metadata"]).as_dict(), ensure_ascii=False)
        return {"id": case["id"], "ok": case["forbidden"] not in blob}
    if kind == "repeat":
        first = json.dumps(build_host_intake(case["problem"], case["metadata"]).as_dict(), ensure_ascii=False, separators=(",", ":"))
        for _ in range(case.get("repeats", 20)):
            again = json.dumps(build_host_intake(case["problem"], case["metadata"]).as_dict(), ensure_ascii=False, separators=(",", ":"))
            if again != first:
                return {"id": case["id"], "ok": False, "expected": first, "actual": again}
        return {"id": case["id"], "ok": True}
    raise ValueError(case["id"])


def evaluate_obligation_case(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("kind") == "error":
        try:
            extract_bounded_obligations(case["problem"])
        except Exception as exc:
            actual = str(exc)
            return {"id": case["id"], "ok": actual == case["error"], "expected": case["error"], "actual": actual}
        return {"id": case["id"], "ok": False, "expected": case["error"], "actual": "no_error"}
    result = extract_bounded_obligations(case["problem"], max_items=case.get("max_items", 8))
    actual_kinds = [item.kind for item in result.obligations]
    if "kinds" in case and actual_kinds != list(case["kinds"]):
        return {"id": case["id"], "ok": False, "expected": case["kinds"], "actual": actual_kinds}
    if "states" in case and [item.state for item in result.obligations] != list(case["states"]):
        return {"id": case["id"], "ok": False, "expected": case["states"], "actual": [item.state for item in result.obligations]}
    if "ids" in case and [item.id for item in result.obligations] != list(case["ids"]):
        return {"id": case["id"], "ok": False, "expected": case["ids"], "actual": [item.id for item in result.obligations]}
    if "max_len" in case and len(result.obligations) != case["max_len"]:
        return {"id": case["id"], "ok": False, "expected": case["max_len"], "actual": len(result.obligations)}
    if "truncated" in case and result.truncated != case["truncated"]:
        return {"id": case["id"], "ok": False, "expected": case["truncated"], "actual": result.truncated}
    if len(result.obligations) > 8:
        return {"id": case["id"], "ok": False, "expected": "<=8", "actual": len(result.obligations)}
    first = json.dumps(result.as_dict(), ensure_ascii=False, separators=(",", ":"))
    for _ in range(20):
        again = json.dumps(extract_bounded_obligations(case["problem"], max_items=case.get("max_items", 8)).as_dict(), ensure_ascii=False, separators=(",", ":"))
        if again != first:
            return {"id": case["id"], "ok": False, "expected": first, "actual": again}
    return {"id": case["id"], "ok": True, "actual": actual_kinds}


def _run_symbolic(case: dict[str, Any]) -> VerificationResult:
    adapter = SymbolicConstraintAdapter()
    if case.get("op") == "rel":
        return adapter.check_relation(case["left"], case.get("relation", "=="), case["right"], claim_id=case["id"], assumptions=case.get("assumptions", ()))
    return adapter.check_equivalence(case["left"], case["right"], case["id"], assumptions=case.get("assumptions", ()))


def _check_result(case: dict[str, Any], result: VerificationResult, started: float) -> dict[str, Any]:
    elapsed = time.monotonic() - started
    if elapsed > 5.0:
        return {"id": case["id"], "ok": False, "gate": "RESOURCE_GATE_FAIL", "elapsed": elapsed}
    json.dumps(result.as_dict(), ensure_ascii=False)
    if result.status not in ALLOWED_STATUSES or len(result.claim_id) > 32:
        return {"id": case["id"], "ok": False, "expected": case["status"], "actual": result.status}
    if result.status != case["status"]:
        return {"id": case["id"], "ok": False, "expected": case["status"], "actual": result.status, "error": result.error}
    if "witness" in case and result.witness != case["witness"]:
        return {"id": case["id"], "ok": False, "expected": case["witness"], "actual": result.witness}
    return {"id": case["id"], "ok": True, "status": result.status, "elapsed": elapsed, "result": result.as_dict()}


def evaluate_symbolic_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    return _check_result(case, _run_symbolic(case), started)


def evaluate_finite_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    return _check_result(case, FiniteDomainAdapter().check_all(case["var"], case["pred"], case["values"], claim_id=case["id"]), started)


def evaluate_counterexample_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    result = CounterexampleAdapter().find(case["var"], case["pred"], case["values"], claim_id=case["id"])
    checked = _check_result(case, result, started)
    if result.status == "EXACT":
        checked["ok"] = False
        checked["gate"] = "false_proof"
    return checked


def _fuzz_expr(rng: random.Random) -> str:
    atoms = ["x", "y", "0", "1", "2", "3"]
    expr = rng.choice(atoms)
    for _ in range(rng.randint(0, 3)):
        op = rng.choice(["+", "-", "*", "/", "**"])
        rhs = str(rng.randint(0, 4)) if op == "**" else rng.choice(atoms + [str(rng.randint(-3, 3))])
        expr = f"({expr}{op}{rhs})"
    return expr


def generate_fuzz_cases(count: int = 300, seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    cases: list[dict[str, Any]] = []
    adapters = ["symbolic", "finite", "counterexample"]
    for index in range(count):
        adapter = adapters[index % 3]
        if adapter == "symbolic":
            cases.append({"id": f"Z{index:03d}", "adapter": adapter, "left": _fuzz_expr(rng), "right": _fuzz_expr(rng), "relation": rng.choice(["==", "!=", "<", "<=", ">", ">="])})
        else:
            pred_left = rng.choice(["x", "x+1", "x*x", "x%2", "1/x", "x**2"])
            pred = f"{pred_left} {rng.choice(['==', '!=', '<', '<=', '>', '>='])} {rng.choice(['0', '1', '2', 'x'])}"
            cases.append({"id": f"Z{index:03d}", "adapter": adapter, "var": "x", "pred": pred, "values": [rng.randint(-4, 4) for _ in range(rng.randint(0, 8))]})
    return cases


def evaluate_fuzz_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    if case["adapter"] == "symbolic":
        first = SymbolicConstraintAdapter().check_relation(case["left"], case["relation"], case["right"], claim_id=case["id"])
        second = SymbolicConstraintAdapter().check_relation(case["left"], case["relation"], case["right"], claim_id=case["id"])
    elif case["adapter"] == "finite":
        first = FiniteDomainAdapter().check_all(case["var"], case["pred"], case["values"], claim_id=case["id"])
        second = FiniteDomainAdapter().check_all(case["var"], case["pred"], case["values"], claim_id=case["id"])
    else:
        first = CounterexampleAdapter().find(case["var"], case["pred"], case["values"], claim_id=case["id"])
        second = CounterexampleAdapter().find(case["var"], case["pred"], case["values"], claim_id=case["id"])
    elapsed = time.monotonic() - started
    encoded = json.dumps(first.as_dict(), ensure_ascii=False, separators=(",", ":"))
    encoded_again = json.dumps(second.as_dict(), ensure_ascii=False, separators=(",", ":"))
    ok = first.status in ALLOWED_STATUSES and encoded == encoded_again and elapsed <= 5.0 and (case["adapter"] != "counterexample" or first.status != "EXACT")
    return {"id": case["id"], "ok": ok, "status": first.status, "elapsed": elapsed, "adapter": case["adapter"], "case": case}


def all_contract_results() -> list[dict[str, Any]]:
    rows = []
    for family, cases, fn in (
        ("intake", INTAKE_CASES, evaluate_intake_case),
        ("obligation", OBLIGATION_CASES, evaluate_obligation_case),
        ("symbolic", SYMBOLIC_CASES, evaluate_symbolic_case),
        ("finite", FINITE_CASES, evaluate_finite_case),
        ("counterexample", COUNTEREXAMPLE_CASES, evaluate_counterexample_case),
    ):
        for case in cases:
            row = fn(case)
            row["family"] = family
            rows.append(row)
    return rows
