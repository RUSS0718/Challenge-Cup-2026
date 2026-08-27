import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import evaluate_protocol_ab as protocol_ab
from scripts.evaluate_protocol_ab import (
    VARIANTS,
    CircuitBreaker,
    answer_rows,
    append_answers,
    budget_summary,
    make_config,
    parse_args,
    run_interleaved,
    run_variant,
    summarize_records,
)
from user_agent import POLICY_PROMPT


def _record(idx=0, verdict="correct", diagnostic_reasons=None, latency=1.0, finish="stop"):
    return {
        "idx": idx, "extracted_answer": "42" if verdict == "correct" else "", "verdict": verdict,
        "model_calls": 1, "latency_seconds": latency, "total_completion_tokens": 10,
        "main_finish_reason": finish, "main_marker": True, "retry_used": False,
        "final_response_nonempty": True, "finalization_status": "selected",
        "extracted_present": verdict == "correct", "diagnostic_reasons": list(diagnostic_reasons or []),
    }


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
            ["current", "current_refine", "current_strict", "current_refine_strict", "baseline86", "A", "B", "A+B", "A+B+6144", "failure_backoff", "answer_conflict_retry", "gated_retry", "gated_retry_8k", "temperature04", "temperature08", "adaptive_vote", "adaptive_vote08", "adaptive_vote_k5"],
            list(VARIANTS),
        )

    def test_current_family_reproduces_answer_first_k5_and_bounded_refine(self):
        current = make_config(VARIANTS["current"])
        refine = make_config(VARIANTS["current_refine"])
        strict = make_config(VARIANTS["current_strict"])
        both = make_config(VARIANTS["current_refine_strict"])

        for config in (current, refine, strict, both):
            self.assertEqual(4096, config.max_tokens)
            self.assertEqual(4096, config.l0_max_tokens)
            self.assertEqual(5, config.max_model_calls)
            self.assertTrue(config.enable_adaptive_voting)
            self.assertEqual(5, config.vote_k_max)
            self.assertEqual(3, config.vote_agree_threshold)
            self.assertTrue(config.enable_numeric_answer_first_prompt)
            self.assertFalse(config.enable_numeric_answer_only_prompt)
            self.assertFalse(config.enable_conditional_token_retry)
            self.assertFalse(config.enable_verification_gated_retry)
        self.assertEqual(POLICY_PROMPT, current.policy_prompt)
        self.assertFalse(current.enable_step_verification)
        self.assertFalse(current.enable_strict_numeric_salvage)
        self.assertTrue(refine.enable_step_verification)
        self.assertTrue(refine.enable_step_revision)
        self.assertTrue(strict.enable_strict_numeric_salvage)
        self.assertTrue(both.enable_step_verification)
        self.assertTrue(both.enable_strict_numeric_salvage)
        self.assertEqual(8, budget_summary(VARIANTS["current_refine"])["effective_max_model_calls"])

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
            {"idx": 7, "extracted_answer": "1/2", "verdict": "correct",
             "diagnostic_reasons": [], "latency_seconds": 2.5, "main_finish_reason": "stop"},
            {"idx": 9, "extracted_answer": "", "verdict": "unknown",
             "diagnostic_reasons": ["model_error", "fallback"], "latency_seconds": 120.0,
             "main_finish_reason": None},
        ]
        rows = answer_rows("adaptive_vote", 2, "sample_data/p.jsonl", records)
        self.assertEqual(
            {"input_file": "sample_data/p.jsonl", "round": 2, "variant": "adaptive_vote",
             "idx": 7, "extracted_answer": "1/2", "verdict": "correct",
             "diagnostic_reasons": [], "latency_seconds": 2.5, "main_finish_reason": "stop"},
            rows[0],
        )
        self.assertEqual("", rows[1]["extracted_answer"])
        self.assertEqual(["model_error", "fallback"], rows[1]["diagnostic_reasons"])
        self.assertEqual(120.0, rows[1]["latency_seconds"])
        self.assertIsNone(rows[1]["main_finish_reason"])

    def test_answer_rows_expose_safe_status_fields_without_raw_output(self):
        rows = answer_rows("current_refine", 1, "sample_data/p.jsonl", [{
            "idx": 3, "extracted_answer": "", "verdict": "unknown",
            "diagnostic_reasons": ["model_error"], "latency_seconds": 1.0,
            "main_finish_reason": None, "final_response_nonempty": False,
            "result_status": "error", "model_calls": 2, "model_call_limit": 8,
            "p3_verify_status": "skipped", "p3_revise_status": "not_run",
            "p3_reverify_status": "disabled",
        }])
        self.assertEqual({
            "final_response_nonempty": False, "result_status": "error",
            "model_calls": 2, "model_call_limit": 8,
            "p3_verify_status": "skipped", "p3_revise_status": "not_run",
            "p3_reverify_status": "disabled",
        }, {key: rows[0][key] for key in (
            "final_response_nonempty", "result_status", "model_calls", "model_call_limit",
            "p3_verify_status", "p3_revise_status", "p3_reverify_status",
        )})
        self.assertNotIn("raw_response", rows[0])

    def test_append_answers_is_atomic_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answers.jsonl"
            append_answers(path, [{"idx": 1}])
            append_answers(path, [{"idx": 2}])
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(2, len(lines))
            self.assertNotIn(".tmp", str(path))

    def test_append_mode_mixes_legacy_rows_with_new_diagnostic_rows(self):
        from json import loads

        with tempfile.TemporaryDirectory() as tmp:
            answers = Path(tmp) / "answers.jsonl"
            legacy_row = {"input_file": "x.jsonl", "round": 1, "variant": "baseline86",
                          "idx": 1, "extracted_answer": "", "verdict": "unknown"}
            append_answers(answers, [legacy_row])
            report = run_variant(VARIANTS["baseline86"], [{"idx": 2}], 120, 1, 1, 0.6,
                                 save_answers_to=str(answers), round_no=2, input_file="x.jsonl",
                                 breaker=CircuitBreaker(8),
                                 solve_fn=lambda item: _record(idx=item["idx"]))
            self.assertFalse(report["void"])
            lines = [loads(line) for line in answers.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(2, len(lines))
        self.assertNotIn("diagnostic_reasons", lines[0])
        self.assertEqual([], lines[1]["diagnostic_reasons"])
        self.assertIn("latency_seconds", lines[1])
        self.assertIn("main_finish_reason", lines[1])

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


class TimeoutGuardrailTest(unittest.TestCase):
    def test_parser_rejects_sub_minute_timeout_without_force(self):
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["--timeout-seconds", "5"])
        self.assertEqual(2, ctx.exception.code)

    def test_parser_rejection_message_explains_incident_and_escape_hatch(self):
        with patch.object(sys, "stderr") as stderr:
            with self.assertRaises(SystemExit):
                parse_args(["--timeout-seconds", "5"])
            printed = "".join(call.args[0] for call in stderr.method_calls if call.args)
        self.assertIn("--force", printed)
        self.assertIn("60", printed)

    def test_parser_force_allows_short_timeout_probe(self):
        args = parse_args(["--timeout-seconds", "5", "--force"])
        self.assertTrue(args.force)
        self.assertEqual(5, args.timeout_seconds)

    def test_default_timeout_passes_guardrail(self):
        args = parse_args([])
        self.assertEqual(60, args.timeout_seconds)
        self.assertFalse(args.force)

    def test_breaker_threshold_configurable_with_floor_of_one(self):
        self.assertEqual(4, parse_args(["--max-consecutive-failures", "4"]).max_consecutive_failures)
        self.assertEqual(8, parse_args([]).max_consecutive_failures)
        with self.assertRaises(SystemExit):
            parse_args(["--max-consecutive-failures", "0"])


