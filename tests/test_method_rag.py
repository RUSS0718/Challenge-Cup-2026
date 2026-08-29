import unittest
from pathlib import Path

from experiments.legacy.method_rag import MethodCardRetriever


class MethodCardRetrieverTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.retriever = MethodCardRetriever(
            root / "experiments" / "legacy" / "method_rag" / "method_cards.jsonl"
        )

    def test_retrieves_relevant_number_theory_card(self):
        cards = self.retriever.search("素数模 指数 同余", top_k=2)
        self.assertTrue(cards)
        self.assertEqual("number_theory_fermat", cards[0]["id"])

    def test_retrieves_probability_card(self):
        cards = self.retriever.search("独立试验 恰好 k 次 成功概率", top_k=2)
        self.assertTrue(cards)
        self.assertEqual("probability_binomial", cards[0]["id"])

    def test_empty_or_invalid_query_is_safe(self):
        self.assertEqual([], self.retriever.search("", top_k=2))
        self.assertEqual([], self.retriever.search("anything", top_k=0))

    def test_chinese_retrieval_uses_phrases_not_single_character_overlap(self):
        tokens = self.retriever._tokenize("固定和时乘积最大")
        self.assertIn("固定", tokens)
        self.assertIn("乘积", tokens)
        self.assertNotIn("固", tokens)

    def test_card_catalog_has_40_unique_complete_cards(self):
        self.assertEqual(40, len(self.retriever.cards))
        self.assertEqual(40, len({card["id"] for card in self.retriever.cards}))
        for card in self.retriever.cards:
            for field in ("title", "signals", "method", "conditions", "pitfalls", "example"):
                self.assertTrue(str(card.get(field, "")).strip(), (card.get("id"), field))

    def test_cards_do_not_contain_evaluator_answer_fields_or_holdout_ids(self):
        holdout_ids = {str(index) for index in range(6000, 6300)}
        for card in self.retriever.cards:
            self.assertNotIn("answer", card)
            self.assertNotIn("idx", card)
            for value in card.values():
                self.assertNotIn(str(value), holdout_ids)


if __name__ == "__main__":
    unittest.main()
