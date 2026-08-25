import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.evaluate_protocol_ab import (
    VARIANTS,
    answer_rows,
    append_answers,
    budget_summary,
    make_config,
    parse_args,
    run_interleaved,
    summarize_records,
)
from user_agent import POLICY_PROMPT, ReasoningAgent


class ProtocolAbTest(unittest.TestCase):
    def test_parser_accepts_single_variant_round_and_append(self):
        args = parse_args([
            "--variant", "baseline86", "--round", "3", "--append-output",
        ])
        self.assertEqual(["baseline86"], args.variants)
        self.assertEqual([3], args.rounds)
        self.assertTrue(args.append_output)

    def test_resume_arguments_support_one_new_round(self):
        with patch.object(sys, "argv", ["evaluate_protocol_ab.py", "--rounds", "1", "--round-start", "2", "--append-output", "--output-file", "report.json"]):
            args = parse_args()
        self.assertEqual(1, args.rounds)
        self.assertEqual(2, args.round_start)
        self.assertTrue(args.append_output)
    def test_declares_isolated_variants(self):
        self.assertEqual(
            ["baseline86", "A", "B", "A+B", "A+B+6144", "failure_backoff", "answer_conflict_retry", "temperature04", "temperature08", "adaptive_vote", "adaptive_vote08", "adaptive_vote_k5", "legacy_4k_k5", "legacy_4k_k5_exit2", "legacy_4k_k5_length_pressure", "legacy_4k_k5_substitution", "legacy_4k_k5_answer_first", "baseline8k_k2", "single_8k_t0", "k3_8k"],
            list(VARIANTS),
        )

    def test_variant_flags_are_single_variable(self):
        baseline = make_config(VARIANTS["baseline86"])
        a = make_config(VARIANTS["A"])
        b = make_config(VARIANTS["B"])
        ab_retry = make_config(VARIANTS["A+B+6144"])
        self.assertFalse(baseline.enable_numeric_answer_first_prompt)
        self.assertTrue(baseline.enable_numeric_answer_only_prompt)
        self.assertFalse(baseline.enable_strict_numeric_salvage)
        self.assertFalse(baseline.enable_conditional_token_retry)
        self.assertTrue(a.enable_numeric_answer_first_prompt)
        self.assertFalse(a.enable_numeric_answer_only_prompt)
        self.assertFalse(a.enable_strict_numeric_salvage)
        self.assertTrue(b.enable_strict_numeric_salvage)
        self.assertFalse(b.enable_numeric_answer_first_prompt)
        self.assertTrue(b.enable_numeric_answer_only_prompt)
        self.assertTrue(ab_retry.enable_numeric_answer_first_prompt)
        self.assertFalse(ab_retry.enable_numeric_answer_only_prompt)
        self.assertTrue(ab_retry.enable_strict_numeric_salvage)
        self.assertTrue(ab_retry.enable_conditional_token_retry)
        self.assertEqual(6144, ab_retry.conditional_retry_max_tokens)

    def test_temperature_variants_change_only_policy_temperature(self):
        baseline = make_config(VARIANTS["baseline86"])
        cool = make_config(VARIANTS["temperature04"])
        warm = make_config(VARIANTS["temperature08"])
        self.assertEqual(0.6, baseline.policy_temperature)
        self.assertEqual(0.4, cool.policy_temperature)
        self.assertEqual(0.8, warm.policy_temperature)
        self.assertEqual(baseline.max_tokens, cool.max_tokens)
        self.assertEqual(baseline.max_model_calls, warm.max_model_calls)

    def test_adaptive_vote_variant_enables_voting_with_three_calls(self):
        config = make_config(VARIANTS["adaptive_vote"])
        self.assertTrue(config.enable_adaptive_voting)
        self.assertEqual(3, config.vote_k_max)
        self.assertEqual(2, config.vote_agree_threshold)
        self.assertEqual(3, config.max_model_calls)
        self.assertFalse(make_config(VARIANTS["baseline86"]).enable_adaptive_voting)

    def test_budget_summary_reflects_effective_call_cap(self):
        baseline = budget_summary(VARIANTS["baseline86"])
        vote = budget_summary(VARIANTS["adaptive_vote"])
        self.assertEqual(2, baseline["max_model_calls"])
        self.assertFalse(baseline["adaptive_voting"])
        self.assertEqual(3, vote["max_model_calls"])
        self.assertTrue(vote["adaptive_voting"])

    def test_answer_rows_carry_identity_and_verdict(self):
        records = [
            {"idx": 7, "extracted_answer": "1/2", "verdict": "correct",
             "total_completion_tokens": 3900, "main_finish_reason": "length"},
            {"idx": 9, "extracted_answer": "", "verdict": "unknown",
             "total_completion_tokens": 800, "main_finish_reason": "stop"},
        ]
        rows = answer_rows("adaptive_vote", 2, "sample_data/p.jsonl", records)
        self.assertEqual(
            {"input_file": "sample_data/p.jsonl", "round": 2, "variant": "adaptive_vote",
             "idx": 7, "extracted_answer": "1/2", "verdict": "correct",
             "total_completion_tokens": 3900, "main_finish_reason": "length"},
            rows[0],
        )
        self.assertEqual("", rows[1]["extracted_answer"])
        self.assertEqual(800, rows[1]["total_completion_tokens"])
        self.assertEqual("stop", rows[1]["main_finish_reason"])

    def test_answer_rows_tolerate_missing_telemetry(self):
        rows = answer_rows("baseline86", 1, "p.jsonl", [{"idx": 1, "verdict": "correct"}])
        self.assertIsNone(rows[0]["total_completion_tokens"])
        self.assertIsNone(rows[0]["main_finish_reason"])

    def test_solve_one_records_substitution_statuses(self):
        from scripts.evaluate_protocol_ab import solve_one
        from unittest.mock import patch

        class FakeClient:
            def __init__(self, responses):
                self.responses = iter(responses)
                self.finish_reasons = []
                self.completion_tokens = []
                self.raw_contents = []
                self.latencies = []

            def chat(self, messages, temperature, max_tokens):
                self.finish_reasons.append("stop")
                self.completion_tokens.append(100)
                response = next(self.responses)
                self.raw_contents.append(response)
                self.latencies.append(0.1)
                return response

        client = FakeClient([
            "最终答案：7",
            "print(candidate**2 == candidate + 2)",
            "最终答案：7",
            "最终答案：7",
            "最终答案：7",
        ])
        variant = VARIANTS["legacy_4k_k5_substitution"]
        agent = ReasoningAgent(client=client, config=make_config(variant))
        item = {"idx": 1, "problem": "已知 x 满足 x**2 = x + 2，求 x", "answer": "2"}
        with patch("scripts.evaluate_protocol_ab._get_agent", return_value=(client, agent)):
            record = solve_one(variant, item, 60, 1, 0.6)
        self.assertTrue(record["substitution_statuses"])
        self.assertIn("SUCCESS", record["substitution_statuses"])

    def test_summary_counts_substitution_statuses(self):
        report = summarize_records([
            {"model_calls": 1, "latency_seconds": 1.0, "total_completion_tokens": 100,
             "main_finish_reason": "stop", "main_marker": True, "retry_used": False,
             "final_response_nonempty": True, "finalization_status": "selected",
             "extracted_present": True, "verdict": "correct", "diagnostic_reasons": [],
             "substitution_statuses": ["SUCCESS"]},
            {"model_calls": 1, "latency_seconds": 1.0, "total_completion_tokens": 100,
             "main_finish_reason": "stop", "main_marker": True, "retry_used": False,
             "final_response_nonempty": True, "finalization_status": "selected",
             "extracted_present": True, "verdict": "correct", "diagnostic_reasons": [],
             "substitution_statuses": ["ERROR"]},
        ])
        self.assertEqual({"SUCCESS": 1, "ERROR": 1}, report["substitution_status_counts"])

    def test_append_answers_is_atomic_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answers.jsonl"
            append_answers(path, [{"idx": 1}])
            append_answers(path, [{"idx": 2}])
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(2, len(lines))
            self.assertNotIn(".tmp", str(path))

    def test_interleave_alternates_variant_order_per_item(self):
        va, vb = VARIANTS["baseline86"], VARIANTS["adaptive_vote"]
        calls = []

        def fake_solve(variant, item):
            calls.append((item["idx"], variant.name))
            return {
                "idx": item["idx"], "extracted_answer": "", "verdict": "unknown",
                "model_calls": 1, "latency_seconds": 1.0, "total_completion_tokens": 10,
                "main_finish_reason": "stop", "main_marker": True, "retry_used": False,
                "final_response_nonempty": True, "finalization_status": "selected",
                "extracted_present": False, "diagnostic_reasons": [],
            }

        items = [{"idx": 0}, {"idx": 1}, {"idx": 2}]
        reports = run_interleaved([va, vb], items, 60, 1, 3, 0.6, solve_fn=fake_solve)
        self.assertEqual(
            [(0, "baseline86"), (0, "adaptive_vote"),
             (1, "adaptive_vote"), (1, "baseline86"),
             (2, "baseline86"), (2, "adaptive_vote")],
            calls,
        )
        self.assertEqual({"baseline86", "adaptive_vote"}, {r["variant"] for r in reports})
        self.assertEqual([3, 3], sorted(r["dataset_size"] for r in reports))
        self.assertTrue(all(r["interleaved"] for r in reports))

    def test_interleave_rotates_three_arms_per_item(self):
        va, vb, vc = (VARIANTS["baseline86"], VARIANTS["adaptive_vote"], VARIANTS["adaptive_vote08"])
        calls = []

        def fake_solve(variant, item):
            calls.append((item["idx"], variant.name))
            return {
                "idx": item["idx"], "extracted_answer": "", "verdict": "unknown",
                "model_calls": 1, "latency_seconds": 1.0, "total_completion_tokens": 10,
                "main_finish_reason": "stop", "main_marker": True, "retry_used": False,
                "final_response_nonempty": True, "finalization_status": "selected",
                "extracted_present": False, "diagnostic_reasons": [],
            }

        items = [{"idx": 0}, {"idx": 1}]
        reports = run_interleaved([va, vb, vc], items, 60, 1, 3, 0.6, solve_fn=fake_solve)
        self.assertEqual(
            [(0, "baseline86"), (0, "adaptive_vote"), (0, "adaptive_vote08"),
             (1, "adaptive_vote"), (1, "adaptive_vote08"), (1, "baseline86")],
            calls,
        )
        self.assertEqual([2, 2, 2], sorted(r["dataset_size"] for r in reports))

    def test_interleave_requires_at_least_two_variants(self):
        with self.assertRaises(SystemExit):
            run_interleaved([VARIANTS["baseline86"]], [], 60, 1, 3, 0.6, solve_fn=lambda v, i: {})

    def test_parser_accepts_save_answers_to(self):
        args = parse_args(["--save-answers-to", "docs/ab_answers.jsonl"])
        self.assertEqual("docs/ab_answers.jsonl", args.save_answers_to)
        self.assertIsNone(parse_args([]).save_answers_to)

    def test_adaptive_vote_k5_variant_uses_five_call_consensus(self):
        config = make_config(VARIANTS["adaptive_vote_k5"])
        self.assertTrue(config.enable_adaptive_voting)
        self.assertEqual(5, config.vote_k_max)
        self.assertEqual(3, config.vote_agree_threshold)
        self.assertEqual(5, config.max_model_calls)
        self.assertEqual(0.6, config.policy_temperature)

    def test_budget_summary_reflects_k5_cap(self):
        summary = budget_summary(VARIANTS["adaptive_vote_k5"])
        self.assertEqual(5, summary["max_model_calls"])
        self.assertEqual(5, summary["vote_k_max"])

    def test_legacy_4k_k5_pins_official_r2_snapshot(self):
        # Official R2 (accuracy 9.82%): 4096 ceiling, k5 consensus on POLICY_PROMPT.
        config = make_config(VARIANTS["legacy_4k_k5"])
        self.assertTrue(config.enable_adaptive_voting)
        self.assertEqual(5, config.vote_k_max)
        self.assertEqual(3, config.vote_agree_threshold)
        self.assertEqual(5, config.max_model_calls)
        self.assertEqual(4096, config.max_tokens)
        self.assertIs(POLICY_PROMPT, config.policy_prompt)
        self.assertEqual(0.6, config.policy_temperature)

    def test_legacy_4k_k5_exit2_changes_only_agreement_threshold(self):
        baseline = make_config(VARIANTS["legacy_4k_k5"])
        challenger = make_config(VARIANTS["legacy_4k_k5_exit2"])
        self.assertEqual(2, challenger.vote_agree_threshold)
        self.assertEqual(baseline.vote_k_max, challenger.vote_k_max)
        self.assertEqual(baseline.max_model_calls, challenger.max_model_calls)
        self.assertEqual(baseline.max_tokens, challenger.max_tokens)
        self.assertIs(baseline.policy_prompt, challenger.policy_prompt)
        self.assertEqual(baseline.policy_temperature, challenger.policy_temperature)

    def test_legacy_challengers_pin_their_own_4k_k5_fields(self):
        baseline = make_config(VARIANTS["legacy_4k_k5"])
        pressure = make_config(VARIANTS["legacy_4k_k5_length_pressure"])
        substitution = make_config(VARIANTS["legacy_4k_k5_substitution"])
        answer_first = make_config(VARIANTS["legacy_4k_k5_answer_first"])

        for config in (pressure, substitution, answer_first):
            self.assertEqual(4096, config.max_tokens)
            self.assertEqual(4096, config.l0_max_tokens)
            self.assertTrue(config.enable_adaptive_voting)
            self.assertEqual(5, config.vote_k_max)
            self.assertEqual(3, config.vote_agree_threshold)
            self.assertIs(POLICY_PROMPT, config.policy_prompt)
            self.assertEqual(0.6, config.policy_temperature)
        self.assertEqual(5, pressure.max_model_calls)
        self.assertEqual(10, substitution.max_model_calls)
        self.assertTrue(substitution.enable_substitution_check)
        self.assertFalse(pressure.enable_substitution_check)
        self.assertFalse(substitution.enable_numeric_answer_first_prompt)
        self.assertTrue(answer_first.enable_numeric_answer_first_prompt)
        self.assertFalse(answer_first.enable_numeric_answer_only_prompt)

    def test_legacy_challenger_budget_summary_is_explicit(self):
        pressure = budget_summary(VARIANTS["legacy_4k_k5_length_pressure"])
        substitution = budget_summary(VARIANTS["legacy_4k_k5_substitution"])
        answer_first = budget_summary(VARIANTS["legacy_4k_k5_answer_first"])

        self.assertEqual(4096, pressure["max_tokens"])
        self.assertEqual(5, pressure["max_model_calls"])
        self.assertEqual(10, substitution["max_model_calls"])
        self.assertTrue(substitution["substitution_check"])
        self.assertTrue(answer_first["numeric_prompt"])

    def test_baseline8k_k2_pins_8k_consensus(self):
        config = make_config(VARIANTS["baseline8k_k2"])
        self.assertTrue(config.enable_adaptive_voting)
        self.assertEqual(2, config.vote_k_max)
        self.assertEqual(2, config.vote_agree_threshold)
        self.assertEqual(2, config.max_model_calls)
        self.assertEqual(8192, config.max_tokens)
        self.assertIs(POLICY_PROMPT, config.policy_prompt)
        self.assertEqual(0.6, config.policy_temperature)

    def test_single_8k_t0_is_one_greedy_call(self):
        config = make_config(VARIANTS["single_8k_t0"])
        self.assertFalse(config.enable_adaptive_voting)
        self.assertEqual(1, config.max_model_calls)
        self.assertEqual(8192, config.max_tokens)
        self.assertIs(POLICY_PROMPT, config.policy_prompt)
        self.assertEqual(0.0, config.policy_temperature)

    def test_k3_8k_is_three_sample_majority(self):
        config = make_config(VARIANTS["k3_8k"])
        self.assertTrue(config.enable_adaptive_voting)
        self.assertEqual(3, config.vote_k_max)
        self.assertEqual(2, config.vote_agree_threshold)
        self.assertEqual(3, config.max_model_calls)
        self.assertEqual(8192, config.max_tokens)
        self.assertIs(POLICY_PROMPT, config.policy_prompt)

    def test_summary_reports_invalid_calls_and_safe_diagnostics(self):
        report = summarize_records([
            {
                "model_calls": 1, "latency_seconds": 1.0,
                "total_completion_tokens": 100, "main_finish_reason": "stop",
                "main_marker": True, "retry_used": False,
                "final_response_nonempty": True, "finalization_status": "selected",
                "extracted_present": True, "verdict": "correct",
                "diagnostic_reasons": [],
            },
            {
                "model_calls": 2, "latency_seconds": 2.0,
                "total_completion_tokens": 200, "main_finish_reason": "length",
                "main_marker": False, "retry_used": True,
                "final_response_nonempty": True, "finalization_status": "fallback",
                "extracted_present": False, "verdict": "unknown",
                "diagnostic_reasons": ["no_marker", "fallback"],
            },
        ])
        self.assertEqual(1, report["correct"])
        self.assertEqual(1, report["invalid"])
        self.assertEqual(1, report["retry_count"])
        self.assertEqual(0.5, report["main_length_rate"])
        self.assertEqual({"no_marker": 1, "fallback": 1}, report["diagnostic_reason_counts"])
        self.assertNotIn("raw_responses", report)


if __name__ == "__main__":
    unittest.main()
