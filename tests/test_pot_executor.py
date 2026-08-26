"""Local-only tests for the PoT restricted executor (spec 2026-08-22 §3/§6).

No API calls: every case feeds a fixed program string to ``execute_program``.
"""
import unittest

from pot_executor import PotExecutorConfig, execute_program


def assert_success(testcase, source, expected_answer=None):
    result = execute_program(source)
    testcase.assertEqual("SUCCESS", result["status"], msg=f"{source!r} -> {result}")
    testcase.assertIsNone(result["reason"])
    if expected_answer is not None:
        testcase.assertEqual(expected_answer, result["answer"])
    return result


def assert_unsupported(testcase, source, reason, config=None):
    result = execute_program(source, config)
    testcase.assertEqual(
        "UNSUPPORTED", result["status"], msg=f"{source!r} -> {result}"
    )
    testcase.assertEqual(reason, result["reason"])
    testcase.assertIsNone(result["answer"])
    return result


def assert_error(testcase, source, reason, config=None):
    result = execute_program(source, config)
    testcase.assertEqual("ERROR", result["status"], msg=f"{source!r} -> {result}")
    testcase.assertEqual(reason, result["reason"])
    testcase.assertIsNone(result["answer"])


class ResultContractTest(unittest.TestCase):
    def test_success_result_shape(self):
        result = assert_success(self, "print(40 + 2)", "42")
        self.assertEqual({"status", "reason", "answer"}, set(result))

    def test_rejected_programs_carry_no_answer(self):
        result = execute_program("while True:\n    pass")
        self.assertEqual("UNSUPPORTED", result["status"])
        self.assertIsNone(result["answer"])
        result = execute_program("print(1 / 0)")
        self.assertEqual("ERROR", result["status"])
        self.assertIsNone(result["answer"])

    def test_empty_or_invalid_source_is_unsupported(self):
        assert_unsupported(self, "", "empty_source")
        assert_unsupported(self, "   \n\t", "empty_source")
        assert_unsupported(self, None, "empty_source")
        assert_unsupported(self, "x === 1", "syntax_error")

    def test_config_limits_are_honored(self):
        tight = PotExecutorConfig(max_source_chars=8)
        assert_unsupported(self, "print(1 + 1)", "source_too_long", tight)

    def test_same_program_executes_identically(self):
        source = (
            "total = 0\n"
            "for i in range(1, 11):\n"
            "    total = total + i\n"
            "print(total)"
        )
        first, second = execute_program(source), execute_program(source)
        self.assertEqual(first, second)
        self.assertEqual(repr(first), repr(second))


class StatementAcceptMatrixTest(unittest.TestCase):
    """§3.1 positive rows: every accepted construct gets one program."""

    def test_assignment_and_print(self):
        assert_success(self, "value = 6 * 7\nprint(value)", "42")

    def test_for_range_loop(self):
        source = "total = 0\nfor i in range(1, 5):\n    total = total + i\nprint(total)"
        assert_success(self, source, "10")

    def test_all_binary_operators(self):
        cases = {
            "print(2 + 3)": "5",
            "print(7 - 4)": "3",
            "print(6 * 7)": "42",
            "print(10 / 4)": "5/2",
            "print(10 // 4)": "2",
            "print(10 % 3)": "1",
            "print(2 ** 10)": "1024",
        }
        for source, answer in cases.items():
            assert_success(self, source, answer)

    def test_unary_operators(self):
        assert_success(self, "print(-5 + 3)", "-2")
        assert_success(self, "print(+7)", "7")

    def test_comparisons_over_numeric_operands(self):
        cases = {
            "print(3 == 3)": "True",
            "print(3 != 4)": "True",
            "print(3 < 5)": "True",
            "print(3 <= 3)": "True",
            "print(5 > 3)": "True",
            "print(3 >= 3)": "True",
        }
        for source, answer in cases.items():
            assert_success(self, source, answer)

    def test_float_literals(self):
        assert_success(self, "print(1.5 * 2)", "3")

    def test_sympy_names_and_constants(self):
        assert_success(self, 'x = Symbol("x")\nprint(x * 1)', "x")
        assert_success(self, "print(Rational(3, 4))", "3/4")
        assert_success(self, "print(Integer(5) + 1)", "6")
        assert_success(self, "print(pi > 3)", "True")
        assert_success(self, "print(E > 2)", "True")
        assert_success(self, "print(I * I)", "-1")
        assert_success(self, "print(oo > 10**9)", "True")

    def test_whitelisted_builtin_functions(self):
        assert_success(self, "print(int(sqrt(9)))", "3")
        assert_success(self, "print(float(Rational(1, 4)))", "1/4")
        assert_success(self, "print(abs(-5))", "5")
        assert_success(self, "print(min(3, 1, 2))", "1")
        assert_success(self, "print(max(3, 1, 2))", "3")
        assert_success(self, "print(sum([1, 2, 3]))", "6")
        assert_success(self, "print(round(float(sqrt(17))))", "4")

    def test_combinatorics_functions(self):
        # thinking-off 探针实证缺口：factorial / comb(n,k) 用法（spec 2026-08-23）。
        assert_success(self, "print(factorial(5) // (factorial(2) * factorial(3)))", "10")
        assert_success(self, "print(binomial(10, 3))", "120")

    def test_multiple_prints_use_last_non_empty_line(self):
        assert_success(self, "print(1 + 1)\nprint(2 + 2)", "4")


