"""Unit tests for P0.1 scan_budget gate, ranking, adoption, and pollution logic.

These tests exercise the pure functions in ``scripts.scan_budget`` without
requiring a real LLM client or network access.
"""

import unittest

from scripts.archive.scan_budget import (
    BASELINE_CORRECT,
    TOTAL_BUDGET_SECONDS,
    adopt_best_tier,
    count_connectivity_errors,
    gate_check,
    is_polluted_by_connectivity,
    rank_tiers,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal report-like dicts that the tested functions expect.
# ---------------------------------------------------------------------------

def _report(**overrides):
    """Minimal valid report with clean baseline values."""
    base = {
        "dataset_size": 23,
        "accuracy": 0.2609,               # 6 / 23
        "average_model_calls": 1.57,
        "average_latency_seconds": 5.8,
        "empty_final_response_count": 0,
        "empty_response_count": 0,
        "timeout_count": 0,
        "total_elapsed_seconds": 134.0,
        "within_call_cap": True,
        "records": [
            {
                "failure_reasons": [],
            }
        ],
    }
    base.update(overrides)
    return base


def _report_with_connectivity():
    """A report polluted by 3 connectivity errors."""
    return _report(
        accuracy=0.0,
        records=[
            {"failure_reasons": ["model_call_failed:connectivity"]},
            {"failure_reasons": ["model_call_failed:connectivity"]},
            {"failure_reasons": ["model_call_failed:connectivity"]},
        ],
    )


def _report_above_baseline(correct: int = 7):
    """A report that passes the accuracy gate (correct > BASELINE_CORRECT)."""
    acc = correct / 23.0
    return _report(accuracy=acc)


# ---------------------------------------------------------------------------
# count_connectivity_errors / is_polluted_by_connectivity
# ---------------------------------------------------------------------------

class ConnectivityPollutionTest(unittest.TestCase):
    def test_count_connectivity_errors_zero_when_clean(self):
        report = _report()
        self.assertEqual(0, count_connectivity_errors(report))

    def test_count_connectivity_errors_sums_all_records(self):
        report = _report_with_connectivity()
        self.assertEqual(3, count_connectivity_errors(report))

    def test_count_connectivity_errors_case_insensitive(self):
        report = _report(
            records=[
                {"failure_reasons": ["Model_Call_Failed:Connectivity"]},
                {"failure_reasons": ["MODEL_CALL_FAILED:CONNECTIVITY"]},
            ],
        )
        self.assertEqual(2, count_connectivity_errors(report))

    def test_is_polluted_false_when_clean(self):
        self.assertFalse(is_polluted_by_connectivity(_report()))

    def test_is_polluted_true_when_present(self):
        self.assertTrue(is_polluted_by_connectivity(_report_with_connectivity()))

# ---------------------------------------------------------------------------
# gate_check
# ---------------------------------------------------------------------------

class GateCheckTest(unittest.TestCase):
    def test_clean_report_passes_all_gates(self):
        result = gate_check(_report_above_baseline(7))
        self.assertTrue(result["passed"], f"Expected pass, got: {result['failure_summary']}")
        self.assertEqual([], result["failure_summary"])
        self.assertTrue(result["checks"]["accuracy_above_baseline"])
        self.assertTrue(result["checks"]["all_non_empty_response"])
        self.assertTrue(result["checks"]["zero_timeouts"])
        self.assertTrue(result["checks"]["within_600s_budget"])
        self.assertTrue(result["checks"]["within_call_cap"])
        self.assertTrue(result["checks"]["no_connectivity_pollution"])

    def test_fails_when_accuracy_not_above_baseline(self):
        report = _report(accuracy=6 / 23.0)  # exactly baseline, not above
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["accuracy_above_baseline"])
        self.assertIn("accuracy", result["failure_summary"][0].lower())

    def test_fails_when_final_response_is_empty(self):
        report = _report_above_baseline(7)
        report["empty_final_response_count"] = 1
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["all_non_empty_response"])

    def test_fails_when_frozen_dataset_is_incomplete(self):
        report = _report_above_baseline(7)
        report["dataset_size"] = 22
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["frozen_dataset_complete"])

    def test_fails_when_timeouts_present(self):
        report = _report_above_baseline(7)
        report["timeout_count"] = 1
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["zero_timeouts"])

    def test_fails_when_exceeds_600s_budget(self):
        report = _report_above_baseline(7)
        report["total_elapsed_seconds"] = 601.0
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["within_600s_budget"])

    def test_fails_when_call_cap_exceeded(self):
        report = _report_above_baseline(7)
        report["within_call_cap"] = False
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["within_call_cap"])

    def test_fails_when_connectivity_pollution_present(self):
        report = _report_with_connectivity()
        report["accuracy"] = 8 / 23.0  # above baseline
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["no_connectivity_pollution"])

    def test_failure_summary_is_detailed_on_multiple_failures(self):
        report = _report(
            accuracy=3 / 23.0,
            timeout_count=1,
            total_elapsed_seconds=601.0,
        )
        result = gate_check(report)
        self.assertFalse(result["passed"])
        self.assertGreaterEqual(len(result["failure_summary"]), 3)

    def test_gate_check_uses_custom_baseline(self):
        """With baseline=3, a 4/23 report should pass the accuracy gate."""
        report = _report(accuracy=4 / 23.0)
        result = gate_check(report, baseline_correct=3)
        self.assertTrue(result["checks"]["accuracy_above_baseline"])


