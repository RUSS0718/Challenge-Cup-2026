import unittest

from scripts.evaluate_protocol_ab_gate import check_gate


def _report(variant, round_no, accuracy, invalid, incorrect=20, length=0.1, calls=1.0, max_calls=1, nonempty=1.0):
    return {
        "input_file": "freeze.jsonl",
        "variant": variant,
        "round": round_no,
        "accuracy": accuracy,
        "invalid": invalid,
        "incorrect": incorrect,
        "main_length_rate": length,
        "average_model_calls": calls,
        "max_model_calls": max_calls,
        "final_response_nonempty_rate": nonempty,
    }


class ProtocolAbGateTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
