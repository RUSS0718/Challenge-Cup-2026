import json
import unittest

from reasoning_agent.host_intake import (
    build_host_intake,
    estimate_complexity,
    normalize_problem,
    sanitize_metadata,
)


class HostIntakeTest(unittest.TestCase):
    def test_normalization_preserves_math_and_line_structure(self):
        self.assertEqual("x = 1\n y = 2", normalize_problem("\u200b x = 1\r\n y = 2\r"))

    def test_empty_and_overlong_problems_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "problem_empty"):
            normalize_problem(" \n")
        with self.assertRaisesRegex(ValueError, "problem_too_long"):
            normalize_problem("x" * 20, max_chars=10)

    def test_metadata_is_allowlisted_and_scalar_only(self):
        clean, reasons = sanitize_metadata(
            {
                "idx": 7,
                "language": "zh",
                "answer": "42",
                "unknown": "value",
                "source": ["not", "scalar"],
                "difficulty": float("inf"),
            }
        )
        self.assertEqual({"idx": 7, "language": "zh"}, clean)
        self.assertIn("sensitive_key", reasons)
        self.assertIn("not_allowlisted", reasons)
        self.assertIn("non_scalar", reasons)
        self.assertIn("non_finite", reasons)

    def test_intake_hash_and_complexity_are_bounded_and_serializable(self):
        problem = "证明任意 x != 0 时\n1/x = 1/x。\n1. 检查定义域\n2. 给出全部结论"
        intake = build_host_intake(
            problem,
            {"idx": 1, "gold": "must not be retained", "domain": "algebra"},
            answer_type="proof",
        )
        self.assertEqual(16, len(intake.problem_hash))
        self.assertEqual("proof", intake.answer_type)
        self.assertEqual("structured", intake.complexity.profile)
        self.assertTrue(intake.complexity.has_proof_language)
        self.assertTrue(intake.complexity.has_universal_language)
        self.assertTrue(intake.complexity.has_multiple_parts)
        encoded = json.dumps(intake.as_dict(), ensure_ascii=False)
        self.assertNotIn("must not be retained", encoded)

    def test_complexity_rejects_overlong_input_without_clipping(self):
        with self.assertRaisesRegex(ValueError, "problem_too_long"):
            estimate_complexity("a" * 12_001)

    def test_frozen_intake_contract_table(self):
        from tests.support.host_loop_foundations import evaluate_intake_case
        from tests.support.host_loop_foundations_cases import INTAKE_CASES

        self.assertGreaterEqual(len(INTAKE_CASES), 30)
        failures = [evaluate_intake_case(case) for case in INTAKE_CASES]
        self.assertEqual([], [row for row in failures if not row.get("ok")])


if __name__ == "__main__":
    unittest.main()
