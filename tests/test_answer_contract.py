"""Regression tests for the gold-free answer contract and parser."""

import unittest

from reasoning_agent.answer_contract import AnswerType, TaskContract, infer_task_contract
from reasoning_agent.candidate_canonicalizer import canonicalize, parse_response


class AnswerContractTests(unittest.TestCase):
    """Cover accepted surfaces and fail-closed conflicts."""

    def test_typed_marker_is_extracted(self):
        contract = TaskContract(answer_type=AnswerType.INTEGER)
        parsed = parse_response("work\nFINAL_CANDIDATE: \\boxed{42}", contract)
        self.assertTrue(parsed.complete)
        self.assertEqual("42", parsed.candidates[0].canonical_value)

    def test_conflicting_markers_are_rejected(self):
        contract = TaskContract(answer_type=AnswerType.INTEGER)
        parsed = parse_response("FINAL ANSWER: 1\nFINAL_CANDIDATE: 2", contract)
        self.assertFalse(parsed.complete)
        self.assertEqual("conflicting_candidates", parsed.rejection_reason)

    def test_set_normalization_does_not_reorder_tuple(self):
        self.assertEqual("{1,2}", canonicalize("{2, 1}", TaskContract(answer_type=AnswerType.SET)))
        self.assertEqual("(2,1)", canonicalize("(2, 1)", TaskContract(answer_type=AnswerType.TUPLE)))

    def test_contract_inference_is_gold_free(self):
        self.assertEqual(AnswerType.PROOF, infer_task_contract("Prove that x > 0").answer_type)


if __name__ == "__main__":
    unittest.main()
