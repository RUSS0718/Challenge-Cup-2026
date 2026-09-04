import dataclasses
import json
import unittest

from user_agent import (
    AgentConfig,
    ReasoningAgent,
    SUBMISSION_CONFIG,
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


class TypedParserTest(unittest.TestCase):
    def test_accepts_pure_typed_math_tokens(self):
        self.assertEqual("33", extract_typed_answer("ANSWER: 33\n推理"))
        self.assertEqual(r"\\frac{16\\sqrt{2}}{9}", extract_typed_answer(r"ANSWER: \\frac{16\\sqrt{2}}{9}"))
        self.assertEqual("A", extract_typed_answer("ANSWER: A"))

    def test_rejects_natural_language_and_tail_integers(self):
        self.assertEqual("", extract_typed_answer("推理中得到 17，接着分析 23"))
        self.assertEqual("", extract_typed_answer("ANSWER: The answer is 23"))
        self.assertEqual("", extract_typed_answer("ANSWER: 23, because x=2"))
        self.assertEqual("", extract_typed_answer("答案：23\n正文里还有 99"))
        self.assertEqual("", extract_typed_answer("ANSWER: UNKNOWN"))


class CapsuleFlowTest(unittest.TestCase):
    def cfg(self):
        return dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_typed_answer_capsule=True,
            enable_contextual_answer_reconstruction=False,
            enable_fork_select_deepen_finish=False,
            enable_condition_checked_selection=False,
            enable_plan_solve_compact=False,
            max_tokens=4096,
            capsule_retry_max_tokens=2048,
        )

    def test_primary_accepts_without_retry(self):
        client = FakeClient(["ANSWER: 42\nstep 1"])
        result = ReasoningAgent(client, config=self.cfg()).solve("1+1", {})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][2], 4096)
        self.assertEqual(result["extracted_answer"], "42")
        self.assertEqual(result["final_response"], "ANSWER: 42")

    def test_retry_is_independent_and_uses_2048(self):
        client = FakeClient(["推理被截断，已有 17", "ANSWER: 42\n校验"])
        result = ReasoningAgent(client, config=self.cfg()).solve("1+1", {})
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1][2], 2048)
        self.assertNotIn("已有 17", client.calls[1][0][1]["content"])
        self.assertEqual(result["extracted_answer"], "42")

    def test_both_fail_closed_to_unknown(self):
        client = FakeClient(["推理中 17", "ANSWER: The answer is 42"])
        result = ReasoningAgent(client, config=self.cfg()).solve("1+1", {})
        self.assertEqual(result["final_response"], "UNKNOWN")
        self.assertEqual(result["extracted_answer"], "")
        json.dumps(result, ensure_ascii=False)

    def test_model_error_triggers_only_one_independent_retry(self):
        client = FakeClient([RuntimeError("timeout"), "ANSWER: The answer is 42"])
        result = ReasoningAgent(client, config=self.cfg()).solve("1+1", {})
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result["final_response"], "UNKNOWN")

    def test_default_submission_off(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_typed_answer_capsule)


if __name__ == "__main__":
    unittest.main()
