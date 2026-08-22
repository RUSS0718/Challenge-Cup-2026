import unittest

from scripts.evaluate_protocol_ab_gate import _parse_baseline_rounds, check_gate


def _report(variant, round_no, accuracy, invalid, incorrect=20, length=0.1, calls=1.0, max_calls=1, nonempty=1.0, correct=None):
    return {
        "input_file": "freeze.jsonl",
        "variant": variant,
        "round": round_no,
        "accuracy": accuracy,
        "correct": correct,
        "invalid": invalid,
        "incorrect": incorrect,
        "main_length_rate": length,
        "average_model_calls": calls,
        "max_model_calls": max_calls,
        "final_response_nonempty_rate": nonempty,
    }


class ProtocolAbGateTest(unittest.TestCase):
    def test_new_correctness_variant_requires_mean_gain_of_two(self):
        reports = [
            _report("baseline86", 1, 0.70, 10, incorrect=0, correct=70),
            _report("baseline86", 2, 0.72, 9, incorrect=0, correct=72),
            _report("temperature04", 1, 0.71, 10, incorrect=0, correct=71),
            _report("temperature04", 2, 0.73, 9, incorrect=0, correct=73),
        ]
        result = check_gate(reports)
        self.assertFalse(result["passed"])
        self.assertIn("freeze.jsonl:temperature04:mean_correct_gain_lt_2", result["failures"])

    def test_candidate_passes_both_rounds_when_all_gates_hold(self):
        reports = [
            _report("baseline86", 1, 0.70, 10, incorrect=20, length=0.2), _report("baseline86", 2, 0.72, 10, incorrect=20, length=0.2),
            _report("A+B+6144", 1, 0.72, 8, incorrect=20, length=0.1), _report("A+B+6144", 2, 0.72, 9, incorrect=20, length=0.2),
        ]
        result = check_gate(reports)
        self.assertTrue(result["passed"])
        self.assertEqual([], result["failures"])

    def test_gate_rejects_accuracy_invalid_and_budget_regressions(self):
        reports = [
            _report("baseline86", 1, 0.70, 10, incorrect=20), _report("baseline86", 2, 0.72, 10, incorrect=20),
            _report("A", 1, 0.69, 11, incorrect=21, length=0.3, calls=1.6, max_calls=3, nonempty=0.9),
            _report("A", 2, 0.72, 10, incorrect=20),
        ]
        result = check_gate(reports)
        self.assertFalse(result["passed"])
        self.assertIn("freeze.jsonl:A:round1:accuracy_not_below_baseline", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:invalid_not_above_baseline", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:incorrect_not_above_baseline", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:main_length_not_above_baseline", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:average_calls_le_1.5", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:max_calls_le_2", result["failures"])
        self.assertIn("freeze.jsonl:A:round1:nonempty_100pct", result["failures"])

    def test_adaptive_vote_variant_requires_mean_gain_of_two(self):
        reports = [
            _report("baseline86", 1, 0.70, 10, incorrect=0, correct=70),
            _report("baseline86", 2, 0.72, 9, incorrect=0, correct=72),
            _report("adaptive_vote", 1, 0.71, 10, incorrect=0, correct=71),
            _report("adaptive_vote", 2, 0.73, 9, incorrect=0, correct=73),
        ]
        result = check_gate(reports)
        self.assertFalse(result["passed"])
        self.assertIn("freeze.jsonl:adaptive_vote:mean_correct_gain_lt_2", result["failures"])

    def test_call_caps_follow_declared_budget(self):
        baseline1 = _report("baseline86", 1, 0.70, 10, incorrect=0, correct=70)
        baseline2 = _report("baseline86", 2, 0.72, 10, incorrect=0, correct=72)
        vote1 = _report("adaptive_vote", 1, 0.72, 9, incorrect=0, correct=71, calls=1.8, max_calls=3)
        vote1["budget_config"] = {"max_model_calls": 3}
        vote2 = _report("adaptive_vote", 2, 0.73, 9, incorrect=0, correct=73, calls=2.4, max_calls=3)
        vote2["budget_config"] = {"max_model_calls": 3}
        result = check_gate([baseline1, baseline2, vote1, vote2])
        self.assertFalse(any("calls_le" in failure for failure in result["failures"]))

    def test_runaway_beyond_declared_budget_is_rejected(self):
        baseline1 = _report("baseline86", 1, 0.70, 10, incorrect=0, correct=70)
        baseline2 = _report("baseline86", 2, 0.72, 10, incorrect=0, correct=72)
        vote1 = _report("adaptive_vote", 1, 0.71, 9, incorrect=0, correct=71, calls=2.6, max_calls=4)
        vote1["budget_config"] = {"max_model_calls": 3}
        vote2 = _report("adaptive_vote", 2, 0.73, 9, incorrect=0, correct=73, calls=2.4, max_calls=3)
        vote2["budget_config"] = {"max_model_calls": 3}
        result = check_gate([baseline1, baseline2, vote1, vote2])
        self.assertIn("freeze.jsonl:adaptive_vote:round1:average_calls_le_2.5", result["failures"])
        self.assertIn("freeze.jsonl:adaptive_vote:round1:max_calls_le_3", result["failures"])

    def test_custom_baseline_round_pairing_compares_against_given_rounds(self):
        reports = [
            _report("baseline86", 3, 0.70, 10, incorrect=0, correct=70),
            _report("baseline86", 4, 0.72, 10, incorrect=0, correct=72),
            _report("temperature04", 1, 0.69, 10, incorrect=0, correct=69),
            _report("temperature04", 2, 0.71, 11, incorrect=0, correct=71),
        ]
        result = check_gate(reports, baseline_pairing={1: 3, 2: 4})
        self.assertFalse(result["passed"])
        self.assertIn("freeze.jsonl:temperature04:round1:accuracy_not_below_baseline", result["failures"])
        self.assertIn("freeze.jsonl:temperature04:mean_correct_gain_lt_2", result["failures"])
        self.assertFalse(any("missing_pair" in failure for failure in result["failures"]))

    def test_custom_pairing_passes_when_candidate_beats_paired_baseline(self):
        reports = [
            _report("baseline86", 5, 0.70, 10, incorrect=20, length=0.2),
            _report("baseline86", 6, 0.72, 10, incorrect=20, length=0.2),
            _report("A+B+6144", 1, 0.71, 9, incorrect=20, length=0.1),
            _report("A+B+6144", 2, 0.73, 10, incorrect=20, length=0.2),
        ]
        result = check_gate(reports, baseline_pairing={1: 5, 2: 6})
        self.assertTrue(result["passed"])

    def test_parse_baseline_rounds_maps_variant_rounds_in_order(self):
        self.assertEqual({1: 3, 2: 4}, _parse_baseline_rounds("3,4"))
        self.assertIsNone(_parse_baseline_rounds(None))
        with self.assertRaises(SystemExit):
            _parse_baseline_rounds("3")
        with self.assertRaises(SystemExit):
            _parse_baseline_rounds("x,y")


if __name__ == "__main__":
    unittest.main()

