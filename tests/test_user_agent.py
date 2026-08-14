import json
import time as _time_mod
import unittest

from user_agent import (
    ANSWER_FIRST_POLICY_PROMPT, ANSWER_ONLY_POLICY_PROMPT, POLICY_PROMPT,
    AgentConfig, ReasoningAgent,
    TASK_TYPE_CALCULATION, TASK_TYPE_CHOICE, TASK_TYPE_DERIVATION,
    TASK_TYPE_EXPLANATION, TASK_TYPE_FILL_BLANK, TASK_TYPE_PROOF,
    CALCULATION_PROMPT, CHOICE_PROMPT, DERIVATION_PROMPT,
    EXPLANATION_PROMPT, FILL_BLANK_PROMPT, PROOF_PROMPT, TASK_PROMPTS,
    DIRECT_REASONER_PROMPT, ALTERNATIVE_REASONER_PROMPT,
    STEP_VERIFY_PROMPT, SOLUTION_VERIFY_PROMPT, STEP_REVISE_PROMPT,
    answer_equivalence, classify_problem_type, extract_final_answer,
    extract_answer_segment, normalize_answer,
)


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
        self.assertEqual("", extract_final_answer('输出格式为“最终答案：[Answer]”。'))

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

    def test_normalization_strips_display_math_wrappers(self):
        # Universal LaTeX/markdown wrapper cleanup — never bound to a sample idx.
        self.assertEqual("1/2", normalize_answer(r"$\frac{1}{2}$"))
        self.assertEqual("1/2", normalize_answer(r"\(\frac{1}{2}\)"))
        self.assertEqual("10", normalize_answer('10"'))
        self.assertEqual("(x-2)^2", normalize_answer(r"**$(x-2)^2$**"))

    def test_prompt_echo_is_placeholder(self):
        from user_agent import is_placeholder_answer
        self.assertTrue(is_placeholder_answer("明确写出答案"))
        self.assertTrue(is_placeholder_answer('"明确写出答案"'))
        self.assertFalse(is_placeholder_answer("42"))

    def test_multi_numeric_roots_are_canonicalized_order_invariantly(self):
        # Universal unordered multi-root set form; not bound to any sample idx.
        self.assertEqual("-1,1", normalize_answer("x = 1, x = -1"))
        self.assertEqual("-1,1", normalize_answer("-1, 1"))
        self.assertEqual("-1,1", normalize_answer("x=-1 or x=1"))
        self.assertEqual("-1,1", normalize_answer("{1, -1}"))
        self.assertEqual("2,3", normalize_answer("x=3, x=2"))
        self.assertEqual("EQUIVALENT", answer_equivalence("x=1, x=-1", "-1, 1"))
        self.assertEqual("NOT_EQUIVALENT", answer_equivalence("-1, 1", "1, 2"))
        # Ordered single vectors / inequalities stay untouched.
        self.assertEqual("(1,2,3)", normalize_answer("(1,2,3)"))
        self.assertEqual("x>5", normalize_answer("x > 5"))

    def test_equivalence_is_three_valued_and_conservative(self):
        self.assertEqual("EQUIVALENT", answer_equivalence("1/2", "0.5"))
        self.assertEqual("NOT_EQUIVALENT", answer_equivalence("1", "2"))
        self.assertEqual("NOT_EQUIVALENT", answer_equivalence("A", "B"))
        self.assertEqual("UNKNOWN", answer_equivalence("x+1", "1+x"))


