import json
import unittest

from user_agent import AgentConfig, ReasoningAgent, answer_equivalence, extract_final_answer, normalize_answer


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class AnswerHandlingTest(unittest.TestCase):
    def test_extracts_supported_formats(self):
        self.assertEqual("x={1,2}", extract_final_answer(r"work \boxed{x={1,2}}"))
        self.assertEqual("7", extract_final_answer("推导\n最终答案： 7"))
        self.assertEqual("8", extract_final_answer("Final answer: 8"))
        self.assertEqual("C", extract_final_answer("推导\n选项 C"))
        self.assertEqual("42", extract_final_answer("计算如下\n42"))

    def test_empty_and_multiple_answers_are_deterministic(self):
        self.assertEqual("", extract_final_answer(" \n "))
        self.assertEqual("2", extract_final_answer("最终答案：1\n最终答案：2"))
        self.assertEqual("", extract_final_answer("Final answer:"))

    def test_extracts_equation_set_interval_vector_and_matrix_answers(self):
        self.assertEqual("x=2", extract_final_answer("最终答案：x=2"))
        self.assertEqual("{1,2}", extract_final_answer("Final answer: {1,2}"))
        self.assertEqual("[0,1)", extract_final_answer("最终答案：[0,1)"))
        self.assertEqual("(1,2,3)", extract_final_answer("Final answer: (1,2,3)"))
        self.assertEqual(r"\begin{pmatrix}1&0\\0&1\end{pmatrix}", extract_final_answer(r"最终答案：\begin{pmatrix}1&0\\0&1\end{pmatrix}"))

    def test_normalization_is_conservative(self):
        self.assertEqual("1/2", normalize_answer("1/2"))
        self.assertEqual("1/2", normalize_answer(r"\frac{1}{2}"))
        self.assertEqual("1/2", normalize_answer("0.5"))
        self.assertEqual("sqrt(2)", normalize_answer(r"\sqrt{2}"))
        self.assertEqual("F(x)??", normalize_answer("F(x)??"))

    def test_equivalence_is_three_valued_and_conservative(self):
        self.assertEqual("EQUIVALENT", answer_equivalence("1/2", "0.5"))
        self.assertEqual("NOT_EQUIVALENT", answer_equivalence("1", "2"))
        self.assertEqual("NOT_EQUIVALENT", answer_equivalence("A", "B"))
        self.assertEqual("UNKNOWN", answer_equivalence("x+1", "1+x"))


