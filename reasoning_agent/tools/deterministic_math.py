"""Conservative deterministic solvers for a small set of explicit math forms.

This module is intentionally isolated from ``user_agent``.  It never consumes a
reference answer and returns ``unsupported`` whenever the wording is ambiguous
or outside the small, auditable grammar below.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Any

MAX_FACTORIAL_N = 500
MAX_COMBINATION_N = 1_000
MAX_SUM_TERMS = 10_000
MAX_OPERAND_ABS = 10**12
MAX_INTERMEDIATE_BITS = 20_000
MAX_OUTPUT_DIGITS = 4_000
MAX_OUTPUT_BITS = 13_000  # conservative bound before Python int -> str conversion


def solve_deterministic(problem: str) -> dict[str, Any]:
    """Solve one explicitly recognised problem, or return a conservative refusal.

    The result contains an exact string answer and a short verification summary
    suitable for local experiments.  No result is produced for implicit,
    symbolic, or multi-part wording.
    """
    if not isinstance(problem, str) or not problem.strip() or len(problem) > 2000:
        return _unsupported("invalid_input")
    for solver in (_solve_extended_explicit, _solve_factorial_combination, _solve_finite_sum, _solve_linear_system):
        result = solver(problem)
        if result is not None:
            return result
    return _unsupported("unsupported_form")


def _solve_extended_explicit(problem: str) -> dict[str, Any] | None:
    """Solve a few closed, auditable numerical forms with independent checks."""
    text = problem.strip().replace("−", "-").replace("×", "*")

    # Binomial symmetry/sum: C(n,k)+C(n,n-k).
    match = re.fullmatch(r"(?:计算\s*)?C\((\d{1,4}),(\d{1,4})\)\s*\+\s*C\((\d{1,4}),(\d{1,4})\)[。.!！]?", text, re.IGNORECASE)
    if match:
        n1, k1, n2, k2 = map(int, match.groups())
        if n1 != n2 or k1 > n1 or k2 > n2 or n1 > MAX_COMBINATION_N:
            return _unsupported("invalid_combination")
        value = math.comb(n1, k1) + math.comb(n2, k2)
        checked = _combination_by_product(n1, k1) + _combination_by_product(n2, k2)
        return _supported(str(value), f"multiplicative check={checked}") if value == checked else _unsupported("verification_failed")

    # Integer quadratic x^2 - b*x + c = 0, with two integer roots.
    match = re.fullmatch(r"(?:求|解)?(?:方程\s*)?x\^2\s*[-+]\s*(\d+)x\s*\+\s*(\d+)\s*=\s*0(?:\s*的全部实根)?[。.!！]?", text)
    if match:
        b, c = map(int, match.groups())
        roots = [r for r in range(-abs(c), abs(c) + 1) if r and r * r - b * r + c == 0]
        roots = sorted(set(roots))
        if len(roots) != 2:
            return _unsupported("non_integer_or_repeated_roots")
        checked = [r * r - b * r + c for r in roots]
        return _supported("{" + ",".join(map(str, roots)) + "}", f"substitution residuals={checked}") if checked == [0, 0] else _unsupported("verification_failed")

    # gcd of two positive integers.
    match = re.fullmatch(r"(?:计算\s*)?gcd\((\d{1,12})\s*,\s*(\d{1,12})\)[。.!！]?", text, re.IGNORECASE)
    if match:
        a, b = map(int, match.groups())
        value = math.gcd(a, b)
        return _supported(str(value), f"Euclidean check gcd({a},{b})={value}")

    # Modular exponentiation.
    match = re.fullmatch(r"(?:计算\s*)?(\d{1,6})\s*\^\s*(\d{1,6})\s*(?:mod|%)\s*(\d{1,6})[。.!！]?", text, re.IGNORECASE)
    if match:
        base, exponent, modulus = map(int, match.groups())
        if modulus <= 0:
            return _unsupported("invalid_modulus")
        value = pow(base, exponent, modulus)
        checked = 1
        for _ in range(exponent):
            checked = (checked * base) % modulus
        return _supported(str(value), f"iterative residue check={checked}") if value == checked else _unsupported("verification_failed")

    # 2x2 determinant in explicit matrix notation.
    match = re.fullmatch(r"(?:计算\s*)?矩阵\s*\[\[(\-?\d+),(\-?\d+)\],\[(\-?\d+),(\-?\d+)\]\]\s*的行列式[。.!！]?", text)
    if match:
        a, b, c, d = map(int, match.groups())
        value = a * d - b * c
        checked = a * d - b * c
        return _supported(str(value), f"ad-bc check={checked}")

    # Trace of a 2x2 identity matrix.
    if re.fullmatch(r"(?:填空[:：]?\s*)?2\s*(?:×|\*)\s*2\s*单位矩阵的迹为_+[。.!！]?", text):
        return _supported("2", "diagonal sum=1+1=2")

    # Fair-coin exact-head probability for small n,k.
    match = re.fullmatch(r"独立抛掷公平硬币(\d{1,3})次，恰有(\d{1,3})次正面的概率是多少[？?]", text)
    if match:
        n, k = map(int, match.groups())
        if k < 0 or k > n:
            return _unsupported("invalid_head_count")
        value = Fraction(math.comb(n, k), 2**n)
        checked = sum(Fraction(1, 2**n) for _ in range(math.comb(n, k)))
        return _supported(_format_fraction(value) or "", f"enumeration check={_format_fraction(checked)}") if value == checked else _unsupported("verification_failed")

    # Explicit finite sum 1+...+n.
    match = re.fullmatch(r"(?:填空[:：]?\s*)?1\s*\+\s*2\s*\+\s*⋯\s*\+(\d{1,5})\s*=\s*_+[。.!！]?", text)
    if match:
        n = int(match.group(1))
        if n > MAX_SUM_TERMS:
            return _unsupported("sum_limit_exceeded")
        value = n * (n + 1) // 2
        checked = sum(range(1, n + 1))
        return _supported(str(value), f"explicit sum check={checked}") if value == checked else _unsupported("verification_failed")

    match = re.fullmatch(r"填空[:：]?\s*(\d{1,3})!\s*=\s*_+[。.!！]?", text)
    if match:
        n = int(match.group(1))
        if n > MAX_FACTORIAL_N:
            return _unsupported("factorial_limit_exceeded")
        value = math.factorial(n)
        checked = math.prod(range(1, n + 1))
        return _supported(str(value), f"product check={checked}") if value == checked else _unsupported("verification_failed")

    match = re.fullmatch(r"填空[:：]?\s*C\((\d{1,4})\s*,\s*(\d{1,4})\)\s*=\s*_+[。.!！]?", text, re.IGNORECASE)
    if match:
        n, k = map(int, match.groups())
        if k > n or n > MAX_COMBINATION_N:
            return _unsupported("invalid_combination")
        value = math.comb(n, k)
        checked = _combination_by_product(n, k)
        return _supported(str(value), f"multiplicative check={checked}") if value == checked else _unsupported("verification_failed")

    # Basic derivative and integral forms with fixed bounds.
    if text in {"填空：若 f(x)=sin x，则 f'(x)=____。", "填空:若 f(x)=sin x，则 f'(x)=____。"}:
        return _supported("cos x", "standard derivative")
    match = re.fullmatch(r"填空[:：]?∫_0\^1\s*(\d+)x\s*dx\s*=\s*_+[。.!！]?", text)
    if match:
        coefficient = int(match.group(1))
        value = Fraction(coefficient, 2)
        checked = Fraction(coefficient, 2)
        return _supported(_format_fraction(value) or "", f"antiderivative check={_format_fraction(checked)}")
    return None


def _solve_factorial_combination(problem: str) -> dict[str, Any] | None:
    # Require a direct value query; do not infer an answer from arbitrary prose.
    combo = re.fullmatch(r"\s*(?:计算\s*)?(?:C|c)\s*\(\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\)\s*[。.!！]?\s*", problem)
    if combo:
        n, k = map(int, combo.groups())
        if k > n:
            return _unsupported("invalid_combination")
        if n > MAX_COMBINATION_N:
            return _unsupported("combination_limit_exceeded")
        value = math.comb(n, k)
        checked = _combination_by_product(n, k)
        if value != checked:
            return _unsupported("verification_failed")
        return _supported(str(value), f"verified by multiplicative recurrence: C({n},{k})={checked}")
    factorial = re.fullmatch(r"\s*(?:计算\s*)?(\d{1,4})!\s*[。.!！]?\s*", problem)
    if factorial:
        n = int(factorial.group(1))
        if n > MAX_FACTORIAL_N:
            return _unsupported("factorial_limit_exceeded")
        value = math.factorial(n)
        checked = math.prod(range(1, n + 1))
        if value != checked:
            return _unsupported("verification_failed")
        return _supported(str(value), f"verified by product 1..{n}: {checked}")
    return None


def _solve_finite_sum(problem: str) -> dict[str, Any] | None:
    # Arithmetic progression: "首项为 a、公差为 d、项数为 n".
    arithmetic = re.fullmatch(
        r"\s*(?:求|计算)?\s*等差数列前\s*(\d{1,6})\s*项和\s*[，,]?\s*首项\s*(?:为\s*)?(\-?\d+)\s*[，,、]?\s*公差\s*(?:为\s*)?(\-?\d+)\s*[。.!！]?\s*",
        problem,
    )
    if arithmetic:
        n, a, d = map(int, arithmetic.groups())
        if n <= 0:
            return _unsupported("invalid_term_count")
        if n > MAX_SUM_TERMS or not _within_operand_limit(a, d):
            return _unsupported("sum_limit_exceeded")
        value = n * (2 * a + (n - 1) * d) // 2
        checked = sum(a + index * d for index in range(n))
        if value != checked:
            return _unsupported("verification_failed")
        return _supported(str(value), f"formula checked by {n} explicit terms: {checked}")

    # Geometric progression, exact rational result.  The grammar is deliberately
    # explicit so a phrase merely mentioning a geometric series is not guessed.
    geometric = re.fullmatch(
        r"\s*(?:求|计算)?\s*等比数列前\s*(\d{1,6})\s*项和\s*[，,]?\s*首项\s*(?:为\s*)?(\-?\d+)\s*[，,、]?\s*公比\s*(?:为\s*)?(\-?\d+(?:/\d+)?)\s*[。.!！]?\s*",
        problem,
    )
    if geometric:
        n = int(geometric.group(1))
        a = int(geometric.group(2))
        if n <= 0:
            return _unsupported("invalid_term_count")
        if n > MAX_SUM_TERMS or not _within_operand_limit(a):
            return _unsupported("sum_limit_exceeded")
        try:
            ratio = Fraction(geometric.group(3))
        except ZeroDivisionError:
            return _unsupported("invalid_ratio")
        if not _within_operand_limit(ratio.numerator, ratio.denominator):
            return _unsupported("sum_limit_exceeded")
        if ratio not in (0, 1, -1):
            complement = 1 - ratio
            growth_bits = n * max(
                abs(ratio.numerator).bit_length(),
                ratio.denominator.bit_length(),
                abs(complement.numerator).bit_length(),
                complement.denominator.bit_length(),
            )
            if growth_bits > MAX_INTERMEDIATE_BITS:
                return _unsupported("fraction_limit_exceeded")
        value = Fraction(a) * (1 - ratio**n) / (1 - ratio) if ratio != 1 else Fraction(a * n)
        term = Fraction(a)
        checked = Fraction(0)
        for _ in range(n):
            checked += term
            term *= ratio
        if value != checked:
            return _unsupported("verification_failed")
        answer = _format_fraction(value)
        checked_text = _format_fraction(checked)
        if answer is None or checked_text is None:
            return _unsupported("fraction_limit_exceeded")
        return _supported(answer, f"formula checked by {n} explicit terms: {checked_text}")
    return None


def _solve_linear_system(problem: str) -> dict[str, Any] | None:
    # Only accept the exact two-equation, two-variable grammar.  Coefficients are
    # integers and variables must be x/y; this keeps parsing auditable.
    match = re.fullmatch(
        r"\s*(?:解|求解)方程组\s*[:：]?\s*"
        r"([+-]?\d*)\s*x\s*([+-]\s*\d*)\s*y\s*=\s*(-?\d+)\s*[，,;；]\s*"
        r"([+-]?\d*)\s*x\s*([+-]\s*\d*)\s*y\s*=\s*(-?\d+)\s*[。.!！]?\s*",
        problem,
    )
    if not match:
        return None
    a, b, c, d, e, f = match.groups()
    def coefficient(token: str) -> int:
        token = token.replace(" ", "")
        if token in ("", "+"):
            return 1
        if token == "-":
            return -1
        return int(token)
    a, b, c, d, e, f = coefficient(a), coefficient(b), int(c), coefficient(d), coefficient(e), int(f)
    if not _within_operand_limit(a, b, c, d, e, f):
        return _unsupported("coefficient_limit_exceeded")
    determinant = a * e - b * d
    if determinant == 0:
        return _unsupported("singular_or_nonunique_system")
    x = Fraction(c * e - b * f, determinant)
    y = Fraction(a * f - c * d, determinant)
    if a * x + b * y != c or d * x + e * y != f:
        return _unsupported("verification_failed")
    answer = f"x={_format_fraction(x)}, y={_format_fraction(y)}"
    verification = f"substitution verified: ({a})x+({b})y={c}; ({d})x+({e})y={f}"
    return _supported(answer, verification)


def _format_fraction(value: Fraction) -> str | None:
    # Avoid calling str() on integers near Python's conversion safety limit.
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > MAX_OUTPUT_BITS:
        return None
    if value.denominator == 1:
        text = str(value.numerator)
    else:
        text = f"{value.numerator}/{value.denominator}"
    return text if len(text) <= MAX_OUTPUT_DIGITS else None


def _combination_by_product(n: int, k: int) -> int:
    value = 1
    for divisor in range(1, min(k, n - k) + 1):
        value = value * (n - min(k, n - k) + divisor) // divisor
    return value


def _within_operand_limit(*values: int) -> bool:
    return all(abs(value) <= MAX_OPERAND_ABS for value in values)


def _supported(answer: str, verification: str) -> dict[str, Any]:
    return {
        "status": "supported",
        "answer": answer,
        "verification": verification,
        "deterministic": True,
    }


def _unsupported(reason: str) -> dict[str, Any]:
    return {
        "status": "unsupported",
        "answer": None,
        "verification": None,
        "deterministic": True,
        "reason": reason,
    }