class ReasoningAgentTest(unittest.TestCase):
    def test_default_generation_budget_is_bounded_for_local_api_latency(self):
        self.assertEqual(3072, AgentConfig(enable_step_verification=False).max_tokens)
        self.assertTrue(AgentConfig(enable_step_verification=False).enable_l0_extended_tokens)

    def test_extracts_answer_and_keeps_trace_compact(self):
        agent = ReasoningAgent(FakeClient(["推导略。\n最终答案： 7", "另一种推导。\nFinal answer: 7", "VERDICT: A", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        self.assertTrue(all("prompt" not in entry and "response" not in entry for entry in result["trace"]))
        json.dumps(result, ensure_ascii=False)

    def test_consensus_precedes_audit_and_conflicts_use_audit(self):
        consistent = ReasoningAgent(FakeClient(["最终答案：1/2", r"最终答案：\frac{1}{2}", "VERDICT: B", "VERDICT: B"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4, enable_step_verification=False))
        self.assertIn("1/2", consistent.solve("题", {})["final_response"])

        conflicting = ReasoningAgent(FakeClient(["最终答案：1", "最终答案：2", "VERDICT: B", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4, enable_step_verification=False))
        self.assertIn("2", conflicting.solve("题", {})["final_response"])

    def test_budget_failure_and_unextractable_candidates_degrade(self):
        client = FakeClient(["Final answer:", "最终答案：9", "VERDICT: A"])
        result = ReasoningAgent(client, AgentConfig(policy_sample_times=2, verifier_voting_times=2, max_model_calls=3, enable_step_verification=False)).solve("测试题", {"idx": 1})
        self.assertIn("9", result["final_response"])
        self.assertTrue(any(entry.get("reason") == "model_call_budget_exhausted" for entry in result["trace"]))

    def test_all_unextractable_candidates_use_fallback(self):
        result = ReasoningAgent(FakeClient(["Final answer:", "答案："]), AgentConfig(policy_sample_times=2, max_model_calls=2, enable_step_verification=False)).solve("测试题", {})
        self.assertTrue(result["final_response"])
        self.assertEqual("fallback", result["trace"][-1]["status"])

    def test_no_candidate_returns_json_serializable_non_empty_fallback(self):
        result = ReasoningAgent(FakeClient([RuntimeError("down")]), AgentConfig(policy_sample_times=1, max_model_calls=1, enable_step_verification=False)).solve("测试题", {})
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
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=3, verifier_voting_times=1, max_model_calls=4, enable_step_verification=False))

        result = agent.solve("题", {})

        self.assertIn("1/2", result["final_response"])
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
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=3, verifier_voting_times=1, max_model_calls=2, enable_dynamic_budget=True, enable_step_verification=False))

        result = agent.solve("计算 3+4", {})

        self.assertIn("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("L0", result["trace"][0]["level"])

    def test_extended_l0_tokens_do_not_change_other_routes(self):
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_l0_extended_tokens=True, l0_max_tokens=1024, enable_step_verification=False))

        agent.solve("计算 3+4", {})

        self.assertEqual(1024, client.calls[0][2])
        self.assertEqual(256, client.calls[1][2])

    def test_answer_only_prompt_is_an_explicit_opt_in(self):
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_l0_extended_tokens=False, enable_task_aware_prompt=False, policy_prompt=ANSWER_ONLY_POLICY_PROMPT, enable_heterogeneous_reasoners=False, enable_step_verification=False))

        agent.solve("题", {})

        self.assertEqual(ANSWER_ONLY_POLICY_PROMPT, client.calls[0][0][0]["content"])

    def test_default_policy_prompt_is_answer_first(self):
        self.assertEqual(ANSWER_FIRST_POLICY_PROMPT, POLICY_PROMPT)
        self.assertEqual(ANSWER_FIRST_POLICY_PROMPT, AgentConfig(enable_step_verification=False).policy_prompt)

    def test_answer_first_prompt_matches_default_generation_prompt(self):
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_l0_extended_tokens=False, enable_heterogeneous_reasoners=False, enable_step_verification=False))

        agent.solve("题", {})

        self.assertEqual(POLICY_PROMPT, client.calls[0][0][0]["content"])

    def test_l2_escalates_conflicting_l1_candidates_within_its_explicit_budget(self):
        client = FakeClient(["最终答案：1", "最终答案：2", "最终答案：2", "VERDICT: B", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=3, verifier_voting_times=1, max_model_calls=6, enable_dynamic_budget=True, enable_l2_routing=True, l2_max_model_calls=8, enable_step_verification=False))

        result = agent.solve("计算题", {})

        self.assertIn("2", result["final_response"])
        self.assertEqual(5, len(client.calls))
        self.assertTrue(any(entry["step"] == "route_budget" and entry["level"] == "L2" and entry["reason"] == "answer_conflict" for entry in result["trace"]))
        self.assertEqual(8, result["trace"][0]["max_model_calls"])

    def test_local_repair_reaudits_a_refuted_candidate(self):
        client = FakeClient(["最终答案：1", "VERDICT: B", "最终答案：2", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=4, enable_local_repair=True, enable_step_verification=False))

        result = agent.solve("题", {})

        self.assertIn("2", result["final_response"])
        self.assertEqual(4, len(client.calls))
        self.assertTrue(any(entry["step"] == "repair_candidate" and entry["status"] == "ok" for entry in result["trace"]))

    def test_uncertain_repair_runs_only_when_no_candidate_passed_audit(self):
        client = FakeClient(["最终答案：1", "VERDICT: UNCERTAIN", "最终答案：2", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=4, enable_local_repair=True, enable_uncertain_repair=True, enable_step_verification=False))

        result = agent.solve("题", {})

        self.assertIn("2", result["final_response"])
        repair = next(entry for entry in result["trace"] if entry["step"] == "repair_candidate")
        self.assertEqual("uncertain_without_pass", repair["trigger"])

    def test_uncertain_repair_does_not_run_when_another_candidate_passed_audit(self):
        client = FakeClient(["最终答案：1", "最终答案：2", "VERDICT: UNCERTAIN", "VERDICT: A"])
        agent = ReasoningAgent(client, AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=5, enable_local_repair=True, enable_uncertain_repair=True, enable_step_verification=False))

        result = agent.solve("题", {})

        self.assertIn("2", result["final_response"])
        self.assertFalse(any(entry["step"] == "repair_candidate" for entry in result["trace"]))

    def test_controlled_tool_path_validates_simple_arithmetic(self):
        agent = ReasoningAgent(FakeClient(["最终答案：7", "VERDICT: A"]), AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_sympy_evidence=True, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        tool_trace = next(entry for entry in result["trace"] if entry["step"] == "controlled_tool")
        self.assertEqual("SUPPORTED", tool_trace["claim_status"])

    def test_controlled_tool_evidence_selects_independently_verified_candidate(self):
        agent = ReasoningAgent(FakeClient(["最终答案：8", "最终答案：7", "VERDICT: A", "VERDICT: A"]), AgentConfig(policy_sample_times=2, verifier_voting_times=1, max_model_calls=4, enable_sympy_evidence=True, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        self.assertEqual("controlled_tool_evidence", result["trace"][-1]["selection_basis"])

    def test_verdict_prompt_defines_labels(self):
        self.assertIn("A 表示未发现可证实错误", __import__("user_agent").VERIFIER_PROMPT)
        self.assertIn("B 表示发现可证实错误", __import__("user_agent").VERIFIER_PROMPT)

    def test_failed_audit_attempt_counts_against_candidate_budget(self):
        agent = ReasoningAgent(FakeClient(["最终答案：7", RuntimeError("down")]), AgentConfig(policy_sample_times=1, verifier_voting_times=1, max_model_calls=2, enable_step_verification=False))
        candidates: list[dict] = []
        original_select = agent._select_candidate
        def capture(items):
            candidates.extend(items)
            return original_select(items)
        agent._select_candidate = capture
        agent.solve("计算 3+4", {})
        self.assertEqual(2, candidates[0]["model_calls_used"])


# ═══════════════════════════════════════════════════════════════════════════
# P0: Problem-type classification tests
# ═══════════════════════════════════════════════════════════════════════════

class ProblemTypeClassificationTest(unittest.TestCase):
    """classify_problem_type must be purely text-based and deterministic."""

    def test_choice_detection_from_enumerated_options(self):
        self.assertEqual(TASK_TYPE_CHOICE, classify_problem_type(
            "A. 1  B. 2  C. 3  D. 4  哪个是正确的？"))

    def test_choice_detection_from_keyword(self):
        self.assertEqual(TASK_TYPE_CHOICE, classify_problem_type(
            "下列选项中正确的是"))

    def test_fill_blank_detection_from_underscores(self):
        self.assertEqual(TASK_TYPE_FILL_BLANK, classify_problem_type(
            "填入 ____ 的值。"))

    def test_fill_blank_detection_from_keyword(self):
        self.assertEqual(TASK_TYPE_FILL_BLANK, classify_problem_type(
            "填空题：计算下列结果。"))

    def test_proof_detection_chinese(self):
        self.assertEqual(TASK_TYPE_PROOF, classify_problem_type(
            "证明：对于任意正整数 n，..."))

    def test_proof_detection_english(self):
        self.assertEqual(TASK_TYPE_PROOF, classify_problem_type(
            "Prove that the sum of two even numbers is even."))

    def test_proof_show_that(self):
        self.assertEqual(TASK_TYPE_PROOF, classify_problem_type(
            "Show that x^2 >= 0 for all real x."))

    def test_derivation_detection(self):
        self.assertEqual(TASK_TYPE_DERIVATION, classify_problem_type(
            "推导出匀变速运动的位移公式。"))

    def test_explanation_detection(self):
        self.assertEqual(TASK_TYPE_EXPLANATION, classify_problem_type(
            "解释为什么负数乘以负数得正数。"))

    def test_calculation_as_default(self):
        self.assertEqual(TASK_TYPE_CALCULATION, classify_problem_type(
            "计算 3 + 4 * 2"))

    def test_calculation_default_for_unknown(self):
        self.assertEqual(TASK_TYPE_CALCULATION, classify_problem_type(
            "求 x^2 - 5x + 6 = 0 的解。"))

    def test_empty_input_defaults_to_calculation(self):
        self.assertEqual(TASK_TYPE_CALCULATION, classify_problem_type(""))

    def test_non_string_input_defaults_to_calculation(self):
        self.assertEqual(TASK_TYPE_CALCULATION, classify_problem_type(None))

    def test_proof_has_priority_over_explanation(self):
        # "证明...并解释" → proof (more specific)
        self.assertEqual(TASK_TYPE_PROOF, classify_problem_type(
            "证明勾股定理并解释其几何意义。"))


# ═══════════════════════════════════════════════════════════════════════════
# P0: Task-aware prompt selection tests
# ═══════════════════════════════════════════════════════════════════════════

class TaskAwarePromptTest(unittest.TestCase):

    def test_task_prompts_map_all_six_types(self):
        for task_type in (TASK_TYPE_CHOICE, TASK_TYPE_FILL_BLANK,
                          TASK_TYPE_CALCULATION, TASK_TYPE_DERIVATION,
                          TASK_TYPE_PROOF, TASK_TYPE_EXPLANATION):
            self.assertIn(task_type, TASK_PROMPTS)

    def test_calculation_prompt_is_policy_prompt(self):
        self.assertEqual(POLICY_PROMPT, CALCULATION_PROMPT)

    def test_choice_prompt_asks_for_letter(self):
        self.assertIn("选项字母", CHOICE_PROMPT)

    def test_proof_prompt_asks_for_proof(self):
        self.assertIn("证明", PROOF_PROMPT)

    def test_explanation_prompt_asks_for_conclusion(self):
        self.assertIn("核心回答", EXPLANATION_PROMPT)

    def test_non_numeric_prompts_answer_first(self):
        """答案前置协议：最终答案 标记必须在 推导/证明/解释 正文标题之前。"""
        for prompt, body_word in ((DERIVATION_PROMPT, "推导"), (PROOF_PROMPT, "证明"), (EXPLANATION_PROMPT, "解释")):
            ans_pos = prompt.find("最终答案")
            body_pos = prompt.find(body_word + "：")
            self.assertGreater(ans_pos, -1, prompt)
            self.assertGreater(body_pos, -1, prompt)
            self.assertLess(ans_pos, body_pos, prompt)

    def test_task_policy_prompt_returns_type_specific_prompt(self):
        client = FakeClient(["最终答案：42", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_task_aware_prompt=True,
                        enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=False, enable_step_verification=False))
        agent.solve("这是一道证明题：证明1+1=2", {})
        self.assertEqual(PROOF_PROMPT, client.calls[0][0][0]["content"])

    def test_task_policy_prompt_disabled_uses_default(self):
        client = FakeClient(["最终答案：42", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_task_aware_prompt=False,
                        enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=False, enable_step_verification=False))
        agent.solve("这是一道证明题：证明1+1=2", {})
        self.assertEqual(POLICY_PROMPT, client.calls[0][0][0]["content"])

    def test_fallback_to_default_prompt_for_unknown_type(self):
        agent = ReasoningAgent(FakeClient([]))
        self.assertEqual(POLICY_PROMPT, agent._task_policy_prompt("bogus_type"))


# ═══════════════════════════════════════════════════════════════════════════
# P0: Proof / explanation / derivation — never rejected for no marker
# ═══════════════════════════════════════════════════════════════════════════

class NonNumericTaskTypeTest(unittest.TestCase):

    def test_proof_without_final_answer_marker_is_not_rejected(self):
        """Proof with a real answer but no '最终答案：' marker is still accepted."""
        # Response contains reasoning but no explicit final-answer marker line.
        proof_text = "证明：对于任意正整数n，n^2+n=n(n+1)，两个连续整数之积必为偶数，所以命题成立。"
        client = FakeClient([proof_text, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("证明：对于任意正整数n，n^2+n是偶数。", {})
        # Should NOT be fallback — proof answer is the full text
        self.assertNotEqual("fallback", result["trace"][-1].get("status"))
        self.assertIn("n^2+n", result["final_response"])

    def test_explanation_without_marker_is_not_rejected(self):
        explanation = "数学归纳法基于两个步骤：基础步骤证明P(1)成立，归纳步骤从P(k)推出P(k+1)。最终答案：归纳法原理阐述完毕。"
        client = FakeClient([explanation, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("解释数学归纳法的原理。", {})
        self.assertNotEqual("fallback", result["trace"][-1].get("status"))

    def test_calculation_without_marker_still_rejected(self):
        """Regular calculation without marker is still rejected (not non-numeric)."""
        # Use a response with an empty marker that genuinely fails extraction
        client = FakeClient(["最终答案：", "最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=2, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("数学题：计算 1+2+3", {})
        self.assertIn("7", result["final_response"])
        # First candidate should have been rejected (empty answer after marker)
        rejected = any(e.get("reason") == "answer_not_extractable"
                       for e in result["trace"])
        self.assertTrue(rejected)

    def test_proof_response_used_as_is_in_final_response(self):
        proof_text = "证明：设x>0，由实数性质可知x^2>0。因此对于任意正实数x，其平方恒正。最终答案：得证。"
        client = FakeClient([proof_text, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("证明x>0时x^2>0。", {})
        # For proof type, final_response should be the full solution text
        self.assertIn("x^2>0", result["final_response"])

    def test_derivation_uses_full_solution_text(self):
        deriv_text = "推导过程：由牛顿第二定律 F=ma，代入已知条件得到加速度 a=F/m。最终答案：a=F/m"
        client = FakeClient([deriv_text, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("推导牛顿第二定律的公式。", {})
        # For derivation, final_response is the full solution
        self.assertIn("F=ma", result["final_response"])

    def test_short_valid_proof_is_not_rejected(self):
        """A logically complete short proof (no hard length threshold)."""
        # ~20 chars, valid proof, no "最终答案：" marker
        short_proof = "因为n²+n=n(n+1)，相邻整数必有一偶，故命题成立。"
        client = FakeClient([short_proof, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("证明：n²+n是偶数。", {})
        self.assertNotEqual("fallback", result["trace"][-1].get("status"))
        self.assertIn("n²+n", result["final_response"])

    def test_long_format_echo_with_placeholder_is_rejected(self):
        """A long format-instruction text ending with placeholder is rejected."""
        format_echo = (
            "请按照以下格式输出数学解答：\n"
            "步骤1：分析问题条件。\n"
            "步骤2：应用定理进行推导。\n"
            "步骤3：在最后一行写出最终答案。\n"
            "最终答案：[Answer]"
        )
        client = FakeClient([format_echo, "数学归纳法分为基础步骤与归纳步骤两部分。最终答案：归纳法原理阐述完毕。"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=0,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("解释数学归纳法。", {})
        # The placeholder echo is rejected, never used as the answer.
        self.assertTrue(any(e.get("reason") == "placeholder_answer" for e in result["trace"]))
        self.assertIn("归纳法", result["final_response"])


# ═══════════════════════════════════════════════════════════════════════════
# P0: Time convergence tests
# ═══════════════════════════════════════════════════════════════════════════

class TimeConvergenceTest(unittest.TestCase):

    def test_time_convergence_false_when_disabled(self):
        agent = ReasoningAgent(FakeClient([]),
            AgentConfig(enable_time_convergence=False, enable_step_verification=False))
        past = _time_mod.monotonic() - 99999
        self.assertFalse(agent._time_converge_exceeded(past))
        self.assertFalse(agent._time_hard_exceeded(past))

    def test_time_convergence_false_when_no_start_time(self):
        agent = ReasoningAgent(FakeClient([]),
            AgentConfig(enable_time_convergence=True, enable_step_verification=False))
        self.assertFalse(agent._time_converge_exceeded())
        self.assertFalse(agent._time_hard_exceeded())

    def test_time_convergence_true_after_soft_limit(self):
        agent = ReasoningAgent(FakeClient([]),
            AgentConfig(enable_time_convergence=True,
                        solve_converge_timeout_seconds=0.0, enable_step_verification=False))
        self.assertTrue(agent._time_converge_exceeded(_time_mod.monotonic() - 1.0))

    def test_time_hard_exceeded_true_after_hard_limit(self):
        agent = ReasoningAgent(FakeClient([]),
            AgentConfig(enable_time_convergence=True,
                        solve_hard_timeout_seconds=0.0, enable_step_verification=False))
        self.assertTrue(agent._time_hard_exceeded(_time_mod.monotonic() - 1.0))

    def test_time_hard_exceeded_blocks_all_calls(self):
        """When hard timeout is reached, _request refuses all new calls."""
        client = FakeClient(["最终答案：7"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=3, verifier_voting_times=1,
                        max_model_calls=6, enable_time_convergence=True,
                        solve_hard_timeout_seconds=0.0, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        # All calls should have been refused (0.0 hard timeout)
        self.assertTrue(
            result["trace"][-1].get("status") == "fallback" or len(client.calls) == 0)

    def test_converge_gracefully_with_remaining_candidates(self):
        """Convergence produces a result using already-generated candidates."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        config = AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                             max_model_calls=2, enable_time_convergence=True,
                             solve_converge_timeout_seconds=960.0,
                             enable_l0_extended_tokens=False, enable_step_verification=False)
        agent = ReasoningAgent(client, config)
        result = agent.solve("计算 1+1", {})
        self.assertEqual("7", result["final_response"])
        self.assertNotEqual("fallback", result["trace"][-1].get("status"))

    def test_time_disabled_does_not_block_calls(self):
        """With time convergence disabled, no calls are blocked by time."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_time_convergence=False,
                        enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertEqual("7", result["final_response"])

    def test_trace_includes_problem_type_in_route_budget(self):
        """Every route_budget and finalize trace entry carries problem_type."""
        proof_text = "这是一个完整的证明过程，包含前提、推理步骤和结论。最终答案：证毕。"
        client = FakeClient([proof_text, "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("证明：1+1=2", {})
        route = next(e for e in result["trace"] if e["step"] == "route_budget")
        self.assertEqual(TASK_TYPE_PROOF, route["problem_type"])
        finalize = next(e for e in result["trace"] if e["step"] == "finalize")
        self.assertEqual(TASK_TYPE_PROOF, finalize["problem_type"])

    def test_config_defaults_for_p0_fields(self):
        config = AgentConfig(enable_step_verification=False)
        self.assertTrue(config.enable_task_aware_prompt)
        self.assertTrue(config.enable_time_convergence)
        self.assertEqual(960.0, config.solve_converge_timeout_seconds)
        self.assertEqual(1080.0, config.solve_hard_timeout_seconds)


# ═══════════════════════════════════════════════════════════════════════════
# P0: Integration — full solve with task-aware routing
# ═══════════════════════════════════════════════════════════════════════════

class TaskAwareSolveIntegrationTest(unittest.TestCase):

    def test_calculation_type_produces_normalized_answer(self):
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])

    def test_choice_type_still_extracts_letter(self):
        client = FakeClient(["最终答案：B", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("A. 1  B. 2  C. 3  D. 4", {})
        self.assertEqual("B", result["final_response"])

    def test_fill_blank_produces_answer(self):
        client = FakeClient(["最终答案：42", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False, enable_step_verification=False))
        result = agent.solve("填入 ____ 的值。", {})
        self.assertEqual("42", result["final_response"])


# ── P2: heterogeneous reasoner tests ────────────────────────────────────

class HeterogeneousReasonerTest(unittest.TestCase):
    """P2: verify that enable_heterogeneous_reasoners dispatches correctly."""

    def test_disabled_uses_default_single_prompt(self):
        """With P2 off, generation uses the task-aware prompt, not heterogeneous prompts."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=False, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        # Default path should NOT have reasoner tags
        gen_entries = [e for e in result["trace"] if e.get("step") == "generate_candidate" and e.get("status") == "ok"]
        for entry in gen_entries:
            self.assertNotIn("reasoner", entry)

    def test_enabled_dispatches_both_reasoners(self):
        """P2 on: non-L0 items generate with both Direct and Alternative prompts."""
        client = FakeClient([
            "最终答案：5",   # direct reasoner
            "最终答案：5",   # alternative reasoner
            "VERDICT: A",
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=2, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        result = agent.solve("计算 2+3", {})
        self.assertIn("5", result["final_response"])
        gen_ok = [e for e in result["trace"] if e.get("step") == "generate_candidate" and e.get("status") == "ok"]
        self.assertEqual(2, len(gen_ok))
        self.assertEqual({"direct", "alternative"}, {e.get("reasoner") for e in gen_ok})

    def test_l0_arithmetic_stays_single_direct_when_heterogeneous(self):
        """L0 arithmetic items: 1 generation with direct reasoner, even with P2 on."""
        # "计算 3+4" triggers L0 (simple arithmetic expression)
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=True,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        gen_ok = [e for e in result["trace"] if e.get("step") == "generate_candidate" and e.get("status") == "ok"]
        self.assertEqual(1, len(gen_ok))
        self.assertEqual("direct", gen_ok[0].get("reasoner"))

    def test_default_config_has_heterogeneous_disabled(self):
        """P0 stop-bleeding: heterogeneous reasoners are off by default."""
        config = AgentConfig(enable_step_verification=False)
        self.assertFalse(config.enable_heterogeneous_reasoners)

    def test_heterogeneous_trace_includes_route_with_problem_type(self):
        """Route budget trace entries still carry problem_type in P2 mode."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        route = next((e for e in result["trace"] if e.get("step") == "route_budget"), {})
        self.assertEqual(TASK_TYPE_CALCULATION, route.get("problem_type"))

    def test_extracted_answer_present_in_p2_mode(self):
        """P2 mode: extracted_answer is still present for evaluator scoring."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertEqual("7", result.get("extracted_answer"))

    def test_single_call_does_not_overflow(self):
        """total_calls=1 → exactly 1 generation (no 1→2 overflow bug)."""
        client = FakeClient(["最终答案：7", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        gen_ok = [e for e in result["trace"] if e.get("step") == "generate_candidate" and e.get("status") == "ok"]
        self.assertEqual(1, len(gen_ok), f"expected 1 generation, got {len(gen_ok)}")

    def test_proof_task_prompt_merged_into_reasoner(self):
        """Proof-type task prompt is appended to reasoner prompt, not lost."""
        client = FakeClient(["最终答案：证毕", "VERDICT: A"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_heterogeneous_reasoners=True, enable_step_verification=False))
        agent.solve("这是一道证明题：证明1+1=2", {})
        prompt_sent = client.calls[0][0][0]["content"]
        # Must contain both the direct reasoner strategy AND the proof constraint
        self.assertIn("证明", prompt_sent)


# ── P3: step verification and revision tests ────────────────────────────

class StepVerificationTest(unittest.TestCase):
    """P3: merged verify + targeted revision + re-verify."""

    def test_disabled_defaults_leave_best_unchanged(self):
        """Without P3, best candidate is used as-is — no extra calls."""
        client = FakeClient([
            "最终答案：7",  # candidate
            "VERDICT: A",    # audit
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_step_verification=False))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        self.assertFalse(any(e.get("step") == "verify" for e in result["trace"]))

    def test_verify_runs_and_captures_errors(self):
        """Merged verify call records errors in trace."""
        client = FakeClient([
            "最终答案：f'(a)=0",          # candidate
            "VERDICT: A",                   # audit
            "ERROR:step1:导数定义用错\nERRORS",  # merged verify
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("求导数", {})
        sv = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertTrue(sv, "verify trace entry missing")
        self.assertEqual(1, sv[0].get("error_count"))

    def test_all_ok_complete_skips_revision(self):
        """ALL_OK:COMPLETE → no revision triggered."""
        client = FakeClient([
            "最终答案：7",              # candidate
            "VERDICT: A",                # audit
            "OK\nALL_OK:COMPLETE",       # merged verify
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True,
                        enable_step_revision=True))
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        self.assertFalse(any(e.get("step") == "revise" for e in result["trace"]))

    def test_revision_rejects_unanswerable_output(self):
        """Revision with no extractable answer → rejected, best unchanged."""
        client = FakeClient([
            "最终答案：3",                    # candidate (wrong)
            "VERDICT: A",                       # audit
            "ERROR:calc:1+1 != 3\nERRORS",     # verify
            "Final answer: [Answer]",           # revision (no extractable)
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=4, enable_l0_extended_tokens=False,
                        enable_step_verification=True,
                        enable_step_revision=True))
        result = agent.solve("计算 1+1", {})
        rev = [e for e in result["trace"] if e.get("step") == "revise"]
        self.assertTrue(rev)
        self.assertEqual("rejected", rev[0]["status"])

    def test_revision_accepted_and_reverified(self):
        """Valid revision → accepted → re-verify runs."""
        client = FakeClient([
            "最终答案：3",                     # candidate
            "VERDICT: A",                        # audit
            "ERROR:calc:1+1=2 not 3\nERRORS",   # verify
            "修正：1+1=2。\n最终答案：2",        # revision
            "OK\nALL_OK:COMPLETE",               # re-verify
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=6, enable_l0_extended_tokens=False,
                        enable_step_verification=True,
                        enable_step_revision=True))
        result = agent.solve("计算 1+1", {})
        self.assertIn("2", result.get("extracted_answer", ""))
        rev = [e for e in result["trace"] if e.get("step") == "revise"]
        self.assertEqual("ok", rev[0]["status"])
        self.assertTrue(any(e.get("step") == "reverify" for e in result["trace"]))

    def test_reverify_error_rolls_back_revision(self):
        """Re-verify finds errors → rollback to original answer."""
        client = FakeClient([
            "最终答案：3",                     # candidate (wrong)
            "VERDICT: A",                        # audit
            "ERROR:calc:1+1 != 3\nERRORS",      # verify
            "最终答案：0",                        # revision (also wrong)
            "ERROR:calc:1+1=2 not 0\nERRORS",   # re-verify finds error
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=6, enable_l0_extended_tokens=False,
                        enable_step_verification=True,
                        enable_step_revision=True))
        result = agent.solve("计算 1+1", {})
        rv = [e for e in result["trace"] if e.get("step") == "reverify"]
        self.assertTrue(rv)
        self.assertEqual("fail", rv[0]["status"])
        # original answer preserved (3), not the bad revision (0)
        self.assertIn("3", result.get("extracted_answer", ""))

    def test_error_and_gap_parsing(self):
        """Mixed ERROR: and GAPS in single response parse correctly."""
        client = FakeClient([
            "最终答案：0",
            "VERDICT: A",
            "OK\nERROR:第3步:除数为零\nALL_OK:GAPS:未检查定义域",
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("计算 1/0", {})
        sv = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertEqual(1, sv[0].get("error_count"))
        self.assertEqual(1, sv[0].get("gap_count"))

    def test_budget_exhausted_verify_skipped_not_ok(self):
        """Budget exhausted → verify skipped, never recorded as ok."""
        client = FakeClient([
            "最终答案：7",
            "VERDICT: A",
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=2, enable_l0_extended_tokens=False,
                        enable_step_verification=True,
                        p3_call_boost=0))  # no boost → budget stays at 2
        result = agent.solve("计算 3+4", {})
        verify_entries = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertFalse(any(e.get("status") == "ok" for e in verify_entries),
                         "verify should not report ok when budget was exhausted")

    def test_malformed_verifier_output_is_inconclusive(self):
        """Verifier output with no protocol lines → inconclusive, not ok with 0 errors."""
        client = FakeClient([
            "最终答案：7",                                # candidate
            "VERDICT: A",                                  # audit
            "This does not follow the verifier protocol",  # malformed verify
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("计算 3+4", {})
        verify_entries = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertTrue(verify_entries)
        self.assertEqual("inconclusive", verify_entries[0]["status"])

    def test_truncated_ok_without_terminal_is_inconclusive(self):
        """A per-step OK without the required terminal verdict is incomplete."""
        client = FakeClient([
            "最终答案：7",
            "VERDICT: A",
            "OK",
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("计算 3+4", {})
        verify_entries = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertEqual("inconclusive", verify_entries[0]["status"])

    def test_bare_errors_without_error_lines_is_inconclusive(self):
        """ERRORS without preceding ERROR: → malformed, not 0 errors."""
        client = FakeClient([
            "最终答案：7",
            "VERDICT: A",
            "ERRORS",  # protocol violation: no ERROR: lines
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("计算 3+4", {})
        verify_entries = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertEqual("inconclusive", verify_entries[0]["status"])

    def test_empty_gaps_is_inconclusive(self):
        """ALL_OK:GAPS: with no content → malformed, not 0 gaps."""
        client = FakeClient([
            "最终答案：7",
            "VERDICT: A",
            "ALL_OK:GAPS:",  # protocol violation: empty gap list
        ])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=1,
                        max_model_calls=3, enable_l0_extended_tokens=False,
                        enable_step_verification=True))
        result = agent.solve("计算 3+4", {})
        verify_entries = [e for e in result["trace"] if e.get("step") == "verify"]
        self.assertEqual("inconclusive", verify_entries[0]["status"])


# ═══════════════════════════════════════════════════════════════════════════
# P0 stop-bleeding: truncation → bounded calls, strict extraction, compact output
# ═══════════════════════════════════════════════════════════════════════════

class P0StopBleedingTest(unittest.TestCase):

    def test_default_config_is_stop_bleeding(self):
        config = AgentConfig()
        self.assertEqual(1, config.policy_sample_times)
        self.assertEqual(0, config.verifier_voting_times)
        self.assertEqual(2, config.max_model_calls)
        self.assertEqual(3072, config.max_tokens)
        self.assertFalse(config.enable_heterogeneous_reasoners)
        self.assertFalse(config.enable_step_verification)
        self.assertFalse(config.enable_step_revision)
        self.assertFalse(config.enable_l2_routing)
        self.assertFalse(config.enable_local_repair)

    def test_truncated_response_triggers_at_most_two_calls(self):
        """Truncated main call (no answer marker) → exactly one recovery call, never 7."""
        client = FakeClient(["根据题意，代入公式可得", "最终答案：7"])
        agent = ReasoningAgent(client)  # default stop-bleeding config
        result = agent.solve("计算 3+4", {})
        self.assertIn("7", result["final_response"])
        self.assertLessEqual(len(client.calls), 2)
        self.assertTrue(any(e.get("step") == "conditional_retry" for e in result["trace"]))

    def test_clear_answer_skips_conditional_retry(self):
        """A clear main answer ends immediately with a single model call."""
        client = FakeClient(["最终答案：7"])
        agent = ReasoningAgent(client)
        result = agent.solve("计算 3+4", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertFalse(any(e.get("step") == "conditional_retry" for e in result["trace"]))

    def test_truncated_last_line_is_not_taken_as_answer(self):
        self.assertEqual("", extract_final_answer("推导过程如下\n因此我们代入得到"))
        self.assertEqual("", extract_final_answer("计算得到\n根据公式代入"))
        self.assertEqual("", extract_final_answer("步骤1：求导\n步骤2：代入"))

    def test_calculation_returns_compact_normalized_answer(self):
        client = FakeClient(["推导若干……\n最终答案：1/2"])
        agent = ReasoningAgent(client,
            AgentConfig(policy_sample_times=1, verifier_voting_times=0,
                        max_model_calls=2, enable_heterogeneous_reasoners=False,
                        enable_step_verification=False, enable_l0_extended_tokens=False))
        result = agent.solve("计算某表达式", {})
        self.assertEqual("1/2", result["final_response"])

    def test_truncation_signals_recorded_on_rejected_candidate(self):
        client = FakeClient(["根据题意，代入公式可得", "最终答案：7"])
        agent = ReasoningAgent(client)
        result = agent.solve("计算 3+4", {})
        rejected = [e for e in result["trace"]
                    if e.get("step") == "generate_candidate" and e.get("status") == "rejected"]
        self.assertTrue(rejected)
        self.assertIn("no_extractable_answer", rejected[0].get("truncation_signals", []))


# ═══════════════════════════════════════════════════════════════════════════
# 13.2 实验 C：非数值题型答案段抽取（answer-first 协议）边界单测
# ═══════════════════════════════════════════════════════════════════════════

class AnswerSegmentExtractionTest(unittest.TestCase):

    def test_single_line_numeric(self):
        self.assertEqual("31", extract_answer_segment("最终答案：31\n\n推导：\n完整推导"))

    def test_single_line_expression(self):
        self.assertEqual("x^2-1", extract_answer_segment("最终答案：x^2-1\n\n推导：\n..."))

    def test_multi_line_conclusion(self):
        self.assertEqual("第一行\n第二行",
                         extract_answer_segment("最终答案：第一行\n第二行\n\n解释：\n..."))

    def test_followed_by_proof_body(self):
        self.assertEqual("命题成立；行列式为 -1",
                         extract_answer_segment("最终答案：命题成立；行列式为 -1\n\n证明：\n完整证明"))

    def test_no_marker_returns_empty(self):
        self.assertEqual("", extract_answer_segment("这是一段没有答案标记的文本"))

    def test_truncated_after_marker(self):
        self.assertEqual("3", extract_answer_segment("最终答案：3"))

    def test_repeated_marker_takes_first_non_echo(self):
        self.assertEqual("31", extract_answer_segment("最终答案：31\n推导：...\n最终答案：31"))

    def test_inequality_preserved(self):
        self.assertEqual("x > 3", extract_answer_segment("最终答案：x > 3\n\n推导：..."))

    def test_set_preserved(self):
        self.assertEqual("{1, 2, 3}", extract_answer_segment("最终答案：{1, 2, 3}\n\n推导：..."))

    def test_tuple_preserved(self):
        self.assertEqual("(1, 2, 3)", extract_answer_segment("最终答案：(1, 2, 3)\n\n推导：..."))

    def test_natural_language_conclusion(self):
        self.assertEqual("无法证明", extract_answer_segment("最终答案：无法证明\n\n解释：..."))

    def test_condition_insufficient_conclusion(self):
        self.assertEqual("条件不足", extract_answer_segment("最终答案：条件不足\n\n证明：\n..."))

    def test_skip_thinking_echo_placeholder(self):
        resp = (
            'Thinking Process: 1. Analyze the request... "Final Answer: <only write final expression>"\n'
            '最终答案：31\n\n推导：\n完整推导'
        )
        self.assertEqual("31", extract_answer_segment(resp))

    def test_placeholder_echo_only_returns_empty(self):
        self.assertEqual("", extract_answer_segment("最终答案：<只写最终表达式>"))


if __name__ == "__main__":
    unittest.main()
