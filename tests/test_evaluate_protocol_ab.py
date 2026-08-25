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
from user_agent import POLICY_PROMPT


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
            ["baseline86", "A", "B", "A+B", "A+B+6144", "failure_backoff", "answer_conflict_retry", "gated_retry", "gated_retry_8k", "temperature04", "temperature08", "adaptive_vote", "adaptive_vote08", "adaptive_vote_k5", "legacy_4k_k5", "baseline8k_k2", "single_8k_t0", "k3_8k"],
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

        gated = make_config(VARIANTS["gated_retry"])
        self.assertTrue(gated.enable_verification_gated_retry)
        self.assertFalse(gated.enable_truncation_recovery_prompt)
        self.assertEqual(4096, gated.max_tokens)
        gated_8k = make_config(VARIANTS["gated_retry_8k"])
        self.assertTrue(gated_8k.enable_verification_gated_retry)
        self.assertEqual(8192, gated_8k.max_tokens)
        self.assertEqual(8192, gated_8k.l0_max_tokens)

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

    def test_budget_summary_names_8k_exploration_arm(self):
        summary = budget_summary(VARIANTS["gated_retry_8k"])
        self.assertEqual(8192, summary["max_tokens"])
        self.assertTrue(summary["verification_gated_retry"])
        self.assertFalse(summary["truncation_recovery_prompt"])

    def test_answer_rows_carry_identity_and_verdict(self):
        records = [
            {"idx": 7, "extracted_answer": "1/2", "verdict": "correct"},
            {"idx": 9, "extracted_answer": "", "verdict": "unknown"},
        ]
        rows = answer_rows("adaptive_vote", 2, "sample_data/p.jsonl", records)
        self.assertEqual(
            {"input_file": "sample_data/p.jsonl", "round": 2, "variant": "adaptive_vote",
             "idx": 7, "extracted_answer": "1/2", "verdict": "correct"},
            rows[0],
        )
        self.assertEqual("", rows[1]["extracted_answer"])

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

    def test_summary_reports_gate_mechanism_metrics(self):
        base = {
            "model_calls": 1, "latency_seconds": 1.0,
            "total_completion_tokens": 10, "main_finish_reason": "stop",
            "main_marker": True, "retry_used": False,
            "final_response_nonempty": True, "finalization_status": "selected",
            "extracted_present": True, "verdict": "correct",
            "diagnostic_reasons": [],
        }
        short_circuit = dict(base, gate_short_circuit=True)
        accepted = dict(base, retry_used=True, retry_reason="truncation",
                        gate_short_circuit=False, gate_accepted=1)
        rejected = dict(base, retry_used=True, retry_reason="sanity",
                        gate_short_circuit=False, gate_rejected=1,
                        gate_rejected_modes=["sanity"], gate_kept_originals=True)
        report = summarize_records([short_circuit, accepted, rejected])
        self.assertEqual({"truncation": 1, "sanity": 1}, report["retry_reason_counts"])
        self.assertEqual(1, report["gate_short_circuit_count"])
        self.assertEqual(1, report["gate_accepted_count"])
        self.assertEqual(1, report["gate_rejected_count"])
        self.assertEqual({"sanity": 1}, report["gate_rejected_mode_counts"])
        self.assertEqual(1, report["gate_kept_originals_count"])


if __name__ == "__main__":
    unittest.main()
