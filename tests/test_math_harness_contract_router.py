import json
import unittest

from reasoning_agent.math_harness import (
    ANSWER_SHAPE_FINITE_SET,
    ANSWER_SHAPE_FUNCTION_FAMILY,
    ANSWER_SHAPE_INTERVAL_OR_RANGE,
    ANSWER_SHAPE_PARAMETERIZED_EXPRESSION,
    ANSWER_SHAPE_PROOF_TEXT,
    ANSWER_SHAPE_SINGLE_NUMERIC,
    REASONING_RISK_DEEP,
    REASONING_RISK_DIRECT,
    ROUTE_CONFIDENCE_HIGH,
    ROUTE_CONFIDENCE_LOW,
    HostRouter,
    ProblemContract,
)


class ProblemContractTest(unittest.TestCase):
    def test_contract_has_only_the_three_routing_fields(self):
        contract = ProblemContract(
            ANSWER_SHAPE_SINGLE_NUMERIC,
            REASONING_RISK_DIRECT,
            ROUTE_CONFIDENCE_HIGH,
        )
        self.assertEqual(
            {
                "answer_shape": ANSWER_SHAPE_SINGLE_NUMERIC,
                "reasoning_risk": REASONING_RISK_DIRECT,
                "route_confidence": ROUTE_CONFIDENCE_HIGH,
            },
            contract.as_dict(),
        )
        json.dumps(contract.as_dict(), ensure_ascii=False)


class DualAxisRouterTest(unittest.TestCase):
    def setUp(self):
        self.router = HostRouter(deep_enabled=True, hybrid_enabled=True)

    def test_direct_single_numeric_uses_direct_lane(self):
        decision = self.router.route("计算 3+4")
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)
        self.assertEqual(REASONING_RISK_DIRECT, decision.contract.reasoning_risk)
        self.assertEqual("direct", decision.lane)
        self.assertEqual("harness", decision.target)

    def test_deep_single_numeric_is_not_direct(self):
        decision = self.router.route(
            "有 60 个带坐标的元素，要求满足边界条件的排列数，求所有可能的排列数量。"
        )
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)
        self.assertEqual(REASONING_RISK_DEEP, decision.contract.reasoning_risk)
        self.assertEqual("deep", decision.lane)
        self.assertEqual("harness", decision.target)

    def test_typed_answer_shapes_are_distinguished(self):
        cases = (
            ("求 T=T(m) 的表达式", ANSWER_SHAPE_PARAMETERIZED_EXPRESSION),
            ("求方程的所有可能解组成的集合", ANSWER_SHAPE_FINITE_SET),
            ("求 x 的取值范围和区间", ANSWER_SHAPE_INTERVAL_OR_RANGE),
            ("找出所有满足条件的函数 f", ANSWER_SHAPE_FUNCTION_FAMILY),
            ("证明该不等式对所有实数成立", ANSWER_SHAPE_PROOF_TEXT),
        )
        for problem, expected_shape in cases:
            with self.subTest(problem=problem):
                self.assertEqual(expected_shape, self.router.route(problem).contract.answer_shape)

    def test_proof_and_low_confidence_mixed_fall_back_to_legacy(self):
        proof = self.router.route("证明这个命题")
        self.assertEqual("legacy_fsdf", proof.target)
        mixed = self.router.route("证明所有函数的取值范围并求所有解")
        self.assertEqual(ROUTE_CONFIDENCE_LOW, mixed.contract.route_confidence)
        self.assertEqual("legacy_fsdf", mixed.target)

    def test_metadata_cannot_change_contract(self):
        plain = self.router.route("计算 3+4", {})
        poisoned = self.router.route("计算 3+4", {"answer": "999", "idx": 7})
        self.assertEqual(plain.contract.as_dict(), poisoned.contract.as_dict())
        self.assertEqual(plain.lane, poisoned.lane)

    def test_deep_contract_falls_back_when_deep_lane_is_disabled(self):
        decision = HostRouter(hybrid_enabled=True).route(
            "求所有满足条件的函数 f"
        )
        self.assertEqual("legacy_fsdf", decision.target)

    def test_range_signal_uses_word_boundaries(self):
        decision = self.router.route(
            "Nine balls are arranged on a circle; compute the minimum sum."
        )
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)

    def test_probability_question_is_a_numeric_answer(self):
        decision = self.router.route("Find the probability of the arrangement.")
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)

    def test_numeric_remainder_bound_is_not_an_interval_answer(self):
        decision = self.router.route(
            "Find the remainder modulo 2017^2 (provide the value in the range [0, 2017^2))."
        )
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)

    def test_short_choice_is_a_direct_single_answer(self):
        decision = self.router.route("Choose the correct option: A, B, C, or D.")
        self.assertEqual(ANSWER_SHAPE_SINGLE_NUMERIC, decision.contract.answer_shape)
        self.assertEqual("direct", decision.lane)
        self.assertEqual("choice", decision.answer_type)


if __name__ == "__main__":
    unittest.main()
