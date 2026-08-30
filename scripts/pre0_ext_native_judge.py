"""PRE0-EXT-001: dual-scope judging after the smoke run.

Reads the runner's compact answers (contract verdict via evaluate_dev.judge_correct)
and re-judges each extracted answer with the fixed native evaluator
(math-verify 0.8.0, verify(gold, pred), parse wrapped in $...$, timeouts
disabled for Windows).  Emits per-item dual verdicts, the contract/native
diffset, answer types, invalid and timing aggregates.  No accuracy gate.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from user_agent import extract_final_answer  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402

WORKTREE = REPO_ROOT / ".worktrees" / "main-integration-20260829"
import sys as _sys

_ANSWERS = Path(_sys.argv[1]) if len(_sys.argv) > 1 else Path("docs/experiments/PRE0-EXT-001/pre0_ext_answers.jsonl")
ANSWERS = _ANSWERS if _ANSWERS.is_absolute() else REPO_ROOT / _ANSWERS
REPORT = ANSWERS.with_name(ANSWERS.stem.replace("_answers", "_report") + ".json")
DATASET = REPO_ROOT / "tmp" / "pre0_ext_001" / "cache" / "ext12_run.jsonl"
EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-EXT-001"


def native_verdict(gold: str, extracted: str) -> tuple[str, str]:
    from math_verify import parse, verify

    if not extracted.strip():
        return "unparseable", ""
    try:
        pred = parse(f"${extracted}$", parsing_timeout=None)
        if not pred:
            return "unparseable", ""
        gold_parsed = parse(f"${gold}$", parsing_timeout=None)
        if not gold_parsed:
            return "unparseable", "gold_unparseable"
        result = verify(gold_parsed, pred, timeout_seconds=None)
    except Exception as exc:  # noqa: BLE001
        return f"crash:{type(exc).__name__}", str(exc)[:80]
    return ("correct" if result else "incorrect"), ""


def main() -> None:
    golds = {}
    meta = {}
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            golds[item["idx"]] = item["answer"]
            meta[item["idx"]] = {key: item[key] for key in
                                 ("unique_id", "problem_group_id", "subject", "subject_en",
                                  "difficulty", "language", "answer_type")}

    rows = [json.loads(line) for line in ANSWERS.read_text(encoding="utf-8").splitlines() if line.strip()]
    judged = []
    diffset = []
    crashes = 0
    for row in rows:
        idx = row["idx"]
        gold = golds.get(idx, "")
        # S1 fix: contract score re-extracts from final_response (spec §4.3);
        # fall back to the runner's internal extracted_answer only when the
        # artifact predates the final_response field (PRE0-EXT-001 2b).
        final_response = row.get("final_response")
        if final_response is not None:
            external = extract_final_answer(final_response)
            contract_source = "final_response_external_extraction"
        else:
            external = row.get("extracted_answer", "")
            contract_source = "agent_extracted_answer (legacy artifact)"
        contract = judge_correct(external, gold, "calculation") if external.strip() else "unparseable"
        native, note = native_verdict(gold, external)
        if native.startswith("crash"):
            crashes += 1
        entry = {
            "idx": idx, **meta.get(idx, {}),
            "contract_source": contract_source,
            "extracted_answer": row.get("extracted_answer", ""),
            "external_extraction": external,
            "result_status": row.get("result_status"),
            "model_calls": row.get("model_calls"),
            "latency_seconds": row.get("latency_seconds"),
            "contract_verdict": contract,
            "native_verdict": native,
            "native_note": note,
        }
        if contract != native:
            diffset.append({"idx": idx, "contract": contract, "native": native})
        judged.append(entry)

    completed = sum(1 for row in rows if row.get("result_status") != "error")
    errors = sum(1 for row in rows if row.get("result_status") == "error")
    invalid = sum(1 for row in rows if row.get("result_status") == "invalid")

    output = {
        "experiment": "PRE0-EXT-001",
        "judged_utc": datetime.now(timezone.utc).isoformat(),
        "model_calls_used_by_agent": sum(row.get("model_calls", 0) for row in rows),
        "aggregates": {"completed": completed, "model_errors": errors, "invalid": invalid,
                       "total_rows": len(rows)},
        "native_judge_crashes": crashes,
        "diffset": diffset,
        "items": judged,
    }
    out_path = ANSWERS.with_name(ANSWERS.stem.replace("_answers", "_dual_judgement") + ".json")
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["aggregates"], ensure_ascii=False))
    print("diffset:", json.dumps(diffset, ensure_ascii=False))
    for item in judged:
        print(item["idx"], item["unique_id"], item["answer_type"], item["result_status"],
              "contract:", item["contract_verdict"], "native:", item["native_verdict"],
              f"calls={item['model_calls']}", f"lat={item['latency_seconds']}s")
    sys.exit(0 if completed == 12 and errors == 0 and crashes == 0 else 1)


if __name__ == "__main__":
    main()