class ExpressionAcceptMatrixTest(unittest.TestCase):
    """§3.2 whitelist: every allowed function is callable."""

    def test_expression_functions(self):
        cases = [
            ('x = Symbol("x")\nprint(simplify(x + 0))', "x"),
            ('x = Symbol("x")\nprint(expand((x + 1)**2) - (x**2 + 2*x + 1))', "0"),
            ('x = Symbol("x")\nprint(factor(x**2 - 1) - (x - 1)*(x + 1))', "0"),
            ('x = Symbol("x")\nprint(min(solve(x**2 - 1, x)))', "-1"),
            ("print(nsimplify(pi) == pi)", "True"),
            ("print(sqrt(2)*sqrt(2) == 2)", "True"),
            ("print(Abs(-5))", "5"),
            ("print(log(E))", "1"),
            ("print(exp(0))", "1"),
            ("print(sin(pi / 2))", "1"),
            ("print(cos(0))", "1"),
            ("print(tan(0))", "0"),
            ('x = Symbol("x")\nprint(diff(x**2, x))', "2*x"),
            ('x = Symbol("x")\nprint(integrate(x, (x, 0, 1)))', "1/2"),
            ('k = Symbol("k")\nprint(N(Sum(k, (k, 1, 2))))', "3"),
            ("print(N(pi, 3))", "157/50"),
        ]
        for source, answer in cases:
            assert_success(self, source, answer)


class ConstructRejectMatrixTest(unittest.TestCase):
    """§3.1 negative rows plus §3.3 expression bans: exact reasons."""

    def test_banned_statements(self):
        cases = {
            "if 1 > 0:\n    pass": "unsupported:if",
            "while True:\n    break": "unsupported:while",
            "def f():\n    return 1": "unsupported:def",
            "class C:\n    pass": "unsupported:class",
            "f = lambda v: v\nprint(1)": "unsupported:lambda",
            "import os\nprint(1)": "unsupported:import",
            "try:\n    pass\nexcept:\n    pass": "unsupported:try",
            "with 1:\n    pass": "unsupported:with",
            "x = 1\ndel x\nprint(1)": "unsupported:del",
            "global x\nprint(1)": "unsupported:global",
            "total = 0\ntotal += 1\nprint(total)": "unsupported:augassign",
        }
        for source, reason in cases.items():
            assert_unsupported(self, source, reason)

    def test_banned_expressions(self):
        cases = {
            'x = Symbol("x")\nprint(x.subs(x, 2))': "unsupported:attribute",
            "values = [1, 2]\nprint(values[0])": "unsupported:subscript",
            "print(*[1, 2])": "unsupported:starred",
            "print([i for i in [1, 2]])": "unsupported:listcomp",
            "print({i for i in [1, 2]})": "unsupported:setcomp",
            "print({i: i for i in [1, 2]})": "unsupported:dictcomp",
            "print(sum(i for i in [1, 2]))": "unsupported:generator",
            'x = 1\nprint(f"value={x}")': "unsupported:fstring",
            'pairs = {"a": 1}\nprint(pairs)': "unsupported:dict",
            "print({1, 2})": "unsupported:set",
            "x, y = 1, 2\nprint(1)": "unsupported:assign_target",
        }
        for source, reason in cases.items():
            assert_unsupported(self, source, reason)

    def test_calls_must_target_whitelisted_names(self):
        assert_unsupported(
            self, "unknown_fn(1)", "unsupported:unknown_name:unknown_fn"
        )
        assert_unsupported(self, "print(mystery)", "unsupported:unknown_name:mystery")
        assert_unsupported(self, "print(open('f'))", "unsupported:unknown_name:open")

    def test_string_literals_only_name_symbols(self):
        assert_unsupported(self, 'greeting = "hi"\nprint(1)', "unsupported:string_literal")
        assert_unsupported(self, 'print("hello")', "unsupported:string_literal")


