import unittest
from fractions import Fraction

from user_agent import (
    SUBMISSION_CONFIG,
    TASK_TYPE_CALCULATION,
    TASK_TYPE_PROOF,
    AgentConfig,
    ReasoningAgent,
    _sanity_violation,
    _single_scalar_value,
    run_answer_checks,
)


PROBABILITY_PROBLEM = "袋中有红球和白球，求摸到红球的概率。"
COUNT_PROBLEM = "某方程在区间内共有多少个整数解？"
CALCULATION_PROBLEM = "已知 x+y=10 且 xy=21，求 x 与 y 的值。"


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


def user_text(call):
    return call[0][1]["content"]


def flow_config(**overrides):
    config = {
        "policy_sample_times": 1,
        "max_model_calls": 2,
        "enable_step_verification": False,
        "enable_adaptive_voting": False,
    }
    config.update(overrides)
    return AgentConfig(**config)


class DeterministicCheckTest(unittest.TestCase):
    def test_scalar_parser_is_conservative(self):
        self.assertEqual(_single_scalar_value("7"), Fraction(7))
        self.assertEqual(_single_scalar_value("x=0.3"), Fraction(3, 10))
        self.assertEqual(_single_scalar_value(r"\frac{1}{2}"), Fraction(1, 2))
        self.assertEqual(_single_scalar_value("150%"), Fraction(3, 2))
        self.assertIsNone(_single_scalar_value("{1,2}"))
        self.assertIsNone(_single_scalar_value("x>5"))

    def test_sanity_check_only_handles_explicit_probability_and_count_domains(self):
        self.assertIn("[0,1]", _sanity_violation(PROBABILITY_PROBLEM, "150%"))
        self.assertIsNone(_sanity_violation(PROBABILITY_PROBLEM, "75%"))
        self.assertIsNotNone(_sanity_violation(COUNT_PROBLEM, "2.5"))
        self.assertIsNone(_sanity_violation("平均每组有多少个球？", "2.5"))
        self.assertIsNone(_sanity_violation(CALCULATION_PROBLEM, "150%"))

    def test_all_six_gate_modes_are_distinguishable(self):
        cases = [
            ("truncation", "由题意得 x=3\n因此接下来", ""),
            ("conflict", "先算得最终答案：1\n复核后最终答案：2", "2"),
            ("sanity", "最终答案：150%", "150%"),
            ("unstructured", "只有推导没有结论", "全文兜底"),
            ("placeholder", "格式为“最终答案：[answer]”", ""),
            ("no_answer", "只有推导没有结论", ""),
        ]
        for mode, response, answer in cases:
            problem_type = TASK_TYPE_PROOF if mode == "unstructured" else TASK_TYPE_CALCULATION
            verdict = run_answer_checks(
                PROBABILITY_PROBLEM if mode == "sanity" else CALCULATION_PROBLEM,
                problem_type,
                response,
                answer,
                False if mode == "unstructured" else True,
            )
            self.assertEqual("fail", verdict["status"])
            self.assertEqual(mode, verdict["mode"])

        passing = run_answer_checks(CALCULATION_PROBLEM, TASK_TYPE_CALCULATION, "最终答案：7", "7", True)
        self.assertEqual({"status": "pass", "mode": None, "detail": None}, passing)


