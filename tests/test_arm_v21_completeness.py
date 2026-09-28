"""Acceptance tests for ARM v2.1 answer-completeness gating."""

import unittest

from reasoning_agent.answer_completeness import assess_answer_completeness
from reasoning_agent.harness_contracts import (
    ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    Candidate,
    HostParser,
    ParsedResponse,
)


def _candidate(value: str) -> Candidate:
    """Build a parsed candidate for completeness checks."""
    return Candidate("test", value, value, "exact_expression", "test", "parsed")


class ARMV21CompletenessTest(unittest.TestCase):
    """Reject fragments while accepting complete parameterized answers."""

    def test_scalar_fragments_are_incomplete(self):
        for value in ("x", "x_s", "f", "T"):
            with self.subTest(value=value):
                complete, reason = assess_answer_completeness(
                    _candidate(value),
                    answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
                    parsed=ParsedResponse([], "parsed", "scalar", False, "candidate_extracted"),
                )
                self.assertFalse(complete)
                self.assertEqual("bare_symbol_fragment", reason)

    def test_parameterized_expression_is_complete(self):
        complete, reason = assess_answer_completeness(
            _candidate(r"x_s = -2*floor(m^2/4)"),
            answer_shape=ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
            parsed=ParsedResponse([], "parsed", "scalar", False, "candidate_extracted"),
        )
        self.assertTrue(complete)
        self.assertEqual("answer_complete", reason)

    def test_truncated_candidate_is_never_complete(self):
        complete, reason = assess_answer_completeness(
            _candidate("42"),
            answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
            parsed=ParsedResponse([], "truncated_with_candidate", "scalar", True, "truncated"),
        )
        self.assertFalse(complete)
        self.assertEqual("truncated", reason)

    def test_host_parser_marks_scalar_symbol_as_incomplete(self):
        parsed = HostParser().parse(
            "Final answer: x_s",
            problem="求一个数",
            source="test",
            finish_reason="stop",
        )
        self.assertEqual(1, len(parsed.candidates))
        self.assertFalse(parsed.candidates[0].answer_complete)
        self.assertEqual("bare_symbol_fragment", parsed.candidates[0].answer_complete_reason)

    def test_arm_candidate_requires_explicit_final_answer_marker(self):
        candidate = _candidate("42")
        candidate.source = "arm_primary"
        candidate.response = "Therefore, the result is 42."
        complete, reason = assess_answer_completeness(
            candidate,
            answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
            parsed=ParsedResponse([], "parsed", "scalar", False, "candidate_extracted"),
        )
        self.assertFalse(complete)
        self.assertEqual("missing_final_answer_marker", reason)


if __name__ == "__main__":
    unittest.main()
