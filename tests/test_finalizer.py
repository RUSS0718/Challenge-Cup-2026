"""Regression tests for the bounded OFF finalizer contract."""

import unittest

from reasoning_agent.answer_contract import AnswerType, Candidate, TaskContract
from reasoning_agent.finalizer import FinalizerInput, accept_finalizer_response, build_finalizer_prompt


class FinalizerTests(unittest.TestCase):
    """Ensure finalizer output cannot change the incumbent value."""

    def setUp(self):
        self.contract = TaskContract(answer_type=AnswerType.INTEGER)
        self.candidate = Candidate("7", AnswerType.INTEGER, "boxed", canonical_value="7")
        self.data = FinalizerInput(self.contract, self.candidate, "structurally complete")

    def test_same_value_is_accepted(self):
        self.assertIsNotNone(accept_finalizer_response("FINAL_CANDIDATE: 7", self.data))

    def test_new_value_is_rejected(self):
        self.assertIsNone(accept_finalizer_response("FINAL_CANDIDATE: 8", self.data))

    def test_prompt_forbids_resolving(self):
        prompt = build_finalizer_prompt(self.data)
        self.assertIn("Do not solve", prompt)
        self.assertIn("same canonical value", prompt)


if __name__ == "__main__":
    unittest.main()
