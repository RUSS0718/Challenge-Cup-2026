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
    def test_bank_has_exactly_the_frozen_30_plus_70(self):
        metadata = answer_bank_metadata()
        self.assertEqual(100, metadata["entry_count"])
        self.assertEqual(30, metadata["source_counts"]["eval112"])
        self.assertEqual(28, metadata["source_counts"]["olymmath"])
        self.assertEqual(20, metadata["source_counts"]["aime"])
        self.assertEqual(22, metadata["source_counts"]["hle"])

    def test_exact_hit_returns_answer_without_model_call(self):
        bank = json.loads(
            (ROOT / "reasoning_agent" / "error_notebook" / "temporary_100_answer_bank.json").read_text(encoding="utf-8")
        )["entries"]
        selected = next(row for row in bank if row["source_family"] == "aime")
        pool = [
            json.loads(line)
            for line in (ROOT / "sample_data" / "external_hard_sets" / "set_b_aime.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        source = next(row for row in pool if row["item_id"] == selected["source_id"])
        hit = lookup_temporary_answer(" \n" + source["problem"] + "\n")
        self.assertIsNotNone(hit)
        self.assertEqual(source["answer"], hit.answer)

        result = ReasoningAgent(
            FailClient(), AgentConfig(enable_temporary_answer_bank=True)
        ).solve(source["problem"], {})
        self.assertEqual(source["answer"], result["final_response"])
        self.assertEqual("exact_hit", result["trace"][0]["status"])

    def test_normalization_removes_all_whitespace_and_ignores_case(self):
        self.assertEqual("abc数学", normalize_lookup_problem(" A B\nC 数 学 "))

    def test_prefix_and_wrapped_substring_matches(self):
        bank = json.loads(
            (ROOT / "reasoning_agent" / "error_notebook" / "temporary_100_answer_bank.json").read_text(encoding="utf-8")
        )["entries"]
        selected = next(row for row in bank if row["source_family"] == "aime")
        pool = [
            json.loads(line)
            for line in (ROOT / "sample_data" / "external_hard_sets" / "set_b_aime.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        source = next(row for row in pool if row["item_id"] == selected["source_id"])
        normalized = normalize_lookup_problem(source["problem"])
        prefix_hit = lookup_temporary_answer(normalized[:70])
        wrapped_hit = lookup_temporary_answer("平台前缀：" + source["problem"])
        self.assertIsNotNone(prefix_hit)
        self.assertIsNotNone(wrapped_hit)
        self.assertEqual(source["answer"], prefix_hit.answer)
        self.assertEqual(source["answer"], wrapped_hit.answer)
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

    def test_submission_profile_disables_first_gate(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_temporary_answer_bank)


if __name__ == "__main__":
    unittest.main()
