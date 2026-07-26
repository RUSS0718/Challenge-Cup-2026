import unittest

from sympy_adapter import SympyAdapterConfig, SympyEvidenceAdapter


class SympyEvidenceAdapterTest(unittest.TestCase):
    def setUp(self):
        self.adapter = SympyEvidenceAdapter()

    def test_equivalent_expressions_return_evidence(self):
        result = self.adapter.check_equivalence("(x + 1) * (x - 1)", "x**2 - 1")
        self.assertEqual("SUCCESS", result["execution_status"])
        self.assertEqual("SUPPORTED", result["claim_status"])
        self.assertIsNone(result["result"])

    def test_different_expressions_are_refuted(self):
        result = self.adapter.check_equivalence("x + 1", "x + 2")
        self.assertEqual("REFUTED", result["claim_status"])

    def test_unsafe_syntax_is_rejected(self):
        result = self.adapter.check_equivalence("__import__('os')", "1")
        self.assertEqual("ERROR", result["execution_status"])
        self.assertEqual("UNKNOWN", result["claim_status"])

    def test_input_limit_does_not_affect_future_calls(self):
        limited = SympyEvidenceAdapter(SympyAdapterConfig(max_input_length=3))
        self.assertEqual("ERROR", limited.check_equivalence("1234", "1")["execution_status"])
        self.assertEqual("SUPPORTED", self.adapter.check_equivalence("1", "1")["claim_status"])

    def test_soft_timeout_is_reported_without_changing_the_answer(self):
        timed = SympyEvidenceAdapter(SympyAdapterConfig(soft_timeout_seconds=-1.0))
        result = timed.check_equivalence("1", "1")
        self.assertEqual("TIMEOUT", result["execution_status"])
        self.assertEqual("UNKNOWN", result["claim_status"])


if __name__ == "__main__":
    unittest.main()
