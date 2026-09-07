import json
import unittest

from reasoning_agent.host_loop_context import prepare_host_loop_context
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        return self.responses.pop(0)


def packets():
    return [
        "SKILL_CHOICE: NONE\nAPPLICABILITY: NO\nGOAL: 求唯一值\nANSWER_TYPE: 数值\nCONSTRAINTS: 等式",
        "BRANCH: B\nCLAIMS:\nB1: 1+2=3\nCANDIDATE_B: 3\nOPEN: 检查代回",
        "BRANCH: C\nCLAIMS:\nC1: 1+2=3\nCANDIDATE_C: 3\nOPEN: 无",
        "PRIMARY_BRANCH: B\nPRIMARY_REASON: B 覆盖约束\nSUPPORTED_CLAIMS: none\nAUXILIARY_CLAIMS: none\nREFUTED_CLAIMS: none\nUNRESOLVED_CLAIMS: B1, C1\nCANDIDATE_D: 3\nOPEN: 完成",
        "FINAL: 3",
    ]


class HostLoopContextTest(unittest.TestCase):
    def test_new_host_loop_components_are_off_in_submission_profile(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_host_intake)
        self.assertFalse(SUBMISSION_CONFIG.enable_bounded_obligation_extractor)

    def test_prompt_hints_are_bounded_and_exclude_metadata_values(self):
        context = prepare_host_loop_context(
            "证明任意 x != 0 时 1/x = 1/x。",
            {"idx": 9, "gold": "secret-answer", "domain": "algebra"},
            answer_type="proof",
            extract_obligations=True,
        )
        hints = context.prompt_hints(500)
        self.assertLessEqual(len(hints), 500)
        self.assertIn("HOST_HINTS", hints)
        self.assertNotIn("secret-answer", hints)
        self.assertTrue(context.obligations.obligations)
        json.dumps(context.trace_event(), ensure_ascii=False)

    def test_reasoning_agent_keeps_context_opt_in(self):
        disabled_client = ScriptedClient(["最终答案：3"])
        disabled = ReasoningAgent(disabled_client, AgentConfig(enable_step_verification=False))
        disabled_result = disabled.solve("计算 1+2", {})
        self.assertFalse(any(item.get("stage") == "host_intake" for item in disabled_result["trace"]))

        enabled_client = ScriptedClient(packets())
        enabled = ReasoningAgent(
            enabled_client,
            AgentConfig(
                enable_fesf_v1=True,
                enable_fesf_exact_eval=False,
                enable_host_intake=True,
                enable_bounded_obligation_extractor=True,
            ),
        )
        result = enabled.solve("证明任意 x != 0 时 1/x = 1/x。", {"idx": 1, "gold": "secret"})
        self.assertEqual("3", result["final_response"])
        self.assertTrue(any(item.get("stage") == "host_intake" for item in result["trace"]))
        self.assertIn("HOST_HINTS", enabled_client.calls[0][0][1]["content"])
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))

    def test_disabled_bridge_matches_frozen_fesf_request_budget(self):
        problem = "求满足关系的唯一数值"
        baseline_client = ScriptedClient(packets())
        baseline = ReasoningAgent(
            baseline_client,
            AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False),
        )
        baseline_result = baseline.solve(problem, {"idx": 1, "gold": "secret"})
        disabled_client = ScriptedClient(packets())
        disabled = ReasoningAgent(disabled_client, SUBMISSION_CONFIG)
        disabled_result = disabled.solve(problem, {"idx": 1, "gold": "secret"})
        self.assertEqual([call[2] for call in baseline_client.calls], [call[2] for call in disabled_client.calls])
        self.assertEqual(len(baseline_client.calls), len(disabled_client.calls))
        self.assertEqual(baseline_result["final_response"], disabled_result["final_response"])
        self.assertFalse(any(item.get("stage") == "host_intake" for item in disabled_result["trace"]))
        self.assertFalse(SUBMISSION_CONFIG.enable_host_intake)
        self.assertFalse(SUBMISSION_CONFIG.enable_bounded_obligation_extractor)

    def test_intake_and_obligation_switches_are_independently_constructible(self):
        problem = "证明任意 x != 0 时 1/x = 1/x。"
        metadata = {"idx": 2, "gold": "secret-answer"}
        combinations = (
            (True, False),
            (False, True),
            (True, True),
        )
        for intake, obligation in combinations:
            with self.subTest(intake=intake, obligation=obligation):
                client = ScriptedClient(packets())
                agent = ReasoningAgent(
                    client,
                    AgentConfig(
                        enable_fesf_v1=True,
                        enable_fesf_exact_eval=False,
                        enable_host_intake=intake,
                        enable_bounded_obligation_extractor=obligation,
                    ),
                )
                result = agent.solve(problem, metadata)
                blob = json.dumps(result, ensure_ascii=False)
                prompt = client.calls[0][0][1]["content"]
                self.assertEqual("3", result["final_response"])
                self.assertEqual(5, len(client.calls))
                self.assertEqual([2048, 2048, 2048, 8192, 4096], [call[2] for call in client.calls])
                self.assertIn("HOST_HINTS", prompt)
                self.assertNotIn("secret-answer", prompt)
                self.assertNotIn("secret-answer", blob)
                self.assertNotIn("problem_hash", prompt)
                event = next(item for item in result["trace"] if item.get("stage") == "host_intake")
                self.assertIn(event["profile"], {"short", "structured", "long"})
                self.assertIn("obligation_count", event)
                self.assertNotIn("metadata", event)
                if obligation:
                    self.assertGreater(event["obligation_count"], 0)
                else:
                    self.assertEqual(0, event["obligation_count"])

    def test_consecutive_and_concurrent_solves_do_not_share_context(self):
        import threading

        def run(value):
            client = ScriptedClient(packets())
            agent = ReasoningAgent(
                client,
                AgentConfig(
                    enable_fesf_v1=True,
                    enable_fesf_exact_eval=False,
                    enable_host_intake=True,
                    enable_bounded_obligation_extractor=True,
                ),
            )
            return agent.solve(f"证明任意 x 时 {value}+0={value}。", {"idx": value, "gold": f"secret-{value}"})

        first = run(1)
        second = run(2)
        self.assertEqual("3", first["final_response"])
        self.assertEqual("3", second["final_response"])
        self.assertNotEqual(id(first["trace"]), id(second["trace"]))
        outputs = [None, None, None]
        threads = [
            threading.Thread(target=lambda i=i: outputs.__setitem__(i, run(i)))
            for i in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(["3", "3", "3"], [item["final_response"] for item in outputs])
        for item in outputs:
            blob = json.dumps(item, ensure_ascii=False)
            self.assertNotIn("secret-", blob)

    def test_l0_path_is_unaffected_by_host_loop_bridge(self):
        client = ScriptedClient(["FINAL: 7"])
        agent = ReasoningAgent(
            client,
            AgentConfig(
                enable_fesf_v1=True,
                enable_fesf_exact_eval=False,
                enable_host_intake=True,
                enable_bounded_obligation_extractor=True,
            ),
        )
        result = agent.solve("计算 3+4", {"gold": "secret"})
        self.assertEqual([4096], [call[2] for call in client.calls])
        self.assertEqual("7", result["final_response"])
        self.assertTrue(any(item.get("stage") == "host_intake" for item in result["trace"]))
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
