"""P1 baseline dual-scope analysis (LOCAL_CACHE_ONLY run files).

Per row:
  contract = extract_final_answer(final_response) + evaluate_dev.judge_correct
             (spec §4.3; falls back to agent extracted_answer for legacy rows)
  native   = component-aware: MATH/OlymMATH -> math-verify(gold, pred);
             AIME/GSM-numeric -> integer/numeric exact; critical-thinking -> not scored
Aggregates per component per round + core120 run-to-run variance.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from user_agent import extract_final_answer  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402

RUNS = REPO_ROOT / "docs" / "experiments" / "P1_BASELINE" / "runs"
REGISTRY = json.loads((REPO_ROOT / "docs" / "experiments" / "P1_BASELINE" / "run_registry.json").read_text(encoding="utf-8"))
RUN = REPO_ROOT / "tmp" / "p1_data" / "run"


def native_math_verify(gold: str, extracted: str) -> str:
    from math_verify import parse, verify

    if not extracted.strip():
        return "unparseable"
    try:
        pred = parse(f"${extracted}$", parsing_timeout=None)
        if not pred:
            return "unparseable"
        g = parse(f"${gold}$", parsing_timeout=None)
        if not g:
            return "unparseable"
    except Exception as exc:  # noqa: BLE001
        return f"crash:{type(exc).__name__}"
    return "correct" if verify(g, pred, timeout_seconds=None) else "incorrect"


def native_integer_exact(gold: str, extracted: str) -> str:
    if not extracted.strip():
        return "unparseable"
    m = re.search(r"-?\d+", extracted.replace(",", ""))
    if not m:
        return "unparseable"
    try:
        return "correct" if int(m.group()) == int(gold) else "incorrect"
    except ValueError:
        return "unparseable"


def native_numeric_exact(gold: str, extracted: str) -> str:
    if not extracted.strip():
        return "unparseable"
    m = re.search(r"-?\d+(?:\.\d+)?", extracted.replace(",", ""))
    if not m:
        return "unparseable"
    try:
        value = float(m.group())
        target = float(gold)
    except ValueError:
        return "unparseable"
    return "correct" if abs(value - target) < 1e-6 * max(1.0, abs(target)) else "incorrect"


def native_for_component(component: str) -> "object":
    if component in ("core120_v2_math500", "core120_v2_olympmath40"):
        return native_math_verify
    if component in ("confirm_aim2024_anchor", "confirm30_v2_aim2025"):
        return native_integer_exact
    return native_numeric_exact


def load_layeranswers(paths: list[Path]) -> dict:
    rows = []
    for path in paths:
        if not path.is_file():
            return {}
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def analyse_layer(name: str, dataset_file: str, answer_files: list[Path], rounds: list[int]) -> dict:
    dataset = {r["idx"]: r for r in
               (json.loads(line) for line in (RUN / dataset_file).read_text(encoding="utf-8").splitlines() if line.strip())}
    rows = load_layeranswers(answer_files)
    if not rows:
        return {"status": "missing_artifacts"}

    items = []
    for row in rows:
        meta = dataset.get(row["idx"], {})
        component = meta.get("component", name)
        gold = str(meta.get("answer", ""))
        answer_type = meta.get("answer_type", "numeric")
        final_response = row.get("final_response")
        if final_response is not None:
            external = extract_final_answer(final_response)
            source = "final_response_external_extraction"
        else:
            external = row.get("extracted_answer", "")
            source = "agent_extracted_answer (legacy)"
        contract = judge_correct(external, gold, "calculation") if external.strip() else "unparseable"
        is_ct = answer_type == "critical_thinking"
        if is_ct:
            native = "not_scored"
        elif row.get("result_status") == "error":
            native = "error"
        else:
            native = native_for_component(component)(gold, external)
        items.append({
            "round": row["round"], "idx": row["idx"], "component": component,
            "result_status": row.get("result_status"), "answer_type": answer_type,
            "contract_source": source, "contract_verdict": contract,
            "native_verdict": native, "model_calls": row.get("model_calls"),
            "latency_seconds": row.get("latency_seconds"),
            "total_completion_tokens": row.get("total_completion_tokens"),
        })

    aggregates = {}
    for round_no in rounds:
        r_rows = [i for i in items if i["round"] == round_no]
        per_component: dict[str, dict] = {}
        for component in sorted({i["component"] for i in r_rows}):
            c_rows = [i for i in r_rows if i["component"] == component]
            numeric = [i for i in c_rows if i["answer_type"] != "critical_thinking"]
            per_component[component] = {
                "rows": len(c_rows),
                "errors": sum(1 for i in c_rows if i["result_status"] == "error"),
                "invalid": sum(1 for i in c_rows if i["result_status"] == "invalid"),
                "contract_correct": sum(1 for i in numeric if i["contract_verdict"] == "correct"),
                "native_correct": sum(1 for i in numeric if i["native_verdict"] == "correct"),
                "native_unparseable": sum(1 for i in numeric if i["native_verdict"] == "unparseable"),
                "native_crashes": sum(1 for i in numeric if str(i["native_verdict"]).startswith("crash")),
                "critical_thinking_rows": len(c_rows) - len(numeric),
                "mean_calls": round(statistics.mean([i["model_calls"] or 0 for i in c_rows]), 3),
                "mean_latency": round(statistics.mean([i["latency_seconds"] or 0 for i in c_rows]), 1),
                "mean_tokens": round(statistics.mean([i["total_completion_tokens"] or 0 for i in c_rows]), 1),
            }
        aggregates[f"round{round_no}"] = per_component

    return {
        "status": "ok",
        "aggregates": aggregates,
        "diffset_contract_vs_native": [
            {"round": i["round"], "idx": i["idx"], "component": i["component"],
             "contract": i["contract_verdict"], "native": i["native_verdict"]}
            for i in items if i["contract_verdict"] != i["native_verdict"]
        ],
        "items": items,
    }


def run_to_run_variance(core: dict) -> dict:
    items = core.get("items", [])
    by_idx: dict[int, dict[int, str]] = {}
    for i in items:
        if i["result_status"] == "error":
            verdict = "error"
        else:
            verdict = i["native_verdict"]
        by_idx.setdefault(i["idx"], {})[i["round"]] = verdict
    both = sum(1 for v in by_idx.values() if len(v) == 2 and all(x == "correct" for x in v.values()))
    neither = sum(1 for v in by_idx.values() if len(v) == 2 and all(x != "correct" for x in v.values()))
    flipped = len(by_idx) - both - neither
    return {"items": len(by_idx), "correct_both_rounds": both,
            "correct_neither_rounds": neither, "flipped_across_rounds": flipped}


def main() -> None:
    layers = {
        "core120_v2": ("core120_v2.jsonl", ["core120_answers.jsonl"], [1, 2]),
        "confirm30_v2": ("confirm30_v2_aim2025.jsonl", ["confirm30_answers.jsonl"], [1]),
        "robust_smoke": ("robust_smoke_2seeds.jsonl", ["robust_smoke_answers.jsonl"], [1]),
    }
    output = {"analysed_utc": datetime.now(timezone.utc).isoformat(), "layers": {}}
    for name, (dataset_file, answer_names, rounds) in layers.items():
        paths = [RUNS / a for a in answer_names]
        output["layers"][name] = analyse_layer(name, dataset_file, paths, rounds)
    output["layers"]["core120_v2"]["run_to_run_variance_native"] = run_to_run_variance(
        output["layers"]["core120_v2"])
    out_path = REPO_ROOT / "docs" / "experiments" / "P1_BASELINE" / "p1_baseline_analysis.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {}
    for name, layer in output["layers"].items():
        if layer.get("status") != "ok":
            summary[name] = layer.get("status")
            continue
        summary[name] = {
            f"r{r}": {c: {k: v for k, v in comp.items() if k in
                          ("rows", "errors", "contract_correct", "native_correct", "mean_calls")}
                      for c, comp in agg.items()}
            for r, agg in layer["aggregates"].items()
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
