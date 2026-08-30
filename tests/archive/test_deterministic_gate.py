import unittest

from scripts.archive.evaluate_deterministic_gate import gate


class DeterministicGateTest(unittest.TestCase):
    def test_two_clean_rounds_pass(self):
        records = [{"idx": i, "verdict": "correct"} for i in range(10)]
        report = {"correct": 10, "incorrect": 0, "unknown": 0, "records": records}
        result = gate(report, report)
        self.assertTrue(result["passed"])

    def test_mismatch_or_error_fails(self):
        a = {"correct": 10, "incorrect": 0, "unknown": 0, "records": [{"idx": i, "verdict": "correct"} for i in range(10)]}
        b = {"correct": 10, "incorrect": 1, "unknown": 0, "records": [{"idx": i, "verdict": "correct"} for i in range(10)]}
        result = gate(a, b)
        self.assertFalse(result["passed"])
        self.assertIn("round2:incorrect_nonzero", result["failures"])


if __name__ == "__main__":
    unittest.main()
