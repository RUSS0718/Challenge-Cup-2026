import json
import unittest

from reference_rag import ReferenceRagRetriever, render_reference_context
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, problem, top_k):
        self.calls.append((problem, top_k))
        return self.rows


class ReferenceRagTest(unittest.TestCase):
    def test_submission_profile_disables_reference_rag_and_skills(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_reference_rag)
        self.assertFalse(SUBMISSION_CONFIG.enable_reference_skills)
        self.assertFalse(SUBMISSION_CONFIG.enable_temporary_answer_bank)

    def test_semantic_retriever_keeps_medium_and_high_matches(self):
        database = FakeDatabase([
            {"id": "high", "problem": "求最大值，参数 100。", "answer": "", "solution": "先使用不等式。", "similarity": 0.93},
            {"id": "medium", "problem": "求最大值，参数 80。", "answer": "", "solution": "转化为边界问题。", "similarity": 0.71},
        ])
        rows = ReferenceRagRetriever(database).search("求最大值，参数 99。", top_k=2)
        self.assertEqual(["high", "medium"], [row["id"] for row in rows])
        self.assertEqual(24, database.calls[0][1])

    def test_low_similarity_and_empty_query_degrade(self):
        database = FakeDatabase([
            {"id": "low", "problem": "概率题", "answer": "", "solution": "方法", "similarity": 0.64},
        ])
        retriever = ReferenceRagRetriever(database)
        self.assertEqual([], retriever.search("概率题"))
        self.assertEqual([], retriever.search(""))

    def test_exact_query_is_not_returned_as_a_reference(self):
        database = FakeDatabase([
            {"id": "same", "problem": "求 100 的值。", "answer": "100", "solution": "直接计算。", "similarity": 0.99},
            {"id": "other", "problem": "求 101 的值。", "answer": "101", "solution": "直接计算。", "similarity": 0.80},
        ])
        rows = ReferenceRagRetriever(database).search("求 100 的值。", top_k=2)
        self.assertEqual(["other"], [row["id"] for row in rows])

    def test_context_is_bounded_and_anti_anchors_parameters(self):
        context = render_reference_context(
            "求 1997 个对象的最大数量。",
            [{"problem": "求 2020 个对象的最大数量。", "solution": "结论" * 500, "similarity": 0.91}],
            max_chars=180,
        )
        self.assertLessEqual(len(context), 180)
        self.assertIn("不能直接搬用", context)
        json.dumps({"context": context}, ensure_ascii=False)

    def test_default_harness_receives_reference_context(self):
        class Client:
            def __init__(self):
                self.calls = []

            def chat(self, messages, temperature, max_tokens):
                self.calls.append(messages)
                return "答案是 4"

        class Retriever:
            def search(self, query, top_k):
                return [{
                    "id": "ref-1",
                    "problem": "求 5+5。",
                    "solution": "直接计算。",
                    "similarity": 0.8,
                }]

        client = Client()
        config = AgentConfig(
            enable_constraint_fit_harness=True,
            enable_reference_rag=True,
            enable_temporary_answer_bank=False,
            enable_constraint_fit_deep_lane=False,
        )
        result = ReasoningAgent(
            client,
            config,
            reference_rag_retriever=Retriever(),
        ).solve("计算 2+2", {})
        self.assertEqual("4", result["final_response"])
        self.assertIn("相似题参考", client.calls[0][1]["content"])
        self.assertEqual("used", result["trace"][0]["status"])

    def test_every_harness_model_call_keeps_the_same_reference_context(self):
        class Client:
            def __init__(self):
                self.calls = []
                self.responses = ["无法确定", "答案是 4"]

            def chat(self, messages, temperature, max_tokens):
                self.calls.append(messages)
                return self.responses.pop(0)

        class Retriever:
            def search(self, query, top_k):
                return [{
                    "id": "ref-2",
                    "problem": "求 5+5。",
                    "solution": "直接计算。",
                    "similarity": 0.8,
                }]

        client = Client()
        config = AgentConfig(
            enable_constraint_fit_harness=True,
            enable_reference_rag=True,
            enable_temporary_answer_bank=False,
            enable_constraint_fit_deep_lane=False,
        )
        result = ReasoningAgent(
            client,
            config,
            reference_rag_retriever=Retriever(),
        ).solve("计算 2+2", {})
        self.assertEqual("4", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertTrue(all("相似题参考" in call[1]["content"] for call in client.calls))


if __name__ == "__main__":
    unittest.main()
