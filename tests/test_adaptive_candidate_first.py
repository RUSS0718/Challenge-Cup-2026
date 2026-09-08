import json
import dataclasses
import unittest

from reasoning_agent.adaptive_candidate_first import AdaptiveCandidateFirstRelay
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        if not self.responses:
            raise AssertionError("scripted client exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class AdaptiveCandidateFirstTest(unittest.TestCase):
    def test_submission_profile_keeps_candidate_first_off(self):
        self.assertFalse(AgentConfig().enable_adaptive_candidate_first)
        self.assertFalse(SUBMISSION_CONFIG.enable_adaptive_candidate_first)

    def test_reasoning_agent_opt_in_route(self):
        cfg = dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_adaptive_candidate_first=True,
            enable_fork_select_deepen_finish=False,
            enable_fesf_v1=False,
        )
        client = ScriptedClient(["CANDIDATE: 12"])
        result = ReasoningAgent(client, cfg).solve("计算 3×4", {})
        self.assertEqual("12", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertIn("建议路线", client.calls[0][0][1]["content"])
        self.assertEqual("soft", result["trace"][0]["mode"])

    def test_candidate_first_and_fsdf_are_mutually_exclusive(self):
        cfg = dataclasses.replace(SUBMISSION_CONFIG, enable_adaptive_candidate_first=True)
        with self.assertRaises(ValueError):
            ReasoningAgent(ScriptedClient([]), cfg).solve("求 n", {})

    def test_candidate_first_and_fesf_are_mutually_exclusive(self):
        cfg = dataclasses.replace(
            SUBMISSION_CONFIG,
            enable_adaptive_candidate_first=True,
            enable_fork_select_deepen_finish=False,
            enable_fesf_v1=True,
        )
        with self.assertRaises(ValueError):
            ReasoningAgent(ScriptedClient([]), cfg).solve("求 n", {})

    def test_call_cap_one_fails_closed_without_second_parse(self):
        client = ScriptedClient(["没有候选"])
        result = AdaptiveCandidateFirstRelay(client, max_model_calls=1).solve("求 n")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual(1, len(client.calls))

    def test_hard_deadline_skips_all_calls(self):
        client = ScriptedClient(["CANDIDATE: 7"])
        times = iter((0.0, 900.0, 900.0, 900.0))
        result = AdaptiveCandidateFirstRelay(client, clock=lambda: next(times)).solve("求 n")
        self.assertEqual([], client.calls)
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertTrue(any(event.get("status") == "skipped" for event in result["trace"]))

    def test_soft_deadline_stops_optional_followups(self):
        client = ScriptedClient(["没有候选", "CANDIDATE: 7"])
        times = iter((0.0, 1.0, 601.0, 601.0, 601.0))
        result = AdaptiveCandidateFirstRelay(client, clock=lambda: next(times)).solve("求 n")
        self.assertEqual(1, len(client.calls))
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertIn("soft_deadline", [event.get("reason") for event in result["trace"]])

    def test_unique_candidate_stops_after_first_call(self):
        client = ScriptedClient(["CANDIDATE: 42\n理由：6×7=42"])
        result = AdaptiveCandidateFirstRelay(client).solve("计算 6×7")
        self.assertEqual([2048], [call[2] for call in client.calls])
        self.assertEqual("42", result["final_response"])
        self.assertEqual("42", result["extracted_answer"])
        self.assertEqual("candidate_unproven", result["trace"][-1]["source"])

    def test_missing_candidate_uses_one_recovery_call(self):
        client = ScriptedClient(["推导被截断", "还是没有结论", "CANDIDATE: 9\n理由：代入"])
        result = AdaptiveCandidateFirstRelay(client).solve("计算 3×3")
        self.assertEqual([2048, 2048, 4096], [call[2] for call in client.calls])
        self.assertEqual("9", result["final_response"])
        self.assertEqual("recovered_candidate", result["trace"][-1]["source"])
        self.assertIn("截断片段", client.calls[2][0][1]["content"])

    def test_conflict_keeps_both_then_adjudicates(self):
        client = ScriptedClient([
            "CANDIDATE: 8\nCANDIDATE: 9",
            "CANDIDATE: 9\n理由：复算",
            "FINAL: 9\n依据：第二候选满足题目",
        ])
        result = AdaptiveCandidateFirstRelay(client).solve("计算 3×3")
        self.assertEqual([2048, 2048, 4096], [call[2] for call in client.calls])
        self.assertEqual("9", result["final_response"])
        self.assertEqual("adjudicated", result["trace"][-1]["source"])
        self.assertEqual(["8", "9"], result["trace"][-1]["candidate_values"])

    def test_equivalent_duplicate_candidates_merge_without_adjudication(self):
        client = ScriptedClient(["CANDIDATE: 1/2\nCANDIDATE: 1 / 2"])
        result = AdaptiveCandidateFirstRelay(client).solve("计算一个分数")
        self.assertEqual(1, len(client.calls))
        self.assertEqual("1/2", result["final_response"])
        self.assertEqual("deterministic_agreement", result["trace"][-1]["source"])

    def test_unresolved_conflict_fails_closed(self):
        client = ScriptedClient([
            "CANDIDATE: 8\nCANDIDATE: 9",
            "CANDIDATE: 10",
            "FINAL: UNKNOWN",
        ])
        result = AdaptiveCandidateFirstRelay(client).solve("求一个未知量")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("", result["extracted_answer"])
        self.assertEqual("adjudication_unknown", result["trace"][-1]["source"])
        json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
