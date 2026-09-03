import dataclasses
import json
import unittest

from user_agent import (
    AgentConfig,
    ReasoningAgent,
    SUBMISSION_CONFIG,
    _is_typed_math_value,
    extract_typed_answer,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def config():
    return dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_contextual_answer_reconstruction=True,
        enable_typed_answer_capsule=False,
        enable_condition_checked_selection=False,
        enable_plan_solve_compact=False,
        max_model_calls=2,
        max_tokens=4096,
        reconstruction_max_tokens=2048,
        reconstruction_context_max_chars=80,
    )


class ContextualParserTest(unittest.TestCase):
    def test_final_answer_alias_and_placeholder_guard(self):
        self.assertEqual("42", extract_typed_answer("Final answer: 42"))
        self.assertEqual("42", extract_typed_answer("FINAL: 42"))
        self.assertEqual(r"\\theta+1", extract_typed_answer(r"最终答案：\\theta+1"))
        self.assertEqual("x+y", extract_typed_answer("ANSWER: x+y"))
        self.assertEqual(r"\\binom{n}{2}", extract_typed_answer(r"ANSWER: \\binom{n}{2}"))
        self.assertEqual("", extract_typed_answer("ANSWER: <result>"))
        self.assertEqual("", extract_typed_answer("ANSWER: Weneedtofind23"))
        self.assertFalse(_is_typed_math_value("<result>"))

    def test_context_is_bounded_head_and_tail(self):
        context = ReasoningAgent._bounded_reconstruction_context("a" * 100, 20)
        self.assertIn("...[中间草稿省略]...", context)
        self.assertIn("a", context)


class ContextualFlowTest(unittest.TestCase):
    def test_primary_answer_avoids_second_call(self):
        client = FakeClient(["推导略。\n最终答案：42"])
        result = ReasoningAgent(client, config()).solve("计算 6*7", {})
        self.assertEqual(1, len(client.calls))
        self.assertEqual("42", result["extracted_answer"])
        self.assertEqual("candidate_consensus", result["trace"][-1]["source"])

    def test_baseline_chinese_answer_alias_is_supported(self):
        client = FakeClient(["答案：42"])
        result = ReasoningAgent(client, config()).solve("计算 6*7", {})
        self.assertEqual(1, len(client.calls))
        self.assertEqual("42", result["extracted_answer"])

    def test_complex_candidate_consensus_stops_before_reconstruction(self):
        cfg = dataclasses.replace(config(), max_model_calls=5)
        client = FakeClient(["最终答案：42", "最终答案：42", "最终答案：42"])
        result = ReasoningAgent(client, cfg).solve("求一个由参数定义的极限值。", {})
        self.assertEqual(3, len(client.calls))
        self.assertEqual("42", result["extracted_answer"])
        self.assertEqual("candidate_consensus", result["trace"][-1]["source"])
        self.assertNotIn("第一行必须且只能", client.calls[0][0][0]["content"])

    def test_reconstruction_receives_untrusted_draft(self):
        draft = "推导：" + "x=1; " * 50
        client = FakeClient([draft, "重新核对后\n最终答案：42"])
        result = ReasoningAgent(client, config()).solve("计算 6*7", {})
        self.assertEqual(2, len(client.calls))
        prompt = client.calls[1][0][1]["content"]
        self.assertIn("不可信候选草稿", prompt)
        self.assertIn("中间草稿省略", prompt)
        self.assertEqual(2048, client.calls[1][2])
        self.assertEqual("42", result["extracted_answer"])
        self.assertEqual("reconstruction", result["trace"][-1]["source"])

    def test_primary_placeholder_is_reconstructed(self):
        client = FakeClient(["ANSWER: <result>", "Final answer: 9"])
        result = ReasoningAgent(client, config()).solve("计算 3*3", {})
        self.assertEqual(2, len(client.calls))
        self.assertEqual("9", result["extracted_answer"])

    def test_conflicting_typed_answers_are_reconstructed(self):
        client = FakeClient(["ANSWER: 8\nFINAL: 9", "最终答案：9"])
        result = ReasoningAgent(client, config()).solve("计算 3*3", {})
        self.assertEqual(2, len(client.calls))
        self.assertEqual("9", result["extracted_answer"])

    def test_reconstruction_failure_uses_only_bounded_final_candidate(self):
        cfg = dataclasses.replace(config(), max_model_calls=5)
        client = FakeClient(["无标记草稿", "没有结论", "仍无结论", "重构也失败", "最终答案：9"])
        result = ReasoningAgent(client, cfg).solve("求一个参数极限。", {})
        self.assertEqual(5, len(client.calls))
        self.assertEqual("9", result["extracted_answer"])

    def test_proof_keeps_full_primary_response(self):
        proof = "最终答案：成立\n\n证明：设 n=2k，则 n 为偶数。"
        client = FakeClient([proof])
        result = ReasoningAgent(client, config()).solve("证明 n 为偶数。", {})
        self.assertEqual(1, len(client.calls))
        self.assertIn("n=2k", result["final_response"])

    def test_both_responses_fail_closed(self):
        client = FakeClient(["推导未完成", "ANSWER: The answer is 42"])
        result = ReasoningAgent(client, config()).solve("计算 6*7", {})
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("", result["extracted_answer"])
        json.dumps(result, ensure_ascii=False)

    def test_paths_are_mutually_exclusive(self):
        cfg = dataclasses.replace(config(), enable_typed_answer_capsule=True)
        with self.assertRaises(ValueError):
            ReasoningAgent(FakeClient([]), cfg).solve("计算 1+1", {})


if __name__ == "__main__":
    unittest.main()
