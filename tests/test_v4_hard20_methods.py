"""Zero-model tests for V4-HARD20-DUAL-001 experimental methods."""
from __future__ import annotations

import dataclasses
import json
import unittest

from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


PROBLEM = "设 a = 2，b = 3，求 a 与 b 的乘积。"


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ok(answer: str) -> str:
    return f"推导略。\n最终答案：{answer}"


def experimental_base() -> AgentConfig:
    return dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_contextual_answer_reconstruction=False,
        enable_fork_select_deepen_finish=False,
        enable_fesf_v1=False,
        enable_fesf_exact_eval=False,
    )


class DefaultOffTest(unittest.TestCase):
    def test_submission_keeps_both_flags_off(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_condition_checked_selection)
        self.assertFalse(SUBMISSION_CONFIG.enable_plan_solve_compact)

    def test_mutual_exclusion(self):
        cfg = dataclasses.replace(
            experimental_base(),
            enable_condition_checked_selection=True,
            enable_plan_solve_compact=True,
        )
        with self.assertRaises(ValueError):
            ReasoningAgent(FakeClient([]), config=cfg).solve(PROBLEM, {})


class KcvSelectTest(unittest.TestCase):
    def test_consensus_skips_kcv_call(self):
        cfg = dataclasses.replace(
            experimental_base(),
            enable_condition_checked_selection=True,
            enable_heterogeneous_reasoners=True,
            enable_adaptive_voting=False,
            max_model_calls=4,
        )
        client = FakeClient([ok("6"), ok("6"), ok("6")])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(len(client.calls), 3)
        self.assertIn("6", result["final_response"])
        self.assertFalse(any(e.get("step") == "kcv_select" for e in result["trace"]))

    def test_selects_existing_candidate_only(self):
        cfg = dataclasses.replace(
            experimental_base(),
            enable_condition_checked_selection=True,
            enable_heterogeneous_reasoners=True,
            enable_adaptive_voting=False,
        )
        kcv = (
            "KCV_STATUS: SELECT\n"
            "CANDIDATE_ID: 1\n"
            "KEY_CONDITION: product of a and b\n"
            "EVIDENCE: candidate 1 multiplies 2 and 3"
        )
        client = FakeClient([ok("5"), ok("6"), ok("8"), kcv])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(client.calls[3][2], 512)
        self.assertIn("6", result["final_response"])
        self.assertEqual(result["extracted_answer"], "6")

    def test_unknown_and_out_of_range_fail_closed(self):
        cfg = dataclasses.replace(
            experimental_base(),
            enable_condition_checked_selection=True,
            enable_heterogeneous_reasoners=True,
            enable_adaptive_voting=False,
        )
        bad = (
            "KCV_STATUS: SELECT\n"
            "CANDIDATE_ID: 99\n"
            "KEY_CONDITION: x\n"
            "EVIDENCE: y"
        )
        client = FakeClient([ok("5"), ok("7"), ok("8"), bad])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(result["final_response"], "UNKNOWN")
        self.assertEqual(result["extracted_answer"], "")
        json.dumps(result)


class PlanSolveTest(unittest.TestCase):
    def test_plan_then_solve(self):
        cfg = dataclasses.replace(experimental_base(), enable_plan_solve_compact=True)
        client = FakeClient([
            "VARIABLES: a,b\nCONSTRAINTS: a=2,b=3\nGOAL: product\nANSWER_TYPE: integer\nPLAN: multiply",
            ok("6"),
        ])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0][2], 600)
        self.assertEqual(client.calls[1][2], 3072)
        self.assertIn("6", result["final_response"])

    def test_plan_with_answer_is_rejected(self):
        cfg = dataclasses.replace(experimental_base(), enable_plan_solve_compact=True)
        client = FakeClient(["最终答案：6"])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["final_response"], "UNKNOWN")

    def test_solve_unknown_fail_closed(self):
        cfg = dataclasses.replace(experimental_base(), enable_plan_solve_compact=True)
        client = FakeClient([
            "VARIABLES: a\nCONSTRAINTS: none\nGOAL: x\nANSWER_TYPE: integer\nPLAN: think",
            "无法完成。\n最终答案：UNKNOWN",
        ])
        result = ReasoningAgent(client, config=cfg).solve(PROBLEM, {})
        self.assertEqual(result["final_response"], "UNKNOWN")
        self.assertEqual(result["extracted_answer"], "")


if __name__ == "__main__":
    unittest.main()
