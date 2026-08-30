import unittest

from scripts.archive.evaluate_deterministic_integration_gate import gate


class DeterministicIntegrationGateTest(unittest.TestCase):
    def test_stable_gain_and_lower_cost_pass(self):
        records_b = [{"idx": i, "verdict": "unknown"} for i in range(10)]
        records_d = [{"idx": i, "verdict": "correct"} for i in range(10)]
        b = {"accuracy": 0.48, "average_model_calls": 1.0, "failed_item_ids": [], "timeout_count": 0, "empty_final_response_count": 0, "records": records_b}
        d = {"accuracy": 0.50, "average_model_calls": 0.8, "failed_item_ids": [], "timeout_count": 0, "empty_final_response_count": 0, "records": records_d}
        self.assertTrue(gate(b, d, b, d, 0)["passed"])

    def test_regression_or_runtime_failure_blocks(self):
        b = {"accuracy": 0.5, "average_model_calls": 1.0, "records": []}
        d = {"accuracy": 0.5, "average_model_calls": 1.0, "failed_item_ids": [2], "timeout_count": 0, "empty_final_response_count": 0, "records": []}
        result = gate(b, d, b, d, 1)
        self.assertFalse(result["passed"])
        self.assertIn("round1:runtime_failure", result["failures"])
        self.assertIn("regression_112_supported_items_nonzero", result["failures"])


if __name__ == "__main__":
    unittest.main()