class ReasoningAgentTest(unittest.TestCase):
    def test_default_generation_budget_is_bounded_for_local_api_latency(self):
        self.assertEqual(256, AgentConfig().max_tokens)

    def test_extracts_answer_and_keeps_trace_compact(self):
        agent = ReasoningAgent(FakeClient(["推导略。\n最终答案： 7", "另一种推导。\nFinal answer: 7", "VERDICT: A", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4))
        result = agent.solve("计算 3+4", {})
        self.assertEqual("7", result["final_response"])
        self.assertTrue(all("prompt" not in entry and "response" not in entry for entry in result["trace"]))
        json.dumps(result, ensure_ascii=False)

    def test_consensus_precedes_audit_and_conflicts_use_audit(self):
        consistent = ReasoningAgent(FakeClient(["最终答案：1/2", r"最终答案：\frac{1}{2}", "VERDICT: B", "VERDICT: B"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4))
        self.assertEqual("1/2", consistent.solve("题", {})["final_response"])

        conflicting = ReasoningAgent(FakeClient(["最终答案：1", "最终答案：2", "VERDICT: B", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4))
        self.assertEqual("2", conflicting.solve("题", {})["final_response"])

    def test_budget_failure_and_unextractable_candidates_degrade(self):
        client = FakeClient(["Final answer:", "最终答案：9", "VERDICT: A"])
        result = ReasoningAgent(client, AgentConfig(policy_sample_times=2, verifier_voting_times=2, max_model_calls=3)).solve("测试题", {"idx": 1})
        self.assertEqual("9", result["final_response"])
        self.assertTrue(any(entry.get("reason") == "model_call_budget_exhausted" for entry in result["trace"]))

    def test_all_unextractable_candidates_use_fallback(self):
        result = ReasoningAgent(FakeClient(["Final answer:", "答案："]), AgentConfig(policy_sample_times=2, max_model_calls=2)).solve("测试题", {})
        self.assertTrue(result["final_response"])
        self.assertEqual("fallback", result["trace"][-1]["status"])

    def test_no_candidate_returns_json_serializable_non_empty_fallback(self):
        result = ReasoningAgent(FakeClient([RuntimeError("down")]), AgentConfig(policy_sample_times=1, max_model_calls=1)).solve("测试题", {})
        self.assertTrue(result["final_response"])
        self.assertEqual("fallback", result["trace"][-1]["status"])
        json.dumps(result, ensure_ascii=False)

    def test_controlled_tool_evidence_precedes_consensus(self):
        candidates = [
            {"candidate_id": 0, "answer": "1", "normalized_answer": "1", "evidence": [], "verification_status": "unverified", "model_calls_used": 1},
            {"candidate_id": 1, "answer": "2", "normalized_answer": "2", "evidence": [{"source": "controlled_tool", "claim_status": "SUPPORTED"}], "verification_status": "unverified", "model_calls_used": 1},
            {"candidate_id": 2, "answer": "1", "normalized_answer": "1", "evidence": [], "verification_status": "unverified", "model_calls_used": 1},
        ]
        result = ReasoningAgent._select_candidate(candidates)
        self.assertEqual("2", result["answer"])
        self.assertEqual("controlled_tool_evidence", result["selection_basis"])

    def test_refuted_candidate_loses_to_unrefuted_candidate(self):
        candidates = [
            {"candidate_id": 0, "answer": "1", "normalized_answer": "1", "evidence": [{"source": "controlled_tool", "claim_status": "REFUTED"}], "verification_status": "unverified", "model_calls_used": 1},
            {"candidate_id": 1, "answer": "2", "normalized_answer": "2", "evidence": [], "verification_status": "unverified", "model_calls_used": 1},
            {"candidate_id": 2, "answer": "1", "normalized_answer": "1", "evidence": [{"source": "controlled_tool", "claim_status": "REFUTED"}], "verification_status": "unverified", "model_calls_used": 1},
        ]

        self.assertEqual("2", ReasoningAgent._select_candidate(candidates)["answer"])

    def test_equivalent_answers_are_audited_once_per_group(self):
        client = FakeClient(["最终答案：1/2", r"最终答案：\frac{1}{2}", "最终答案：0.5", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=3, verifier_voting_times=1, max_model_calls=4))

        result = agent.solve("题", {})

        self.assertEqual("1/2", result["final_response"])
        self.assertEqual(4, len(client.calls))
        self.assertEqual(1, sum(entry["step"] == "audit_answer_group" for entry in result["trace"]))

    def test_unknown_equivalence_does_not_merge_answer_groups(self):
        candidates = [
            {"candidate_id": 0, "answer": "x+1", "normalized_answer": "x+1"},
            {"candidate_id": 1, "answer": "1+x", "normalized_answer": "1+x"},
        ]
        self.assertEqual(2, len(ReasoningAgent._answer_groups(candidates)))

    def test_dynamic_budget_routes_simple_arithmetic_to_l0(self):
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=3, verifier_voting_times=1, max_model_calls=2, enable_dynamic_budget=True))

        result = agent.solve("计算 3+4", {})

        self.assertEqual("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("L0", result["trace"][0]["level"])

    def test_local_repair_reaudits_a_refuted_candidate(self):
        client = FakeClient(["最终答案：1", "VERDICT: B", "最终答案：2", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=4, enable_local_repair=True))

        result = agent.solve("题", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual(4, len(client.calls))
        self.assertTrue(any(entry["step"] == "repair_candidate" and entry["status"] == "ok" for entry in result["trace"]))

    def test_controlled_tool_path_validates_simple_arithmetic(self):
        agent = ReasoningAgent(FakeClient(["最终答案：7", "VERDICT: A"]), AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_sympy_evidence=True))
        result = agent.solve("计算 3+4", {})
        tool_trace = next(entry for entry in result["trace"] if entry["step"] == "controlled_tool")
        self.assertEqual("SUPPORTED", tool_trace["claim_status"])

    def test_controlled_tool_evidence_selects_independently_verified_candidate(self):
        agent = ReasoningAgent(FakeClient(["最终答案：8", "最终答案：7", "VERDICT: A", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4, enable_sympy_evidence=True))
        result = agent.solve("计算 3+4", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual("controlled_tool_evidence", result["trace"][-1]["selection_basis"])

    def test_verdict_prompt_defines_labels(self):
        self.assertIn("A 表示未发现可证实错误", __import__("user_agent").VERIFIER_PROMPT)
        self.assertIn("B 表示发现可证实错误", __import__("user_agent").VERIFIER_PROMPT)

    def test_failed_audit_attempt_counts_against_candidate_budget(self):
        agent = ReasoningAgent(FakeClient(["最终答案：7", RuntimeError("down")]), AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2))
        candidates: list[dict] = []
        original_select = agent._select_candidate
        def capture(items):
            candidates.extend(items)
            return original_select(items)
        agent._select_candidate = capture
        agent.solve("计算 3+4", {})
        self.assertEqual(2, candidates[0]["model_calls_used"])


if __name__ == "__main__":
    unittest.main()
