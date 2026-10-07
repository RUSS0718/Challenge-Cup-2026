"""Acceptance tests for v2.1 paired transition attribution."""

import unittest

from reasoning_agent.arm_v21_diagnostics import paired_attribution


class ARMV21AttributionTest(unittest.TestCase):
    """Retain all nine transitions and the selected mechanism source."""

    def test_item_level_attribution_has_transition_and_source(self):
        rows = [
            {"variant": "baseline", "idx": 1, "verdict": "invalid"},
            {"variant": "candidate", "idx": 1, "verdict": "correct", "final_source": "safe_candidate"},
        ]
        result = paired_attribution(rows, "baseline", "candidate")
        self.assertEqual(1, result["transition_matrix"]["invalid → correct"])
        self.assertEqual(
            {
                "idx": 1,
                "baseline_result": "invalid",
                "candidate_result": "correct",
                "transition": "invalid → correct",
                "candidate_final_source": "safe_candidate",
            },
            result["item_attribution"][0],
        )

    def test_matrix_contains_all_nine_cells(self):
        result = paired_attribution([], "baseline", "candidate")
        self.assertEqual(9, len(result["transition_matrix"]))
        self.assertTrue(all(value == 0 for value in result["transition_matrix"].values()))


if __name__ == "__main__":
    unittest.main()
