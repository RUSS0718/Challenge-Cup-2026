import json
import unittest
from pathlib import Path

from reasoning_agent.btcs import PacketParser
from user_agent import (
    AgentConfig,
    ReasoningAgent,
    TASK_TYPE_CALCULATION,
    TASK_TYPE_PROOF,
)
from scripts.btcs_fidelity_probe import _load_items, _raw_parse_gate
from tests.support.replay_client import ReplayClient, load_cases


CASES = load_cases()


def make_agent(client, protocol_mode="btcs_frame_v2"):
    return ReasoningAgent(
        client,
        AgentConfig(
            protocol_mode=protocol_mode,
            policy_temperature=0.0,
            enable_time_convergence=False,
            btcs_retry_base_delay_seconds=0.0,
        ),
    )


class BtcsProtocolTest(unittest.TestCase):
    def solve_case(self, name, problem="计算 3+4。", protocol_mode="btcs_frame_v2"):
        client = ReplayClient(CASES[name])
        result = make_agent(client, protocol_mode).solve(problem, {})
        return client, result

    def test_equivalent_answers_stop_after_two_solver_calls(self):
        client, result = self.solve_case("numeric_equivalent")
        self.assertEqual("7", result["extracted_answer"])
        self.assertEqual([4096, 4096], [call["max_tokens"] for call in client.calls])
        final = result["trace"][-1]
        self.assertEqual(2, final["logical_calls"])
        self.assertEqual(2, final["http_attempts"])

    def test_third_solver_forms_local_majority_without_arbiter(self):
        client, result = self.solve_case("numeric_majority")
        self.assertEqual("1", result["extracted_answer"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual(
            0,
            sum("BTCS 受限裁决器" in call["messages"][0]["content"] for call in client.calls),
        )

    def test_arbiter_receives_short_packets_and_selects_existing_candidate(self):
        client, result = self.solve_case("numeric_arbiter")
        self.assertEqual("2", result["extracted_answer"])
        self.assertEqual([4096, 4096, 4096, 256], [call["max_tokens"] for call in client.calls])
        arbiter_user = client.calls[-1]["messages"][1]["content"]
        self.assertIn("A: FINAL: 1", arbiter_user)
        self.assertIn("B: FINAL: 2", arbiter_user)
        self.assertNotIn("BODY:", arbiter_user)
        self.assertTrue(
            any(
                entry.get("step") == "btcs_arbiter"
                and entry.get("status") == "selected_existing"
                for entry in result["trace"]
            )
        )

    def test_arbiter_cannot_create_a_new_answer(self):
        _, result = self.solve_case("numeric_arbiter_new_answer")
        self.assertEqual("1", result["extracted_answer"])
        self.assertTrue(
            any(
                entry.get("step") == "btcs_arbiter"
                and entry.get("status") == "invalid_format"
                for entry in result["trace"]
            )
        )

    def test_invalid_arbiter_format_uses_local_fallback(self):
        _, result = self.solve_case("numeric_arbiter_bad_format")
        self.assertEqual("1", result["extracted_answer"])
        final = result["trace"][-1]
        self.assertEqual("local_fallback_after_invalid_format", final["selection_basis"])

    def test_no_parsed_answers_use_one_continuation_frame(self):
        client, result = self.solve_case("numeric_continuation")
        self.assertEqual("7", result["extracted_answer"])
        self.assertEqual([4096, 4096, 4096, 256], [call["max_tokens"] for call in client.calls])
        continuation = [entry for entry in result["trace"] if entry.get("step") == "btcs_continuation"]
        self.assertEqual("accepted", continuation[-1]["status"])

    def test_unknown_continuation_does_not_guess(self):
        client, result = self.solve_case("numeric_continuation_unknown")
        self.assertEqual("", result["extracted_answer"])
        self.assertEqual(4, len(client.calls))
        self.assertEqual("未能生成有效数学答案。", result["final_response"])

    def test_proof_keeps_selected_candidate_body(self):
        _, result = self.solve_case(
            "proof_complete",
            "证明：对任意实数 x，有 x^2+1>=2|x|。",
        )
        self.assertEqual("成立", result["extracted_answer"])
        self.assertIn("第二步应用基本不等式", result["final_response"])
        self.assertIn("证明：", result["final_response"])
        self.assertEqual(2, result["trace"][-1]["logical_calls"])

    def test_proof_uses_complete_body_when_equivalent_peer_is_truncated(self):
        client = ReplayClient(
            [
                "FINAL: 成立\nEVIDENCE: condition\nBODY:\n前半步因此",
                "FINAL: 成立\nEVIDENCE: condition\nBODY:\n完整第一步。\n完整第二步并得证。",
            ]
        )
        result = make_agent(client).solve("证明：该命题成立。", {})
        self.assertEqual("成立", result["extracted_answer"])
        self.assertIn("完整第二步并得证", result["final_response"])
        self.assertEqual(2, len(client.calls))

    def test_parser_rejects_unknown_and_placeholder_frames(self):
        parser = PacketParser()
        for response in ("FINAL: UNKNOWN", "FINAL: <答案>", "只有推导没有结论"):
            with self.subTest(response=response):
                self.assertIsNone(parser.parse(response, TASK_TYPE_CALCULATION))
        self.assertIsNone(
            parser.parse("FINAL: 成立\nEVIDENCE: x\nBODY: <正文>", TASK_TYPE_PROOF)
        )
        self.assertIsNone(
            parser.parse("简短旧格式：最终答案：7", TASK_TYPE_CALCULATION)
        )

    def test_btcs_config_rejects_protocol_overlay(self):
        with self.assertRaises(ValueError):
            AgentConfig(protocol_mode="btcs_frame_v2", enable_gsa_aggregation=True)

    def test_protocol_hard_caps_ignore_a_larger_requested_call_budget(self):
        client = ReplayClient(
            [
                "FINAL: 1",
                "FINAL: 2",
                "FINAL: 3",
                "SELECT: A",
            ]
        )
        agent = ReasoningAgent(
            client,
            AgentConfig(
                protocol_mode="btcs_frame_v2",
                btcs_max_model_calls=99,
                enable_time_convergence=False,
            ),
        )
        result = agent.solve("计算 3+4。", {})
        self.assertEqual(4, len(client.calls))
        self.assertLessEqual(result["trace"][-1]["logical_calls"], 4)
        self.assertLessEqual(result["trace"][-1]["http_attempts"], 5)

    def test_result_and_trace_are_json_safe_and_problem_free(self):
        problem = "这是不会出现在诊断 trace 中的题面：计算 3+4。"
        client = ReplayClient(CASES["numeric_equivalent"])
        result = make_agent(client).solve(problem, {})
        json.dumps(result, ensure_ascii=False)
        trace_text = json.dumps(result["trace"], ensure_ascii=False)
        self.assertNotIn(problem, trace_text)
        self.assertNotIn("你是 BTCS 结构化数学求解器", trace_text)
        self.assertIsInstance(result["final_response"], str)
        self.assertTrue(result["final_response"])

    def test_v2_numeric_frame_does_not_require_evidence(self):
        client, result = self.solve_case(
            "v2_numeric_final_only", protocol_mode="btcs_frame_v2"
        )
        self.assertEqual("7", result["extracted_answer"])
        self.assertEqual(2, len(client.calls))
        final = result["trace"][-1]
        self.assertTrue(final["per_solve_final_success"])
        self.assertEqual("parsed_candidate", final["selection_source"])

    def test_v2_numeric_arbiter_does_not_invent_an_evidence_field(self):
        client, result = self.solve_case(
            "numeric_arbiter", protocol_mode="btcs_frame_v2"
        )
        self.assertEqual("2", result["extracted_answer"])
        self.assertNotIn(
            "EVIDENCE:", client.calls[-1]["messages"][1]["content"]
        )

    def test_v2_parser_accepts_only_finite_markdown_wrappers(self):
        parser = PacketParser()
        for response in (
            "```text\n- **FINAL: 7**\n```",
            "1. FINAL：7",
            "Final answer: 7",
            "最终答案：7",
        ):
            with self.subTest(response=response):
                packet = parser.parse(
                    response, TASK_TYPE_CALCULATION, frame_version="v2"
                )
                self.assertIsNotNone(packet)
                self.assertEqual("7", packet.normalized_answer)
        for response in (
            "7",
            "```text\nFINAL: 7",
            "说明 Final answer: 7",
            "FINAL: 7\nEVIDENCE: 3+4=7",
            "FINAL: 7\n这里是额外的自然语言尾部",
            "preamble\nFINAL: 7\ngarbage",
        ):
            with self.subTest(response=response):
                self.assertIsNone(
                    parser.parse(response, TASK_TYPE_CALCULATION, frame_version="v2")
                )

    def test_v2_proof_keeps_evidence_and_body(self):
        _, result = self.solve_case(
            "v2_proof_frame",
            "证明：该命题成立。",
            protocol_mode="btcs_frame_v2",
        )
        self.assertEqual("成立", result["extracted_answer"])
        self.assertIn("第二步成立", result["final_response"])
        self.assertEqual("parsed_candidate", result["trace"][-1]["selection_source"])

    def test_v2_packet_diagnostics_and_two_success_metrics_are_separate(self):
        _, result = self.solve_case(
            "v2_packet_diagnostics", protocol_mode="btcs_frame_v2"
        )
        final = result["trace"][-1]
        self.assertTrue(final["per_solve_final_success"])
        self.assertEqual(2, final["parsed_solver_packets"])
        self.assertEqual(3, final["solver_requests"])
        self.assertAlmostEqual(2 / 3, final["raw_packet_parse_rate"], places=6)
        self.assertEqual(
            {"accepted": 2, "no_final": 1, "unknown_final": 0,
             "placeholder_final": 0, "conflicting_final": 0, "missing_body": 0},
            final["packet_diagnostics"],
        )
        self.assertEqual("arbiter_existing_candidate", final["selection_source"])

    def test_v2_diagnostic_keys_are_closed_and_a_failed_solve_is_not_success(self):
        parser = PacketParser()
        samples = (
            ("FINAL: UNKNOWN", "unknown_final", "unknown_final"),
            ("FINAL: <答案>", "placeholder_final", "placeholder_final"),
            ("FINAL: 1\nFINAL: 2", "conflicting_final", "conflicting_final"),
            ("FINAL: 成立\nEVIDENCE: x", "missing_body", "missing_body"),
            ("only prose", "no_final", "no_final"),
        )
        for response, reason, diagnostic_key in samples:
            with self.subTest(response=response):
                packet, actual_reason = parser.parse_with_reason(
                    response,
                    TASK_TYPE_PROOF if "成立" in response else TASK_TYPE_CALCULATION,
                    candidate_id="A",
                    source="direct",
                    frame_version="v2",
                )
                self.assertIsNone(packet)
                self.assertEqual(reason, actual_reason)
                self.assertEqual(diagnostic_key, parser.diagnostic_key(actual_reason))
        self.assertEqual("accepted", parser.diagnostic_key("accepted"))

        _, result = self.solve_case(
            "numeric_continuation_unknown", protocol_mode="btcs_frame_v2"
        )
        self.assertFalse(result["trace"][-1]["per_solve_final_success"])

    def test_v2_proof_requires_evidence(self):
        parser = PacketParser()
        self.assertIsNone(
            parser.parse(
                "FINAL: 成立\nBODY:\n证明成立。",
                TASK_TYPE_PROOF,
                frame_version="v2",
            )
        )

    def test_v2_fidelity_selection_matches_frozen_problem_hash_order(self):
        items = _load_items(
            Path("sample_data/complex_capability_freeze_48.jsonl"),
            10,
            "btcs_frame_v2",
        )
        self.assertEqual(
            [6006, 6034, 6039, 6028, 6004, 6023, 6019, 6041, 6030, 6015],
            [item["idx"] for item in items],
        )

    def test_v2_fidelity_rejects_a_non_frozen_input_hash(self):
        with self.assertRaisesRegex(ValueError, "dataset_sha256_mismatch"):
            _load_items(Path("sample_data/dev.jsonl"), 10, "btcs_frame_v2")

    def test_v2_fidelity_requires_the_frozen_ten_items(self):
        with self.assertRaisesRegex(ValueError, "v2_fidelity_count_must_be_10"):
            _load_items(
                Path("sample_data/complex_capability_freeze_48.jsonl"),
                9,
                "btcs_frame_v2",
            )

    def test_v2_raw_parse_gate_uses_raw_response_count(self):
        applicable, rate, passed = _raw_parse_gate(20, 18)
        self.assertTrue(applicable)
        self.assertEqual(0.9, rate)
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
