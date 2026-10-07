"""Regression tests for the isolated ARM v2.1.4 completeness extension."""

import unittest

from reasoning_agent.answer_completeness_v214 import assess_answer_completeness
from reasoning_agent.harness_contracts import ANSWER_SHAPE_SINGLE_NUMERIC, Candidate, ParsedResponse


def _candidate(value: str, response: str) -> Candidate:
    """Build an ARM candidate carrying the response used for extraction checks."""
    candidate = Candidate("test", value, value, "exact_expression", "arm_primary", "parsed")
    candidate.response = response
    return candidate


class ARMV214CompletenessTest(unittest.TestCase):
    """Keep v2.1.4 boxed and truncated-tail behavior isolated from legacy ARM."""

    def test_nested_boxed_answer_is_complete(self):
        candidate = _candidate(r"\frac{1}{2}", r"唯一答案为 \boxed{\frac{1}{2}}")
        complete, reason = assess_answer_completeness(
            candidate,
            answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
            parsed=ParsedResponse([], "parsed", "scalar", False, "candidate_extracted"),
        )
        self.assertTrue(complete)
        self.assertEqual("answer_complete", reason)

    def test_marked_truncated_tail_remains_complete(self):
        candidate = _candidate("7", "推理未完\nFinal answer: 7")
        complete, reason = assess_answer_completeness(
            candidate,
            answer_shape=ANSWER_SHAPE_SINGLE_NUMERIC,
            parsed=ParsedResponse([], "truncated_with_candidate", "scalar", True, "truncated"),
        )
        self.assertTrue(complete)
        self.assertEqual("answer_complete_truncated_tail", reason)


if __name__ == "__main__":
    unittest.main()
