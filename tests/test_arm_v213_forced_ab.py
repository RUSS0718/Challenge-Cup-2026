"""Tests for response-free v2.1.3 forced A/B aggregation."""

import unittest

from scripts.run_arm_v213_forced_ab import summarize_forced_ab


class ForcedABSummaryTest(unittest.TestCase):
    """Keep A/B, oracle, rescue, and damage counts explicit."""

    def test_oracle_and_transition_metrics(self):
        rows = [
            {
                "idx": 1,
                "arm_v2_summary": {
                    "candidate_a": {"value": "1", "structural_validity": "valid", "answer_complete": True},
                    "candidate_b": {"value": "2", "structural_validity": "valid", "answer_complete": True},
                    "a_b_relation": "CONFLICT",
                },
            },
            {
                "idx": 2,
                "arm_v2_summary": {
                    "candidate_a": {"value": "3", "structural_validity": "valid", "answer_complete": True},
                    "candidate_b": {"value": "3", "structural_validity": "valid", "answer_complete": True},
                    "a_b_relation": "EQUIVALENT",
                },
            },
            {
                "idx": 3,
                "arm_v2_summary": {
                    "candidate_a": {"value": "4", "structural_validity": "valid", "answer_complete": True},
                    "candidate_b": {"value": "5", "structural_validity": "valid", "answer_complete": True},
                    "a_b_relation": "CONFLICT",
                },
            },
        ]
        metrics = summarize_forced_ab(rows, {1: "2", 2: "3", 3: "6"})
        self.assertEqual(1, metrics["A_correct"])
        self.assertEqual(2, metrics["B_correct"])
        self.assertEqual(2, metrics["oracle_correct"])
        self.assertEqual(1, metrics["A_wrong_B_correct"])
        self.assertEqual(0, metrics["A_correct_B_wrong"])
        self.assertEqual(1, metrics["both_correct_same"])


if __name__ == "__main__":
    unittest.main()
