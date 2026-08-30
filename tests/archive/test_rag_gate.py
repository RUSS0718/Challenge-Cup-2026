import unittest

from scripts.archive.evaluate_rag_gate import gate


class RagGateTest(unittest.TestCase):
    def test_two_round_gain_passes(self):
        baseline = {"accuracy": 0.2, "regression_accuracy": 0.8, "empty_final_response_count": 0, "timeout_count": 0, "average_model_calls": 1.0}
        rag = {"accuracy": 0.3, "regression_accuracy": 0.79, "empty_final_response_count": 0, "timeout_count": 0, "average_model_calls": 1.0}
        self.assertTrue(gate([(baseline, rag), (baseline, rag)])['passed'])

    def test_insufficient_gain_or_cost_fails(self):
        baseline = {"accuracy": 0.2, "regression_accuracy": 0.8, "average_model_calls": 1.0}
        rag = {"accuracy": 0.21, "regression_accuracy": 0.8, "average_model_calls": 2.0}
        result = gate([(baseline, rag), (baseline, rag)])
        self.assertFalse(result['passed'])
        self.assertIn("round1:medium_gain_below_gate", result['failures'])
        self.assertIn("round1:average_calls_increased", result['failures'])

    def test_connectivity_or_failed_items_never_pass(self):
        baseline = {"accuracy": 0.2, "regression_accuracy": 0.8, "average_model_calls": 1.0}
        rag = {"accuracy": 0.4, "regression_accuracy": 0.8, "average_model_calls": 1.0, "failed_item_ids": [1]}
        result = gate([(baseline, rag), (baseline, rag)])
        self.assertFalse(result["passed"])
        self.assertIn("round1:failed_items_present", result["failures"])


if __name__ == "__main__":
    unittest.main()
