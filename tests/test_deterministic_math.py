import unittest

from deterministic_math import solve_deterministic


class DeterministicMathTest(unittest.TestCase):
    def assert_answer(self, problem: str, answer: str) -> None:
        result = solve_deterministic(problem)
        self.assertEqual("supported", result["status"])
        self.assertEqual(answer, result["answer"])
        self.assertTrue(result["deterministic"])

    def test_factorial(self):
        self.assert_answer("计算 6!", "720")

    def test_large_factorial_is_refused_before_computation(self):
        result = solve_deterministic("9999!")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("factorial_limit_exceeded", result["reason"])

    def test_combination(self):
        self.assert_answer("C(10, 3)", "120")

    def test_large_combination_is_refused_before_computation(self):
        result = solve_deterministic("C(9999, 2)")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("combination_limit_exceeded", result["reason"])

    def test_arithmetic_sum(self):
        self.assert_answer("等差数列前10项和，首项为3，公差为4。", "210")

    def test_geometric_sum_fraction(self):
        self.assert_answer("求等比数列前4项和，首项 1，公比 1/2。", "15/8")

    def test_geometric_zero_denominator_is_refused(self):
        result = solve_deterministic("求等比数列前4项和，首项 1，公比 1/0。")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("invalid_ratio", result["reason"])

    def test_geometric_huge_power_is_refused_before_exponentiation(self):
        result = solve_deterministic("求等比数列前9999项和，首项 1，公比 999999999999/1。")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("fraction_limit_exceeded", result["reason"])

    def test_geometric_output_digit_limit_is_refused(self):
        result = solve_deterministic("求等比数列前10000项和，首项 1，公比 1/3。")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("fraction_limit_exceeded", result["reason"])

    def test_large_sum_term_count_is_refused_before_iteration(self):
        result = solve_deterministic("等差数列前999999项和，首项为1，公差为1。")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("sum_limit_exceeded", result["reason"])

    def test_linear_system(self):
        self.assert_answer("解方程组：2x+3y=7，x-y=1。", "x=2, y=1")
        result = solve_deterministic("解方程组：2x+3y=7，x-y=1。")
        self.assertIn("substitution verified", result["verification"])

    def test_singular_system_is_refused(self):
        result = solve_deterministic("解方程组：x+y=2，2x+2y=4。")
        self.assertEqual("unsupported", result["status"])
        self.assertEqual("singular_or_nonunique_system", result["reason"])

    def test_ambiguous_prose_is_refused(self):
        result = solve_deterministic("请解释组合数 C(10,3) 的含义。")
        self.assertEqual("unsupported", result["status"])

    def test_unsafe_or_symbolic_input_is_refused(self):
        result = solve_deterministic("计算 n!")
        self.assertEqual("unsupported", result["status"])

    def test_extended_closed_forms(self):
        cases = {
            "计算 C(12,3)+C(12,9)。": "440",
            "求方程 x^2−5x+6=0 的全部实根。": "{2,3}",
            "计算 gcd(84,30)。": "6",
            "计算 2^10 mod 7。": "2",
            "计算矩阵 [[3,1],[2,4]] 的行列式。": "10",
            "独立抛掷公平硬币3次，恰有2次正面的概率是多少？": "3/8",
            "填空：1+2+⋯+20=____。": "210",
            "填空：若 f(x)=sin x，则 f'(x)=____。": "cos x",
            "填空：5!=____。": "120",
            "填空：C(8,2)=____。": "28",
            "填空：2×2单位矩阵的迹为____。": "2",
        }
        for problem, answer in cases.items():
            with self.subTest(problem=problem):
                self.assert_answer(problem, answer)

    def test_extended_solver_refuses_ambiguous_variants(self):
        for problem in ("求 gcd(a,30)。", "计算 2^10 mod 0。", "方程 x^2−5x+7=0 的全部实根。"):
            with self.subTest(problem=problem):
                self.assertEqual("unsupported", solve_deterministic(problem)["status"])


if __name__ == "__main__":
    unittest.main()
