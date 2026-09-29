"""Tests for response-free submission diagnostics and promotion gates."""

import unittest

from reasoning_agent.submission_diagnostics import (
    check_record_integrity,
    compact_submission_diagnostics,
    legacy_model_calls,
    promotion_gate,
    summarize_submission_diagnostics,
)


class SubmissionDiagnosticsTest(unittest.TestCase):
    """Keep diagnostics bounded while preserving promotion-relevant counts."""

    def test_compact_projection_drops_model_text(self):
        record = {
            "profile": "arm-v2.1.2-adaptive",
            "arm_v2_summary": {
                "solver_reasoning_mode": "off",
                "final_source": "primary",
                "second_sample_triggered": False,
                "resolver_triggered": False,
            },
            "reasoning_modes": ["off"],
            "primary_candidate_complete": True,
            "model_calls": 1,
            "verdict": "incorrect",
            "final_response": "private model answer",
        }
        diagnostics = compact_submission_diagnostics(record, "arm-v2.1.2-adaptive")
        self.assertEqual("arm_v2.1.2", diagnostics["harness"])
        self.assertEqual("adaptive", diagnostics["lane"])
        self.assertEqual("primary", diagnostics["final_source"])
        self.assertNotIn("final_response", diagnostics)

    def test_compact_projection_records_effective_wire_mode(self):
        diagnostics = compact_submission_diagnostics(
            {
                "arm_v2_summary": {"final_source": "primary"},
                "wire_requests": [{"reasoning_mode": "on", "thinking_mode": True}],
                "verdict": "correct",
            },
            "arm-v2.1.2-on",
        )
        self.assertEqual(["on"], diagnostics["wire_reasoning_modes"])
        self.assertEqual([True], diagnostics["wire_thinking_modes"])
        self.assertTrue(diagnostics["primary_thinking_mode"])

    def test_v213_projection_marks_false_trusted_primary_offline(self):
        diagnostics = compact_submission_diagnostics(
            {
                "arm_v2_summary": {
                    "early_stop": True,
                    "trust_decision": {
                        "trusted": True,
                        "reason": "direct_simple_positive_evidence",
                    },
                    "candidate_generation": {"backend": "direct_solver"},
                },
                "primary_candidate_complete": True,
                "second_sample_triggered": False,
                "resolver_triggered": False,
                "baseline_verdict": "incorrect",
                "verdict": "incorrect",
            },
            "arm-v2.1.3-off",
        )
        self.assertEqual("arm_v2.1.3", diagnostics["harness"])
        self.assertTrue(diagnostics["false_trusted_primary"])
        self.assertEqual("incorrect_local_eval", diagnostics["primary_math_status"])
        self.assertEqual("direct_solver", diagnostics["candidate_generation"]["backend"])

    def test_integrity_rejects_missing_or_duplicate_items(self):
        self.assertTrue(
            check_record_integrity([{"idx": 1}, {"idx": 2}], {1, 2})["integrity_passed"]
        )
        failed = check_record_integrity([{"idx": 1}, {"idx": 1}], {1, 2})
        self.assertFalse(failed["integrity_passed"])
        self.assertEqual([1], failed["integrity_duplicate_ids"])
        self.assertEqual([2], failed["integrity_missing_ids"])
        extra = check_record_integrity([{"idx": 1}, {"idx": 2}, {"idx": 3}], {1, 2})
        self.assertFalse(extra["integrity_passed"])
        self.assertEqual([3], extra["integrity_extra_ids"])

    def test_legacy_call_count_comes_from_sanitized_trace(self):
        self.assertEqual(
            3,
            legacy_model_calls([
                {"stage": "attempt_a", "model_calls": 1},
                {"stage": "finalize", "model_calls": 3},
            ]),
        )
        from scripts import run_arm_v21_eval112_timing as runner

        fields = runner._trace_fields({
            "trace": [
                {"stage": "evidence_ledger", "budget": {"calls": 0, "records": []}},
                {"stage": "legacy_backend", "legacy_trace": [{"model_calls": 3}]},
            ]
        })
        self.assertEqual(3, fields["model_calls"])

        class Client:
            request_diagnostics = [{"reasoning_mode": "on", "thinking_mode": True}]

        wire_fields = runner._trace_fields({"trace": []}, client=Client())
        self.assertEqual(True, wire_fields["wire_requests"][0]["thinking_mode"])

    def test_summary_counts_formation_rescue_and_sources(self):
        records = [
            {
                "arm_v2_summary": {"final_source": "primary"},
                "reasoning_modes": ["off"],
                "primary_candidate_complete": True,
                "second_sample_triggered": False,
                "resolver_triggered": False,
                "model_calls": 1,
                "baseline_verdict": "correct",
                "verdict": "correct",
            },
            {
                "arm_v2_summary": {"final_source": "resolver_a"},
                "reasoning_modes": ["on", "off", "off"],
                "primary_candidate_complete": True,
                "second_sample_triggered": True,
                "resolver_triggered": True,
                "model_calls": 3,
                "baseline_verdict": "incorrect",
                "verdict": "correct",
            },
            {
                "arm_v2_summary": {"final_failure_reason": "second_sample_incomplete"},
                "reasoning_modes": ["off"],
                "primary_candidate_complete": False,
                "second_sample_triggered": True,
                "resolver_triggered": False,
                "model_calls": 2,
                "baseline_verdict": "invalid",
                "verdict": "invalid",
            },
        ]
        report = summarize_submission_diagnostics(
            records,
            profile="arm-v2.1.2-on",
            expected_records=3,
        )
        self.assertEqual(3, report["arm_coverage"])
        self.assertEqual(2, report["candidate_formation_count"])
        self.assertEqual(1, report["resolver_count"])
        self.assertEqual(1, report["second_rescue_count"])
        self.assertEqual(1, report["invalid"])
        self.assertEqual(2, report["correct"])
        self.assertEqual(1, report["final_source_verdicts"]["resolver_a"]["correct"])
        self.assertNotIn("private model answer", report)

    def test_gate_fails_when_score_drops_even_if_invalid_improves(self):
        baseline = {
            "profile": "submission",
            "records": 30,
            "correct": 8,
            "invalid": 5,
            "errors": 0,
            "mean_calls_per_problem": 1.0,
        }
        candidate = {
            "profile": "arm-v2.1.2-on",
            "records": 30,
            "correct": 5,
            "invalid": 3,
            "errors": 0,
            "mean_calls_per_problem": 2.0,
        }
        gate = promotion_gate(baseline, candidate)
        self.assertEqual("NO_GO", gate["status"])
        self.assertFalse(gate["checks"]["correct_not_below_baseline"])
        self.assertTrue(gate["checks"]["invalid_not_above_baseline"])

    def test_gate_fails_closed_for_incomplete_arm(self):
        baseline = {"profile": "submission", "correct": 8, "invalid": 5, "errors": 0}
        candidate = {
            "profile": "arm-v2.1.2-off",
            "correct": 8,
            "invalid": 5,
            "errors": 0,
            "integrity_passed": False,
        }
        gate = promotion_gate(baseline, candidate)
        self.assertEqual("NO_GO", gate["status"])
        self.assertFalse(gate["checks"]["candidate_complete"])

    def test_repeated_gate_fails_closed_for_incomplete_round(self):
        from scripts.run_submission_promotion import _aggregate_gate

        gate = _aggregate_gate(
            {
                "profile": "submission",
                "mean_accuracy": 0.2,
                "mean_invalid_rate": 0.1,
                "mean_errors": 0.0,
                "all_rounds_complete": True,
            },
            {
                "profile": "arm-v2.1.2-adaptive",
                "mean_accuracy": 0.2,
                "mean_invalid_rate": 0.1,
                "mean_errors": 0.0,
                "mean_calls_per_problem": 1.0,
                "all_rounds_complete": False,
            },
        )
        self.assertEqual("NO_GO", gate["status"])
        self.assertFalse(gate["checks"]["candidate_complete"])


if __name__ == "__main__":
    unittest.main()
