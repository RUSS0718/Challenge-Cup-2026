import json
import unittest
from pathlib import Path

from method_rag import MethodCardRetriever
from scripts.evaluate_method_rag import evaluate


class MethodRagEvaluationTest(unittest.TestCase):
    def test_pilot_cases_have_retrieval_coverage(self):
        root = Path(__file__).resolve().parents[1]
        cases = [json.loads(line) for line in (root / "method_rag_eval_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        report = evaluate(MethodCardRetriever(root / "method_cards.jsonl"), cases, top_k=2)
        self.assertEqual(len(cases), report["total"])
        self.assertGreaterEqual(report["coverage"], 0.9)


if __name__ == "__main__":
    unittest.main()
