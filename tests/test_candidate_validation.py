"""Tests for ARM v2 candidate-shape validation."""

import unittest

from reasoning_agent.candidate_validation import validate_candidate_shape
from reasoning_agent.harness_contracts import (
    ANSWER_CHOICE,
    ANSWER_EXACT_EXPRESSION,
    ANSWER_INTEGER,
    ANSWER_RATIONAL,
    Candidate,
)


def _candidate(value: str, answer_type: str) -> Candidate:
    """Build the smallest candidate fixture accepted by the validator."""
    return Candidate(
        candidate_id="test",
        value=value,
        normalized_value=value,
        answer_type=answer_type,
        source="test",
        extraction_status="parsed",
    )


class CandidateValidationTest(unittest.TestCase):
    """Keep structural checks strict for scalars and bounded for expressions."""

    def test_integer_accepts_only_a_bare_integer(self):
        self.assertEqual((True, "valid"), validate_candidate_shape(_candidate("117", ANSWER_INTEGER), ANSWER_INTEGER))
        valid, reason = validate_candidate_shape(_candidate("有：", ANSWER_INTEGER), ANSWER_INTEGER)
        self.assertFalse(valid)
        self.assertEqual("integer_shape", reason)

    def test_rational_accepts_fraction_and_rejects_prose(self):
        self.assertEqual((True, "valid"), validate_candidate_shape(_candidate("4/3", ANSWER_RATIONAL), ANSWER_RATIONAL))
        self.assertFalse(validate_candidate_shape(_candidate("The area is:", ANSWER_RATIONAL), ANSWER_RATIONAL)[0])

    def test_choice_accepts_one_option(self):
        self.assertEqual((True, "valid"), validate_candidate_shape(_candidate("C", ANSWER_CHOICE), ANSWER_CHOICE))
        self.assertFalse(validate_candidate_shape(_candidate("maybe C", ANSWER_CHOICE), ANSWER_CHOICE)[0])

    def test_expression_filters_placeholders_without_evaluating_math(self):
        self.assertEqual(
            (True, "valid"),
            validate_candidate_shape(_candidate(r"sqrt(3)/2", ANSWER_EXACT_EXPRESSION), ANSWER_EXACT_EXPRESSION),
        )
        self.assertFalse(
            validate_candidate_shape(_candidate("the answer is", ANSWER_EXACT_EXPRESSION), ANSWER_EXACT_EXPRESSION)[0]
        )


if __name__ == "__main__":
    unittest.main()
