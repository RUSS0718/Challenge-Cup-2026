import unittest

from scripts.run_math_harness_endpoint_preflight import (
    EXTRACTABLE_GATE,
    classify_response,
)


class MathHarnessEndpointPreflightTest(unittest.TestCase):
    def test_ordinary_boxed_answer_is_extractable_without_marker(self):
        result = classify_response(
            "Compute the value.",
            "The calculation gives\\n\\[\\boxed{17}\\]",
            "stop",
            24,
        )
        self.assertTrue(result["unique_extractable_candidate"])
        self.assertIn(result["parser_status"], {"parsed", "truncated_with_candidate"})
        self.assertEqual(["endpoint_preflight"], result["candidate_stage_sources"])

    def test_truncated_unique_candidate_is_format_recoverable(self):
        result = classify_response(
            "Compute the value.",
            "After simplifying, the answer is 17",
            "length",
            4096,
        )
        self.assertTrue(result["unique_extractable_candidate"])
        self.assertEqual("truncated_with_candidate", result["parser_status"])
        self.assertTrue(result["truncated"])

    def test_missing_candidate_is_not_extractable(self):
        result = classify_response(
            "Compute the value.",
            "The derivation is incomplete and ends with x =",
            "length",
            4096,
        )
        self.assertFalse(result["unique_extractable_candidate"])
        self.assertEqual("truncated_without_candidate", result["parser_status"])

    def test_gate_is_frozen_as_eight_of_ten(self):
        self.assertEqual(8, EXTRACTABLE_GATE)


if __name__ == "__main__":
    unittest.main()
