import sys
import unittest
from unittest.mock import patch

from scripts.evaluate_protocol_ab import VARIANTS, make_config, parse_args, summarize_records


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
            ["baseline86", "A", "B", "A+B", "A+B+6144", "failure_backoff", "answer_conflict_retry", "temperature04", "temperature08"],
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
