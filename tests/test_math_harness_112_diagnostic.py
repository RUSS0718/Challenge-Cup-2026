import unittest
from unittest.mock import patch

from scripts.run_math_harness_112_diagnostic import (
    EXPECTED_ITEMS,
    MAX_CALLS,
    MAX_REQUESTED_TOKENS,
    build_report,
    diagnostic_config,
    solve_one,
)


class MathHarness112DiagnosticTest(unittest.TestCase):
    def test_diagnostic_profile_is_explicitly_bank_off_and_bounded(self):
        config = diagnostic_config()
        self.assertTrue(config.enable_constraint_fit_harness)
        self.assertFalse(config.enable_temporary_answer_bank)
        self.assertEqual("off", config.harness_bank_mode)
        self.assertEqual(MAX_CALLS, config.harness_max_model_calls)
        self.assertEqual(MAX_REQUESTED_TOKENS, config.harness_total_token_budget)

    def test_optional_timeout_does_not_override_preserved_final_answer(self):
        trace = [
            {"stage": "submission_gateway", "bank_mode": "off", "status": "disabled"},
            {
                "stage": "evidence_ledger",
                "budget": {
                    "calls": 2,
                    "requested_tokens": 12288,
                    "actual_completion_tokens": None,
                    "actual_token_records": 0,
                    "budget_violated": False,
                    "records": [
                        {"status": "ok", "finish_reason": None, "error_category": None},
                        {"status": "error", "finish_reason": None, "error_category": "timeout"},
                    ],
                },
                "calls": [
                    {"status": "ok", "finish_reason": "stop", "error_category": None},
                    {"status": "error", "finish_reason": None, "error_category": "timeout"},
                ],
                "candidates": [],
            },
        ]

        class FakeAgent:
            def __init__(self, client=None, config=None):
                pass

            def solve(self, problem, metadata):
                return {
                    "final_response": "17",
                    "extracted_answer": "17",
                    "trace": trace,
                }

        with patch("scripts.run_math_harness_112_diagnostic.InternChatClient", return_value=object()), patch(
            "scripts.run_math_harness_112_diagnostic.ReasoningAgent",
            FakeAgent,
        ):
            row = solve_one({"idx": "case-17", "problem": "求值", "answer": "17"})

        self.assertTrue(row["model_error"])
        self.assertTrue(row["timeout"])
        self.assertEqual("correct", row["outcome"])
        self.assertEqual(["stop", "missing"], row["finish_reasons"])

    def test_report_is_diagnostic_and_does_not_claim_capability(self):
        rows = [
            {
                "outcome": "correct",
                "verdict": "correct",
                "model_error": False,
                "timeout": False,
                "bank_violation": False,
                "budget_violated": False,
                "model_calls": 1,
                "requested_tokens": 4096,
                "actual_completion_tokens": None,
                "finish_reasons": ["stop"],
                "candidate_status_counts": {"parsed": 1},
                "candidate_count": 1,
                "duration_seconds": 1.0,
            }
        ]
        report = build_report(rows, 1.0, final=True)
        self.assertEqual("NONE", report["capability_conclusion"])
        self.assertTrue(report["diagnostic_only"])
        self.assertEqual(1, report["correct"])
        self.assertEqual(1, report["candidate_formed_rows"])
        self.assertEqual(EXPECTED_ITEMS, report["expected_records"])
        self.assertIn("incomplete_records", report["health_violations"])


if __name__ == "__main__":
    unittest.main()
