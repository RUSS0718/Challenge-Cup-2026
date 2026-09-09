import unittest

from scripts.run_external_hard_sets_smoke import arm_config, compact_trace
from user_agent import COD_NUMERIC_PROMPT, AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class ScriptedClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        return self.response


def solve(problem, config, response):
    client = ScriptedClient(response)
    result = ReasoningAgent(client, config).solve(problem, {})
    return client, result


class CodNumericTest(unittest.TestCase):
    def test_default_off_and_submission_off(self):
        self.assertFalse(AgentConfig().enable_current_cod_numeric)
        self.assertFalse(SUBMISSION_CONFIG.enable_current_cod_numeric)

    def test_numeric_prompt_only_changes_prompt_and_keeps_pipeline(self):
        baseline = AgentConfig(max_model_calls=1, enable_time_convergence=False)
        candidate = AgentConfig(
            max_model_calls=1,
            enable_time_convergence=False,
            enable_current_cod_numeric=True,
        )
        base_client, base_result = solve("计算 3+4", baseline, "最终答案：7")
        cod_client, cod_result = solve("计算 3+4", candidate, "最终答案：7")
        self.assertEqual("7", base_result["final_response"])
        self.assertEqual(base_result["final_response"], cod_result["final_response"])
        self.assertEqual(base_client.calls[0][1:], cod_client.calls[0][1:])
        self.assertNotEqual(base_client.calls[0][0][0]["content"], cod_client.calls[0][0][0]["content"])
        self.assertEqual(COD_NUMERIC_PROMPT, cod_client.calls[0][0][0]["content"])

    def test_nonnumeric_prompt_and_answer_are_unchanged(self):
        response = "最终答案：命题成立\n\n证明：由 x>1 得 x^2>1。"
        baseline = AgentConfig(max_model_calls=1, enable_time_convergence=False)
        candidate = AgentConfig(
            max_model_calls=1,
            enable_time_convergence=False,
            enable_current_cod_numeric=True,
        )
        base_client, base_result = solve("证明：若 x>1，则 x^2>1。", baseline, response)
        cod_client, cod_result = solve("证明：若 x>1，则 x^2>1。", candidate, response)
        self.assertEqual(base_client.calls, cod_client.calls)
        self.assertEqual(base_result, cod_result)

    def test_fsdf_combination_fails_closed_before_model_call(self):
        client = ScriptedClient("最终答案：7")
        with self.assertRaises(ValueError):
            ReasoningAgent(
                client,
                AgentConfig(
                    enable_current_cod_numeric=True,
                    enable_fork_select_deepen_finish=True,
                ),
            ).solve("计算 3+4", {})
        self.assertEqual([], client.calls)

    def test_l0_heterogeneous_path_uses_cod_prompt(self):
        config = AgentConfig(
            enable_current_cod_numeric=True,
            enable_heterogeneous_reasoners=True,
            max_model_calls=1,
            enable_time_convergence=False,
        )
        client, _ = solve("计算 3+4", config, "最终答案：7")
        self.assertEqual(COD_NUMERIC_PROMPT, client.calls[0][0][0]["content"])

    def test_experiment_arms_pin_c0_and_cod(self):
        baseline = arm_config("current_c0")
        candidate = arm_config("current_cod_numeric")
        self.assertFalse(baseline.enable_temporary_answer_bank)
        self.assertFalse(candidate.enable_temporary_answer_bank)
        self.assertFalse(baseline.enable_fork_select_deepen_finish)
        self.assertFalse(candidate.enable_fork_select_deepen_finish)
        self.assertFalse(baseline.enable_current_cod_numeric)
        self.assertTrue(candidate.enable_current_cod_numeric)
        self.assertFalse(baseline.enable_heterogeneous_reasoners)
        self.assertFalse(candidate.enable_heterogeneous_reasoners)
        self.assertEqual(baseline.max_model_calls, candidate.max_model_calls)
        self.assertEqual(baseline.max_tokens, candidate.max_tokens)

    def test_compact_trace_keeps_cod_diagnostics_without_raw_text(self):
        row = compact_trace([{
            "step": "generate_candidate",
            "status": "rejected",
            "prompt": COD_NUMERIC_PROMPT,
            "duration_seconds": 1.0,
        }])[0]
        self.assertEqual(1.0, row["duration_seconds"])
        self.assertNotIn("prompt", row)
        self.assertNotIn("content", row)


if __name__ == "__main__":
    unittest.main()