class CompatibilityLayerTest(unittest.TestCase):
    def test_approved_math_imports_are_rewritten_without_real_import(self):
        result = assert_success(self, "from math import comb\nprint(comb(10, 3))", "120")
        self.assertEqual("unsupported:from", result["compatibility"]["raw_rejection"])
        self.assertEqual("SUCCESS", result["compatibility"]["post_status"])
        self.assertIn("comb->binomial", result["compatibility"]["actions"])

    def test_approved_module_attributes_are_rewritten(self):
        assert_success(self, "import math\nprint(math.comb(10, 3))", "120")
        assert_success(self, 'import sympy\nx = sympy.Symbol("x")\nprint(sympy.solve(x**2 - 1, x))', "[-1,1]")

    def test_module_attributes_are_only_allowed_as_call_targets(self):
        for source in (
            "import math\nprint(math.sqrt)",
            "import math\nmath.sqrt = 1\nprint(1)",
        ):
            with self.subTest(source=source):
                result = assert_unsupported(self, source, "unsupported:attribute")
                self.assertEqual(["import math"], result["compatibility"]["actions"])

    def test_import_compatibility_keeps_exact_answers_and_reports_action(self):
        result = execute_program("from sympy import Rational\nprint(Rational(1, 3) + Rational(1, 6))")
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual("1/2", result["answer"])
        self.assertEqual("unsupported:from", result["compatibility"]["raw_rejection"])
        self.assertEqual("SUCCESS", result["compatibility"]["post_status"])

    def test_alias_star_unknown_module_and_unknown_attribute_fail_closed(self):
        cases = {
            "import math as m\nprint(m.comb(10, 3))": "unsupported:import_alias",
            "from math import comb as choose\nprint(choose(10, 3))": "unsupported:import_alias",
            "from math import comb\nchoose = comb\nprint(choose(10, 3))": "unsupported:dynamic_alias",
            "from math import comb\nfor comb in range(0, 1):\n    print(comb)": "unsupported:dynamic_alias",
            "import math\nmath = 1\nprint(math.comb(10, 3))": "unsupported:dynamic_alias",
            "from math import *\nprint(sqrt(4))": "unsupported:import_star",
            "from os import system\nprint(system)": "unsupported:import",
            "from math import mystery\nprint(mystery(1))": "unsupported:import_name:math.mystery",
            "import math\nprint(math.mystery(1))": "unsupported:attribute",
        }
        for source, reason in cases.items():
            with self.subTest(source=source):
                assert_unsupported(self, source, reason)


class AttackSurfaceTest(unittest.TestCase):
    """§6 item 2: hostile programs are statically rejected or safely fail."""

    def test_known_escape_hatch_names_are_unknown(self):
        cases = {
            '__import__("os").system("dir")',
            'getattr(print, "__module__")',
            'eval("1 + 1")',
            'exec("x = 1")',
            'compile("1", "<s>", "eval")',
        }
        for source in cases:
            result = execute_program(source)
            self.assertEqual(
                "UNSUPPORTED", result["status"], msg=f"{source!r} -> {result}"
            )
            self.assertTrue(result["reason"].startswith("unsupported:"))

    def test_dynamic_call_via_string_is_rejected(self):
        assert_unsupported(self, 'f = "ev"\nf("al")', "unsupported:string_literal")

    def test_calling_a_variable_fails_safely_at_runtime(self):
        assert_error(self, "n = abs(-1)\nprint(n(1))", "runtime_error:TypeError")

    def test_integer_exponent_bomb_is_blocked_statically(self):
        assert_unsupported(self, "print(10 ** 10 ** 10)", "exponent_too_large")

    def test_computed_integer_exponent_is_blocked_at_runtime(self):
        assert_unsupported(self, "n = 10000\nprint(2 ** n)", "exponent_too_large")

    def test_oversized_source_and_ast_are_rejected(self):
        assert_unsupported(self, ("x = 1\n" * 2000), "source_too_long")
        wide = "print(" + " + ".join(["1"] * 400) + ")"
        assert_unsupported(self, wide, "ast_too_large")


