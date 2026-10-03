"""Regression tests for deterministic verification states."""

import unittest

from reasoning_agent.answer_contract import AnswerType, Candidate, TaskContract, Verification
from reasoning_agent.verification_gates import verify_candidate


class VerificationGateTests(unittest.TestCase):
    """Check PASS/FAIL/UNKNOWN semantics."""

    def test_integer_shape_passes_without_gold(self):
        candidate = Candidate("7", AnswerType.INTEGER, "marker", canonical_value="7")
        result = verify_candidate(candidate, TaskContract(answer_type=AnswerType.INTEGER))
        self.assertEqual(Verification.PASS, result.status)

    def test_expression_remains_unknown(self):
        candidate = Candidate("x+1", AnswerType.EXPRESSION, "marker", canonical_value="x+1")
        result = verify_candidate(candidate, TaskContract(answer_type=AnswerType.EXPRESSION))
        self.assertEqual(Verification.UNKNOWN, result.status)


if __name__ == "__main__":
    unittest.main()
