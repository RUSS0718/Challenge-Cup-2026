import unittest

from reasoning_agent.math_harness import (
    ANSWER_SHAPE_FINITE_SET,
    ANSWER_SHAPE_FUNCTION_FAMILY,
    ANSWER_SHAPE_INTERVAL_OR_RANGE,
    ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
    ANSWER_SHAPE_PROOF_TEXT,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    ProblemContract,
    REASONING_RISK_DEEP,
    ROUTE_CONFIDENCE_HIGH,
    TypedParser,
)


def contract(shape):
    return ProblemContract(shape, REASONING_RISK_DEEP, ROUTE_CONFIDENCE_HIGH)


class TypedParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = TypedParser()

    def test_complete_shapes(self):
        cases = (
            ("Final answer: 42", ANSWER_SHAPE_SINGLE_NUMERIC),
            (r"Final answer: x^2+3x+1", ANSWER_SHAPE_PARAMETERIZED_EXPRESSION),
            (r"Final answer: \{1,2,3\}", ANSWER_SHAPE_FINITE_SET),
            ("Final answer: [0, 1]", ANSWER_SHAPE_INTERVAL_OR_RANGE),
            ("Final answer: f(x)=x+1; g(x)=x^2", ANSWER_SHAPE_FUNCTION_FAMILY),
            ("因此命题成立。证毕。", ANSWER_SHAPE_PROOF_TEXT),
        )
        for response, shape in cases:
            with self.subTest(shape=shape):
                parsed = self.parser.parse(response, contract(shape), finish_reason="stop")
                self.assertTrue(parsed.typed_complete, parsed.reason)
                self.assertEqual(shape, parsed.answer_shape)

    def test_truncation_is_not_typed_complete(self):
        parsed = self.parser.parse(
            "Final answer: 42",
            contract(ANSWER_SHAPE_SINGLE_NUMERIC),
            finish_reason="length",
        )
        self.assertFalse(parsed.typed_complete)
        self.assertEqual("typed_incomplete", parsed.status)

    def test_original_smoke_outputs_are_negative_fixtures(self):
        fixtures = (
            ("all 3 vertices of column $x$ must be visited before we make the transition $x \\to x+1$.", ANSWER_SHAPE_PROOF_TEXT),
            ("-4.", ANSWER_SHAPE_PARAMETERIZED_EXPRESSION),
            ("$(g_1, p_1, o_1)$ always forms a triangle.", ANSWER_SHAPE_FINITE_SET),
            ("A(p) A(1) + A(-p) - 2 p - 1.", ANSWER_SHAPE_FUNCTION_FAMILY),
            ("f is essentially determined by the parity of the length of a word in these involutions mapping a base point to the target, provi", ANSWER_SHAPE_PROOF_TEXT),
            ("inf_N D_N, then that's the maximum. Often the", ANSWER_SHAPE_INTERVAL_OR_RANGE),
            ("x.", ANSWER_SHAPE_PARAMETERIZED_EXPRESSION),
        )
        for response, shape in fixtures:
            with self.subTest(response=response):
                parsed = self.parser.parse(response, contract(shape), finish_reason="stop")
                self.assertFalse(parsed.typed_complete)

    def test_missing_and_conflicting_values_fail_closed(self):
        missing = self.parser.parse("No conclusion", contract(ANSWER_SHAPE_SINGLE_NUMERIC))
        conflict = self.parser.parse(
            "Final answer: 1\nFinal answer: 2",
            contract(ANSWER_SHAPE_SINGLE_NUMERIC),
        )
        self.assertEqual("typed_rejected", missing.status)
        self.assertFalse(conflict.typed_complete)
        self.assertEqual("typed_conflict", conflict.status)


if __name__ == "__main__":
    unittest.main()
