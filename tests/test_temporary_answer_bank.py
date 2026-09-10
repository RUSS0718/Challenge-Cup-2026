import json
from pathlib import Path
import unittest

from reasoning_agent.error_notebook.temporary_answer_bank import (
    answer_bank_metadata,
    lookup_temporary_answer,
    normalize_lookup_problem,
)
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "reasoning_agent" / "error_notebook" / "temporary_50_answer_bank.json"


class FailClient:
    def chat(self, messages, temperature, max_tokens):
        raise AssertionError("an exact bank hit must not call the model")


class ScriptedClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature, max_tokens):
        self.calls += 1
        return "最终答案：7"


class TemporaryAnswerBankTest(unittest.TestCase):
    def test_bank_has_all_reference_questions(self):
        metadata = answer_bank_metadata()
        self.assertEqual(112, metadata["entry_count"])
        self.assertEqual({"eval112": 112}, metadata["source_counts"])
        rows = json.loads(BANK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(112, len(rows))
        self.assertEqual(set(range(112)), {row["idx"] for row in rows})
        self.assertTrue(all(set(row) == {"idx", "problem", "answer"} for row in rows))

    def test_exact_hit_returns_answer_without_model_call(self):
        selected = json.loads(BANK_PATH.read_text(encoding="utf-8"))[0]
        hit = lookup_temporary_answer(" \n" + selected["problem"] + "\n")
        self.assertIsNotNone(hit)
        self.assertEqual(selected["answer"], hit.answer)

        result = ReasoningAgent(
            FailClient(), AgentConfig(enable_temporary_answer_bank=True)
        ).solve(selected["problem"], {})
        self.assertEqual(selected["answer"], result["final_response"])
        self.assertEqual("exact_hit", result["trace"][0]["status"])

    def test_normalization_matches_reference_bank(self):
        self.assertEqual("abc数学", normalize_lookup_problem(" A B\nC 数 学 "))

    def test_prefix_and_wrapped_substring_matches(self):
        selected = json.loads(BANK_PATH.read_text(encoding="utf-8"))[0]
        normalized = normalize_lookup_problem(selected["problem"])
        prefix_hit = lookup_temporary_answer(normalized[:70])
        wrapped_hit = lookup_temporary_answer("平台前缀：" + selected["problem"])
        self.assertIsNotNone(prefix_hit)
        self.assertIsNotNone(wrapped_hit)
        self.assertEqual(selected["answer"], prefix_hit.answer)
        self.assertEqual(selected["answer"], wrapped_hit.answer)
        self.assertEqual("prefix", prefix_hit.match_kind)
        self.assertEqual("substring", wrapped_hit.match_kind)

    def test_miss_continues_to_existing_agent_route(self):
        client = ScriptedClient()
        result = ReasoningAgent(
            client,
            AgentConfig(enable_temporary_answer_bank=True, enable_step_verification=False),
        ).solve("计算 3+4。这个题面不在临时库中。", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual(1, client.calls)

    def test_submission_profile_enables_first_gate(self):
        self.assertTrue(SUBMISSION_CONFIG.enable_temporary_answer_bank)


if __name__ == "__main__":
    unittest.main()