# ---------------------------------------------------------------------------
# rank_tiers
# ---------------------------------------------------------------------------

class RankTiersTest(unittest.TestCase):
    def test_rank_tiers_sorts_by_accuracy_desc(self):
        reports = {
            2: _report(accuracy=0.3),
            4: _report(accuracy=0.1),
            6: _report(accuracy=0.2),
        }
        ranked = rank_tiers(reports)
        self.assertEqual([2, 6, 4], ranked)

    def test_rank_tiers_break_ties_by_calls_asc(self):
        reports = {
            2: _report(accuracy=0.2, average_model_calls=3.0),
            4: _report(accuracy=0.2, average_model_calls=1.0),
            6: _report(accuracy=0.2, average_model_calls=2.0),
        }
        ranked = rank_tiers(reports)
        self.assertEqual([4, 6, 2], ranked)

    def test_rank_tiers_break_ties_by_latency_asc(self):
        reports = {
            2: _report(accuracy=0.2, average_model_calls=1.0,
                        average_latency_seconds=5.0),
            4: _report(accuracy=0.2, average_model_calls=1.0,
                        average_latency_seconds=3.0),
        }
        ranked = rank_tiers(reports)
        self.assertEqual([4, 2], ranked)

    def test_rank_tiers_excludes_polluted_by_default(self):
        reports = {
            2: _report(accuracy=0.3),
            4: _report_with_connectivity(),  # polluted
            6: _report(accuracy=0.2),
        }
        ranked = rank_tiers(reports)
        self.assertNotIn(4, ranked)
        self.assertEqual([2, 6], ranked)

# ---------------------------------------------------------------------------
# adopt_best_tier
# ---------------------------------------------------------------------------

class AdoptBestTierTest(unittest.TestCase):
    def test_zero_reruns_cannot_qualify(self):
        decision = adopt_best_tier({2: []})
        self.assertEqual([], decision["qualified_tiers"])
        self.assertIsNone(decision["adopted_tier"])

    def test_one_rerun_cannot_qualify(self):
        decision = adopt_best_tier({2: [_report_above_baseline(7)]})
        self.assertEqual([], decision["qualified_tiers"])
        self.assertIsNone(decision["adopted_tier"])

    def test_no_qualified_tiers_returns_null_adoption(self):
        reruns = {
            2: [
                _report(accuracy=3 / 23.0),   # 3/23 — not above baseline
                _report(accuracy=4 / 23.0),
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertEqual([], decision["qualified_tiers"])
        self.assertIsNone(decision["adopted_tier"])
        self.assertIn("gate_results", decision)

    def test_single_qualified_tier_is_adopted(self):
        reruns = {
            2: [
                _report_above_baseline(7),
                _report_above_baseline(8),
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertEqual([2], decision["qualified_tiers"])
        self.assertEqual(2, decision["adopted_tier"])
        self.assertEqual(
            {"policy_sample_times": 1, "max_model_calls": 2, "verifier_voting_times": 1},
            decision["adopted_config"],
        )

    def test_best_of_multiple_qualified_is_selected(self):
        reruns = {
            2: [
                _report_above_baseline(7),    # avg 7.5
                _report_above_baseline(8),
            ],
            6: [
                _report_above_baseline(9),    # avg 9.5 → winner
                _report_above_baseline(10),
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertEqual([2, 6], decision["qualified_tiers"])
        self.assertEqual(6, decision["adopted_tier"])

    def test_one_of_two_runs_fails_gate_disqualifies_tier(self):
        """If even one re-run fails the gate, the tier is not adopted."""
        reruns = {
            2: [
                _report_above_baseline(7),    # passes
                _report(accuracy=3 / 23.0),   # fails accuracy gate
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertEqual([], decision["qualified_tiers"])
        self.assertIsNone(decision["adopted_tier"])

    def test_connectivity_pollution_disqualifies_tier(self):
        reruns = {
            2: [
                _report_above_baseline(7),
                _report_with_connectivity(),  # polluted — gate fails
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertEqual([], decision["qualified_tiers"])
        self.assertIsNone(decision["adopted_tier"])

    def test_gate_results_are_recorded_per_tier_per_run(self):
        reruns = {
            2: [
                _report_above_baseline(7),
                _report(accuracy=3 / 23.0),
            ],
        }
        decision = adopt_best_tier(reruns)
        self.assertIn(2, decision["gate_results"])
        self.assertEqual(2, len(decision["gate_results"][2]))
        self.assertTrue(decision["gate_results"][2][0]["passed"])   # first run passed
        self.assertFalse(decision["gate_results"][2][1]["passed"])  # second run failed


if __name__ == "__main__":
    unittest.main()
