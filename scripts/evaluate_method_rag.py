"""Offline evaluator for method-card retrieval coverage.

It deliberately does not score model answers.  A passing retrieval score is
only a prerequisite for a later model A/B experiment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.legacy.method_rag import MethodCardRetriever


def evaluate(retriever: MethodCardRetriever, cases: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    records = []
    for case in cases:
        cards = retriever.search(str(case.get("query", "")), top_k=top_k)
        ids = [str(card.get("id", "")) for card in cards]
        expected = str(case.get("expected_id", ""))
        records.append({"query": case.get("query"), "expected_id": expected, "retrieved_ids": ids, "hit": expected in ids})
    hits = sum(1 for record in records if record["hit"])
    return {"total": len(records), "hits": hits, "coverage": hits / len(records) if records else 0.0, "top_k": top_k, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument(
        "--cards", type=Path,
        default=Path("experiments/legacy/method_rag/method_cards.jsonl"),
    )
    parser.add_argument("--top-k", type=int, default=2)
    args = parser.parse_args()
    with args.cases.open("r", encoding="utf-8") as handle:
        cases = [json.loads(line) for line in handle if line.strip()]
    print(json.dumps(evaluate(MethodCardRetriever(args.cards), cases, args.top_k), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
