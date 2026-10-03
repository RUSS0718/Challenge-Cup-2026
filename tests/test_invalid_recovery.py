"""Regression tests for conservative invalid classification."""

import unittest

from reasoning_agent.answer_contract import AnswerType, Candidate
from reasoning_agent.invalid_recovery import FailureClass, RecoveryAction, SalvageTier, decide_recovery


class InvalidRecoveryTests(unittest.TestCase):
    """Ensure recovery never invents a candidate."""

    def test_no_candidate_is_unknown(self):
        decision = decide_recovery({"outcome": "invalid", "candidate_count": 0})
        self.assertEqual(FailureClass.R1, decision.failure_class)
        self.assertEqual(SalvageTier.S6, decision.salvage_tier)
        self.assertEqual(RecoveryAction.UNKNOWN, decision.action)

    def test_closed_candidate_can_be_serialized(self):
        candidate = Candidate("7", AnswerType.INTEGER, "boxed", canonical_value="7")
        decision = decide_recovery({"outcome": "invalid", "candidate_count": 1}, candidate)
        self.assertEqual(RecoveryAction.SERIALIZE, decision.action)

    def test_timeout_preserves_incumbent(self):
        candidate = Candidate("7", AnswerType.INTEGER, "checkpoint", canonical_value="7")
        decision = decide_recovery({"outcome": "invalid", "timeout": True, "candidate_count": 1}, candidate)
        self.assertEqual(RecoveryAction.SAFE_INCUMBENT, decision.action)


if __name__ == "__main__":
    unittest.main()
