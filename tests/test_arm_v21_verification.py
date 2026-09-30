"""Acceptance tests for the deterministic ARM conflict-verification seam."""

import unittest

from reasoning_agent.arm_v21_verification import DeterministicVerifier, VerificationResult
from reasoning_agent.harness_contracts import Candidate


class ARMV21VerificationTest(unittest.TestCase):
    """Keep the verifier bounded and fail-open by default."""

    def test_default_verifier_is_not_applicable(self):
        result = DeterministicVerifier().verify(object(), object(), "problem")
        self.assertEqual("NOT_APPLICABLE", result.status)
        self.assertIsNone(result.candidate_id)

    def test_selected_status_requires_existing_candidate(self):
        with self.assertRaises(ValueError):
            VerificationResult("A")

    def test_explicit_numeric_rhs_selects_matching_candidate(self):
        a = Candidate("A", "3", "3", "integer", "a", "parsed")
        b = Candidate("B", "4", "4", "integer", "b", "parsed")
        result = DeterministicVerifier().verify(a, b, "x = 4")
        self.assertEqual("B", result.status)
        self.assertEqual("B", result.candidate_id)


if __name__ == "__main__":
    unittest.main()