class CircuitBreakerTest(unittest.TestCase):
    def test_trips_at_threshold_and_tracks_max_streak(self):
        breaker = CircuitBreaker(3)
        self.assertFalse(breaker.record(True))
        self.assertFalse(breaker.record(True))
        self.assertTrue(breaker.record(True))
        self.assertTrue(breaker.tripped)
        self.assertEqual(3, breaker.max_streak)

    def test_success_resets_streak(self):
        breaker = CircuitBreaker(2)
        breaker.record(True)
        breaker.record(False)
        breaker.record(True)
        self.assertFalse(breaker.tripped)
        self.assertEqual(1, breaker.max_streak)

    def test_records_after_trip_do_not_flip_state(self):
        breaker = CircuitBreaker(1)
        self.assertTrue(breaker.record(True))
        self.assertTrue(breaker.record(False))
        self.assertTrue(breaker.tripped)


class RunVariantBreakerTest(unittest.TestCase):
    def test_trips_after_consecutive_model_errors_and_persists_completed_only(self):
        solved = []

        def failing(item):
            solved.append(item["idx"])
            return _record(idx=item["idx"], verdict="unknown", diagnostic_reasons=["model_error"])

        items = [{"idx": i} for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            answers = Path(tmp) / "answers.jsonl"
            report = run_variant(VARIANTS["baseline86"], items, 120, 1, 1, 0.6,
                                 save_answers_to=str(answers), round_no=1, input_file="x.jsonl",
                                 breaker=CircuitBreaker(3), solve_fn=failing)
            rows = [line for line in answers.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual([0, 1, 2], solved)
        self.assertEqual(3, report["dataset_size"])
        self.assertTrue(report["void"])
        self.assertEqual("consecutive_model_errors", report["void_reason"])
        self.assertEqual(3, report["consecutive_failures_max"])
        self.assertEqual([0, 1, 2], [row["idx"] for row in report["items"]])
        self.assertEqual(3, len(rows))

    def test_success_resets_streak_so_batch_completes(self):
        flips = {"count": 0}

        def alternating(item):
            flips["count"] += 1
            failed = flips["count"] % 2 == 1
            reasons = ["model_error"] if failed else []
            return _record(idx=item["idx"], verdict="unknown" if failed else "correct",
                           diagnostic_reasons=reasons)

        items = [{"idx": i} for i in range(8)]
        report = run_variant(VARIANTS["baseline86"], items, 120, 1, 1, 0.6,
                             breaker=CircuitBreaker(2), solve_fn=alternating)
        self.assertFalse(report["void"])
        self.assertIsNone(report["void_reason"])
        self.assertEqual(8, report["dataset_size"])
        self.assertEqual(1, report["consecutive_failures_max"])

    def test_clean_run_reports_void_false_with_observed_streak(self):
        report = run_variant(VARIANTS["baseline86"], [{"idx": 1}], 120, 1, 1, 0.6,
                             breaker=CircuitBreaker(2),
                             solve_fn=lambda item: _record(idx=item["idx"]))
        self.assertFalse(report["void"])
        self.assertIsNone(report["void_reason"])
        self.assertEqual(0, report["consecutive_failures_max"])


class RunInterleavedBreakerTest(unittest.TestCase):
    def test_trip_marks_every_arm_void_with_partial_data(self):
        solved = []

        def failing(variant, item):
            solved.append((variant.name, item["idx"]))
            return _record(idx=item["idx"], verdict="unknown", diagnostic_reasons=["model_error"])

        va, vb = VARIANTS["baseline86"], VARIANTS["adaptive_vote"]
        reports = run_interleaved([va, vb], [{"idx": i} for i in range(4)], 120, 1, 1, 0.6,
                                  breaker=CircuitBreaker(2), solve_fn=failing)
        self.assertEqual(4, len(solved))
        self.assertTrue(all(r["void"] for r in reports))
        self.assertTrue(all(r["void_reason"] == "consecutive_model_errors" for r in reports))
        self.assertTrue(all(r["consecutive_failures_max"] == 2 for r in reports))
        self.assertEqual([2, 2], sorted(r["dataset_size"] for r in reports))


class MainExitCodeTest(unittest.TestCase):
    def test_main_exits_nonzero_when_breaker_trips(self):
        items = [{"problem": "p", "answer": "42", "idx": i} for i in range(6)]

        def fake_solve_one(variant, item, timeout, retry, temperature):
            return _record(idx=item.get("idx"), verdict="unknown", diagnostic_reasons=["model_error"])

        argv = ["evaluate_protocol_ab.py", "--variant", "baseline86",
                "--input-files", "fake.jsonl", "--rounds", "1",
                "--timeout-seconds", "120", "--max-consecutive-failures", "3"]
        with patch.object(sys, "argv", argv), \
                patch.object(protocol_ab, "load_items", lambda path: items), \
                patch.object(protocol_ab, "solve_one", fake_solve_one):
            with self.assertRaises(SystemExit) as ctx:
                protocol_ab.main()
        self.assertEqual(1, ctx.exception.code)

    def test_main_exits_zero_on_clean_run(self):
        items = [{"problem": "p", "answer": "42", "idx": i} for i in range(2)]

        def fake_solve_one(variant, item, timeout, retry, temperature):
            return _record(idx=item.get("idx"))

        argv = ["evaluate_protocol_ab.py", "--variant", "baseline86",
                "--input-files", "fake.jsonl", "--rounds", "1",
                "--timeout-seconds", "120", "--max-consecutive-failures", "3"]
        with patch.object(sys, "argv", argv), \
                patch.object(protocol_ab, "load_items", lambda path: items), \
                patch.object(protocol_ab, "solve_one", fake_solve_one):
            protocol_ab.main()

    def test_main_skips_remaining_variants_after_trip(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from json import loads

        items = [{"problem": "p", "answer": "42", "idx": i} for i in range(3)]

        def fake_solve_one(variant, item, timeout, retry, temperature):
            return _record(idx=item.get("idx"), verdict="unknown", diagnostic_reasons=["model_error"])

        argv = ["evaluate_protocol_ab.py", "--variant", "baseline86", "--variant", "gated_retry",
                "--input-files", "fake.jsonl", "--rounds", "1",
                "--timeout-seconds", "120", "--max-consecutive-failures", "1"]
        buffer = StringIO()
        with patch.object(sys, "argv", argv), \
                patch.object(protocol_ab, "load_items", lambda path: items), \
                patch.object(protocol_ab, "solve_one", fake_solve_one), \
                redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as ctx:
                protocol_ab.main()
        self.assertEqual(1, ctx.exception.code)
        emitted = [loads(line) for line in buffer.getvalue().splitlines() if line.strip()]
        summaries = [entry for entry in emitted if "variant" in entry]
        self.assertEqual(["baseline86"], [entry["variant"] for entry in summaries])
        self.assertTrue(all(entry["void"] for entry in summaries))


if __name__ == "__main__":
    unittest.main()
