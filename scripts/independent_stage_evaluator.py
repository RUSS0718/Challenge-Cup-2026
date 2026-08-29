"""Independent stage evaluator for the local enhancement plan.

This process checks artifacts and gates without calling the model.  It cannot
claim RAG answer gains; that stage remains pending until valid A/B reports exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.legacy.method_rag import MethodCardRetriever
from scripts.evaluate_deterministic_gate import gate as deterministic_gate
from scripts.evaluate_method_rag import evaluate as evaluate_retrieval
from scripts.validate_medium_freeze_set import validate as validate_freeze


ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_stage(
    deterministic_round1: dict[str, Any],
    deterministic_round2: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    freeze_path = ROOT / "sample_data" / "medium_capability_freeze_60.jsonl"
    freeze_errors = validate_freeze(freeze_path, require_public_sources=True)
    if freeze_errors:
        failures.extend(f"freeze:{error}" for error in freeze_errors)

    det = deterministic_gate(deterministic_round1, deterministic_round2)
    if not det["passed"]:
        failures.extend(f"deterministic:{error}" for error in det["failures"])

    data_root = ROOT / "experiments" / "legacy" / "method_rag"
    retriever = MethodCardRetriever(data_root / "method_cards.jsonl")
    cases = [json.loads(line) for line in (data_root / "method_rag_eval_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    retrieval = evaluate_retrieval(retriever, cases, top_k=2)
    if len(retriever.cards) != 40:
        failures.append(f"rag:card_count:{len(retriever.cards)}")
    if retrieval["coverage"] < 0.9:
        failures.append(f"rag:retrieval_coverage:{retrieval['coverage']}")

    # The real model A/B is intentionally represented as a hard pending gate.
    failures.append("rag:model_ab_missing")
    return {
        "overall_passed": not failures,
        "stage1_freeze_passed": not bool(freeze_errors),
        "stage2_deterministic_passed": det["passed"],
        "stage3_retrieval_passed": len(retriever.cards) == 40 and retrieval["coverage"] >= 0.9,
        "stage3_model_ab_passed": False,
        "failures": failures,
        "deterministic": det,
        "retrieval": retrieval,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round1", type=Path)
    parser.add_argument("round2", type=Path)
    args = parser.parse_args()
    result = evaluate_stage(_load_json(args.round1), _load_json(args.round2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