class GatedRetryFlowTest(unittest.TestCase):
    def test_passing_answer_skips_retry(self):
        client = FakeClient(["推导过程\n最终答案：7"])
        result = ReasoningAgent(client, flow_config(enable_verification_gated_retry=True)).solve(CALCULATION_PROBLEM, {})
        self.assertEqual(1, len(client.calls))
        self.assertEqual("7", result["extracted_answer"])
        steps = [entry["step"] for entry in result["trace"]]
        self.assertIn("verification_check", steps)
        self.assertNotIn("conditional_retry", steps)

    def test_failed_check_retries_with_counter_evidence_and_accepts_only_passing_retry(self):
        client = FakeClient([
            "先算得最终答案：1\n复核后最终答案：2",
            "重新核验\n最终答案：2",
        ])
        result = ReasoningAgent(client, flow_config(enable_verification_gated_retry=True)).solve(CALCULATION_PROBLEM, {})
        self.assertEqual(2, len(client.calls))
        self.assertIn("“1”", user_text(client.calls[1]))
        self.assertIn("“2”", user_text(client.calls[1]))
        retry = next(entry for entry in result["trace"] if entry["step"] == "conditional_retry")
        selection = next(entry for entry in result["trace"] if entry["step"] == "verification_gate_selection")
        self.assertEqual("conflict", retry["reason"])
        self.assertEqual(1, selection["accepted"])
        self.assertEqual([0], selection["removed_original_ids"])
        self.assertEqual("2", result["extracted_answer"])

    def test_fail_closed_keeps_invalid_original_when_retry_fails(self):
        client = FakeClient(["最终答案：150%", "再次作答\n最终答案：200%"])
        result = ReasoningAgent(client, flow_config(enable_verification_gated_retry=True)).solve(PROBABILITY_PROBLEM, {})
        selection = next(entry for entry in result["trace"] if entry["step"] == "verification_gate_selection")
        rejected = next(entry for entry in result["trace"] if entry["step"] == "gated_retry_rejected")
        self.assertTrue(selection["kept_originals"])
        self.assertEqual("sanity", rejected["mode"])
        self.assertEqual("150%", result["extracted_answer"])

    def test_unextractable_retry_is_counted_as_rejected(self):
        client = FakeClient(["只有推导没有结论", "仍然没有结论"])
        result = ReasoningAgent(client, flow_config(enable_verification_gated_retry=True)).solve(CALCULATION_PROBLEM, {})
        selection = next(entry for entry in result["trace"] if entry["step"] == "verification_gate_selection")
        rejected = next(entry for entry in result["trace"] if entry["step"] == "gated_retry_rejected")
        self.assertEqual([0], selection["rejected_retry_ids"])
        self.assertEqual("no_answer", rejected["mode"])
        self.assertTrue(selection["kept_originals"])

    def test_budget_cap_still_allows_safe_fallback(self):
        client = FakeClient(["因此接下来"])
        result = ReasoningAgent(client, flow_config(enable_verification_gated_retry=True, max_model_calls=1)).solve(CALCULATION_PROBLEM, {})
        self.assertEqual(1, len(client.calls))
        self.assertTrue(result["final_response"])

    def test_disabled_gate_preserves_legacy_retry_reason(self):
        client = FakeClient(["只有推导没有结论", "最终答案：9"])
        result = ReasoningAgent(client, flow_config()).solve(CALCULATION_PROBLEM, {})
        retry = next(entry for entry in result["trace"] if entry["step"] == "conditional_retry")
        self.assertEqual("no_clear_answer", retry["reason"])
        self.assertNotIn("verification_check", [entry["step"] for entry in result["trace"]])
        self.assertEqual("9", result["extracted_answer"])


class SubmissionConfigTest(unittest.TestCase):
    def test_official_profile_is_k3_8k_window_probe(self):
        self.assertEqual(1, SUBMISSION_CONFIG.policy_sample_times)
        self.assertEqual(0.6, SUBMISSION_CONFIG.policy_temperature)
        self.assertEqual(3, SUBMISSION_CONFIG.max_model_calls)
        self.assertEqual(8192, SUBMISSION_CONFIG.max_tokens)
        self.assertEqual(8192, SUBMISSION_CONFIG.l0_max_tokens)
        self.assertEqual(0, SUBMISSION_CONFIG.verifier_voting_times)
        self.assertFalse(SUBMISSION_CONFIG.enable_dynamic_budget)
        self.assertTrue(SUBMISSION_CONFIG.enable_l0_extended_tokens)
        self.assertTrue(SUBMISSION_CONFIG.enable_task_aware_prompt)
        self.assertFalse(SUBMISSION_CONFIG.enable_verification_gated_retry)
        self.assertFalse(SUBMISSION_CONFIG.enable_truncation_recovery_prompt)
        self.assertTrue(SUBMISSION_CONFIG.enable_adaptive_voting)
        self.assertEqual(3, SUBMISSION_CONFIG.vote_k_max)
        self.assertEqual(2, SUBMISSION_CONFIG.vote_agree_threshold)
        self.assertFalse(SUBMISSION_CONFIG.enable_heterogeneous_reasoners)
        self.assertFalse(SUBMISSION_CONFIG.enable_step_verification)
        self.assertFalse(SUBMISSION_CONFIG.enable_step_revision)
        self.assertFalse(SUBMISSION_CONFIG.enable_conditional_token_retry)
        self.assertFalse(SUBMISSION_CONFIG.enable_explicit_answer_conflict_retry)

    def test_experiment_defaults_are_off(self):
        self.assertFalse(AgentConfig.enable_verification_gated_retry)
        self.assertFalse(AgentConfig.enable_truncation_recovery_prompt)


if __name__ == "__main__":
    unittest.main()
