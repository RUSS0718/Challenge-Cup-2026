import unittest

from reasoning_agent.fesf_obligations import extract_bounded_obligations


class BoundedObligationExtractorTest(unittest.TestCase):
    def test_extracts_explicit_domain_and_completeness_signals(self):
        result = extract_bounded_obligations(
            "OPEN: 检查边界情况\n证明任意 x 的全部实根，并代回检验 1/x。\nx != 0",
            source="B",
        )
        kinds = [item.kind for item in result.obligations]
        self.assertIn("OPEN_ITEM", kinds)
        self.assertIn("DOMAIN_CHECK", kinds)
        self.assertIn("PROOF_COMPLETENESS", kinds)
        self.assertIn("UNIVERSAL_COVERAGE", kinds)
        self.assertIn("SUBSTITUTION_CHECK", kinds)
        domain = next(item for item in result.obligations if item.kind == "DOMAIN_CHECK")
        self.assertEqual("OPEN", domain.state)
        self.assertEqual("B", domain.source)

    def test_unknown_prose_is_not_rewritten_as_a_semantic_obligation(self):
        result = extract_bounded_obligations("这是一个没有数学触发词的普通句子。")
        self.assertEqual((), result.obligations)
        self.assertFalse(result.truncated)

    def test_result_is_bounded_and_ids_are_stable(self):
        text = "\n".join(
            [
                "OPEN: a",
                "OPEN: b",
                "证明任意 x，存在至少一个解，枚举全部解并代回。",
                "1/x",
            ]
        )
        result = extract_bounded_obligations(text, max_items=2)
        self.assertEqual(2, len(result.obligations))
        self.assertTrue(result.truncated)
        self.assertEqual(["O1", "O2"], [item.id for item in result.obligations])

    def test_overlong_input_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "problem_too_long"):
            extract_bounded_obligations("x" * 12_001)

    def test_frozen_obligation_contract_table(self):
        from tests.support.host_loop_foundations import evaluate_obligation_case
        from tests.support.host_loop_foundations_cases import INTAKE_CASES, OBLIGATION_CASES

        self.assertGreaterEqual(len(INTAKE_CASES) + len(OBLIGATION_CASES), 48)
        failures = [evaluate_obligation_case(case) for case in OBLIGATION_CASES]
        self.assertEqual([], [row for row in failures if not row.get("ok")])

    def test_natural_language_slash_is_not_a_denominator_obligation(self):
        for text in ("速度单位是 km/h 。", "选择 and/or 中的一种表述。"):
            with self.subTest(text=text):
                result = extract_bounded_obligations(text)
                self.assertEqual((), result.obligations)

    def test_symbolic_denominators_stay_open_without_claim_dsl(self):
        for text in (
            "已知 x != 0，化简 1/x。",
            "已知 x 非零，化简 1/x。",
            "已知 x*y != 0，化简 1/y。",
            "已知 x != 0.5，化简 1/x。",
        ):
            with self.subTest(text=text):
                domain = [item for item in extract_bounded_obligations(text).obligations if item.kind == "DOMAIN_CHECK"]
                self.assertTrue(domain)
                self.assertEqual(["OPEN"], [item.state for item in domain], text)
        self.assertEqual((), extract_bounded_obligations("化简 1/(x*y)。").obligations)


if __name__ == "__main__":
    unittest.main()
