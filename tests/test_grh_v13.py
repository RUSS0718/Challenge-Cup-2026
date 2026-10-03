"""Regression tests for the opt-in GRH v1.3 host pipeline."""

import unittest

from reasoning_agent.grh_v13 import recover_response


class GrhV13PipelineTests(unittest.TestCase):
    """Keep recovery bounded and independent from model calls."""

    def test_recovery_returns_candidate_without_model_call(self):
        result = recover_response("Find the integer value.", "FINAL_CANDIDATE: 42", {"outcome": "invalid", "candidate_count": 1})
        self.assertEqual(0, result["model_calls"])
        self.assertEqual("42", result["candidate"]["canonical_value"])

    def test_finalizer_cannot_change_value(self):
        result = recover_response("Find the integer value.", "FINAL_CANDIDATE: 42", {"outcome": "invalid", "candidate_count": 1, "final_response": ""}, finalizer_response="FINAL_CANDIDATE: 99")
        self.assertEqual("42", result["candidate"]["canonical_value"])

    def test_conflicting_candidate_is_fail_closed(self):
        result = recover_response(
            "Find the integer value.",
            "42",
            {"outcome": "invalid", "candidate_count": 1, "trace": [{"reason": "conflict"}]},
        )
        self.assertIsNone(result["candidate"])
        self.assertEqual("unknown", result["recovery"]["action"])


if __name__ == "__main__":
    unittest.main()