class GuardLimitsTest(unittest.TestCase):
    def test_symbol_budget(self):
        assignments = "\n".join(f"v{i} = {i}" for i in range(13))
        assert_unsupported(self, assignments + "\nprint(v0)", "symbol_limit")
        ok = "\n".join(f"v{i} = {i}" for i in range(12))
        assert_success(self, ok + "\nprint(v11)", "11")

    def test_loop_span_cap(self):
        source = "total = 0\nfor i in range(0, 10001):\n    total = total + 1\nprint(total)"
        assert_unsupported(self, source, "loop_span")

    def test_range_bounds_must_be_static_integers(self):
        source = "bound = abs(-3)\nfor i in range(0, bound):\n    print(i)"
        assert_unsupported(self, source, "loop_bound_not_static")
        assert_unsupported(self, "for i in range(3):\n    print(i)", "invalid_range_call")
        assert_unsupported(
            self, "for i in range(0, 3, 1):\n    print(i)", "invalid_range_call"
        )

    def test_named_constant_bounds_fold_statically(self):
        source = "n = 50\nacc = 0\nfor i in range(1, n + 1):\n    acc = acc + i\nprint(acc)"
        assert_success(self, source, "1275")


class CorrectnessSamplesTest(unittest.TestCase):
    """§6 item 3: >=20 verified end-to-end answers (normalized forms)."""

    CASES = [
        # arithmetic
        ("x = 2 + 3\nprint(x)", "5"),
        ("print(7 * 6)", "42"),
        ("print(10 / 4)", "5/2"),
        ("print(-5 + 3)", "-2"),
        ("print(2 ** 10)", "1024"),
        # loops
        (
            "total = 0\nfor i in range(1, 101):\n    total = total + i\nprint(total)",
            "5050",
        ),
        (
            "product = 1\nfor i in range(1, 6):\n    product = product * i\nprint(product)",
            "120",
        ),
        # rationals and radicals
        ("print(Rational(1, 3) + Rational(1, 6))", "1/2"),
        ("print(sqrt(16))", "4"),
        ("print(sqrt(8))", "2*sqrt(2)"),
        # equation solving
        (
            'x = Symbol("x")\nprint(solve(x**2 - 5*x + 6, x))',
            "[2,3]",
        ),
        (
            'x = Symbol("x")\ny = Symbol("y")\n'
            "solution = solve([x + y - 3, x - y - 1], [x, y])\nprint(solution)",
            "1,2",
        ),
        # calculus
        (
            'x = Symbol("x")\nprint(integrate(x**2, (x, 0, 1)))',
            "1/3",
        ),
        (
            'x = Symbol("x")\nprint(integrate(exp(-x), (x, 0, oo)))',
            "1",
        ),
        (
            'k = Symbol("k")\nprint(N(Sum(k, (k, 1, 10))))',
            "55",
        ),
        (
            'x = Symbol("x")\ncritical = x**3 - 3*x\nprint(solve(diff(critical, x), x))',
            "[-1,1]",
        ),
        # constants and numeric evaluation
        ("print(N(pi, 6))", "314159/100000"),
        ("print(nsimplify(pi))", "pi"),
        ("print(Abs(-5))", "5"),
        ("print(log(E))", "1"),
        ("print(sin(pi / 2))", "1"),
        # simplification identities
        ('x = Symbol("x")\nprint(factor(x**2 - 1))', "(x-1)*(x+1)"),
        (
            'x = Symbol("x")\nprint(simplify(sin(x)**2 + cos(x)**2))',
            "1",
        ),
        # builtins over containers
        ("print(min(3, 1, 2))", "1"),
        ("print(max(3, 1, 2))", "3"),
    ]

    def test_verified_answers(self):
        self.assertGreaterEqual(len(self.CASES), 20)
        for index, (source, expected) in enumerate(self.CASES):
            with self.subTest(case=index, source=source):
                assert_success(self, source, expected)


class OutputContractTest(unittest.TestCase):
    def test_missing_print_statement_is_static_rejection(self):
        assert_unsupported(self, "x = 1", "no_print")

    def test_empty_runtime_output_is_an_error(self):
        assert_error(self, "x = 1\nprint()", "no_output")

    def test_runtime_exception_reports_exception_class(self):
        assert_error(self, "print(1 / 0)", "runtime_error:ZeroDivisionError")

    def test_soft_timeout_is_reported_post_hoc(self):
        timed_out = PotExecutorConfig(soft_timeout_seconds=-1.0)
        assert_error(self, "print(1 + 1)", "timeout", timed_out)

    def test_answer_passes_through_answer_normalization(self):
        # Executor output is normalized exactly like agent answers upstream.
        assert_success(self, "print(10 / 4)", "5/2")
        assert_success(self, "print(1.5 * 2)", "3")
        assert_success(self, "print(55.0000000000000)", "55")


if __name__ == "__main__":
    unittest.main()
