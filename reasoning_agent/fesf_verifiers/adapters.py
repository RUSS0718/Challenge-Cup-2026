"""Small, fail-closed verifier adapters.

Each adapter has a narrow interface and returns the same three evidence states
used by ``SolveMemory``: ``EXACT``, ``REFUTED`` or ``UNKNOWN``.  Inputs are
bounded and parsed with a restricted grammar; no model text is executed as
Python, and no adapter is imported by the default solve path.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from fractions import Fraction
import operator
import re
import time
from typing import Any, Iterable


EvidenceStatus = str
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


@dataclass(frozen=True)
class VerificationResult:
    """Serializable result shared by all three adapters."""

    status: EvidenceStatus
    adapter: str
    claim_id: str
    evidence: str
    result: str = ""
    witness: str = ""
    assumptions: tuple[str, ...] = ()
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SymbolicVerifierConfig:
    max_input_chars: int = 256
    max_ast_nodes: int = 96
    max_symbols: int = 8
    max_exponent: int = 12
    soft_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class FiniteVerifierConfig:
    max_values: int = 64
    max_expression_chars: int = 256
    max_ast_nodes: int = 96
    max_abs_value: int = 10**9
    max_exponent: int = 10


def _result(
    status: str,
    adapter: str,
    claim_id: str,
    evidence: str,
    *,
    result: str = "",
    witness: str = "",
    assumptions: Iterable[str] = (),
    error: str = "",
) -> VerificationResult:
    safe_claim = claim_id if _ID_RE.fullmatch(str(claim_id or "")) else ""
    return VerificationResult(
        status=status,
        adapter=adapter,
        claim_id=safe_claim,
        evidence=evidence[:160],
        result=result[:240],
        witness=witness[:160],
        assumptions=tuple(str(item)[:160] for item in assumptions)[:8],
        error=error[:160],
    )


def _unknown(adapter: str, claim_id: str, error: str, evidence: str = "unsupported") -> VerificationResult:
    return _result("UNKNOWN", adapter, claim_id, evidence, error=error)


class SymbolicConstraintAdapter:
    """Check a restricted symbolic equality or relation with SymPy.

    The adapter proves only the exact relation it can simplify.  It does not
    infer domains; symbolic denominators require an explicit ``x != 0`` style
    assumption, otherwise the result is ``UNKNOWN``.
    """

    name = "symbolic-constraint"

    def __init__(self, config: SymbolicVerifierConfig | None = None) -> None:
        self.config = config or SymbolicVerifierConfig()

    def check_equivalence(
        self,
        left: str,
        right: str,
        claim_id: str = "",
        *,
        assumptions: Iterable[str] = (),
    ) -> VerificationResult:
        return self.check_relation(left, "==", right, claim_id=claim_id, assumptions=assumptions)

    def check_relation(
        self,
        left: str,
        relation: str,
        right: str,
        *,
        claim_id: str = "",
        assumptions: Iterable[str] = (),
    ) -> VerificationResult:
        started = time.monotonic()
        if relation not in {"==", "!=", "<", "<=", ">", ">="}:
            return _unknown(self.name, claim_id, "relation_unsupported")
        try:
            import sympy

            assumption_list = tuple(str(item).strip() for item in assumptions if str(item).strip())[:8]
            left_value, left_tree = self._parse(left, sympy)
            right_value, right_tree = self._parse(right, sympy)
            left_denominators = self._symbolic_denominators(left_tree)
            right_denominators = self._symbolic_denominators(right_tree)
            if left_denominators is None or right_denominators is None:
                return _unknown(self.name, claim_id, "domain_assumption", "symbolic_domain_unresolved")
            denominators = left_denominators + right_denominators
            missing = [name for name in dict.fromkeys(denominators) if not self._has_nonzero_assumption(name, assumption_list)]
            if missing:
                return _unknown(self.name, claim_id, "domain_assumption", "symbolic_domain_unresolved")
            difference = sympy.simplify(left_value - right_value)
            truth = self._relation_truth(difference, relation, sympy)
            if truth is None:
                return _unknown(self.name, claim_id, "relation_undetermined", "symbolic_relation_undetermined")
            if time.monotonic() - started > self.config.soft_timeout_seconds:
                return _unknown(self.name, claim_id, "operation_exceeded_soft_timeout", "symbolic_timeout")
            status = "EXACT" if truth else "REFUTED"
            return _result(
                status,
                self.name,
                claim_id,
                "relation_verified" if truth else "relation_refuted",
                result=str(difference),
                assumptions=("restricted symbolic grammar", *assumption_list),
                error="" if truth else "relation_false",
            )
        except ImportError:
            return _unknown(self.name, claim_id, "sympy_unavailable")
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
            return _unknown(self.name, claim_id, f"unsupported_expression:{type(exc).__name__}")
        except Exception as exc:  # SymPy exception classes vary by version.
            return _unknown(self.name, claim_id, f"sympy_error:{type(exc).__name__}")
    def _parse(self, source: str, sympy: Any) -> tuple[Any, ast.AST]:
        if not isinstance(source, str) or not source.strip() or len(source) > self.config.max_input_chars:
            raise ValueError("input_length")
        tree = ast.parse(source.replace("^", "**"), mode="eval")
        nodes = list(ast.walk(tree))
        if len(nodes) > self.config.max_ast_nodes:
            raise ValueError("ast_size")
        names = {node.id for node in nodes if isinstance(node, ast.Name)}
        if len(names) > self.config.max_symbols or any(name.startswith("_") for name in names):
            raise ValueError("symbols")
        value = self._evaluate(tree.body, {name: sympy.Symbol(name) for name in names}, sympy)
        return value, tree

    def _evaluate(self, node: ast.AST, symbols: dict[str, Any], sympy: Any) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            if abs(node.value) > 10**12:
                raise ValueError("integer_limit")
            return sympy.Integer(node.value)
        if isinstance(node, ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._evaluate(node.operand, symbols, sympy)
            return value if isinstance(node.op, ast.UAdd) else -value
        if not isinstance(node, ast.BinOp) or not isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
        ):
            raise ValueError("syntax")
        left = self._evaluate(node.left, symbols, sympy)
        right = self._evaluate(node.right, symbols, sympy)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("division_by_zero")
            return left / right
        if not getattr(right, "is_Integer", False) or abs(int(right)) > self.config.max_exponent:
            raise ValueError("exponent")
        return left**right

    @staticmethod
    def _symbolic_denominators(tree: ast.AST) -> list[str] | None:
        """Return simple nonzero symbol names, or None when the domain is unresolved.

        Only a denominator that is exactly one identifier can be discharged by
        ``x != 0``.  Compound denominators such as ``x-1`` keep the result
        ``UNKNOWN`` even if some other symbol is declared nonzero.
        """

        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                if isinstance(node.right, ast.Name):
                    names.append(node.right.id)
                elif any(isinstance(item, ast.Name) for item in ast.walk(node.right)):
                    return None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                exponent = SymbolicConstraintAdapter._integer_exponent(node.right)
                if exponent is None:
                    return None
                if exponent >= 0:
                    continue
                if isinstance(node.left, ast.Name):
                    names.append(node.left.id)
                else:
                    return None
        return names

    @staticmethod
    def _integer_exponent(node: ast.AST) -> int | None:
        """Fold a restricted integer exponent; None means the sign is unknown."""

        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
            return SymbolicConstraintAdapter._integer_exponent(node.operand)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = SymbolicConstraintAdapter._integer_exponent(node.operand)
            return None if value is None else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            left = SymbolicConstraintAdapter._integer_exponent(node.left)
            right = SymbolicConstraintAdapter._integer_exponent(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            return left * right
        return None

    @staticmethod
    def _has_nonzero_assumption(name: str, assumptions: Iterable[str]) -> bool:
        compact = [re.sub(r"\s+", "", value).replace("≠", "!=") for value in assumptions]
        return any(re.fullmatch(rf"{re.escape(name)}!=0", value) for value in compact)

    @staticmethod
    def _relation_truth(difference: Any, relation: str, sympy: Any) -> bool | None:
        if relation == "==":
            return True if difference == 0 else False if difference.is_number else None
        if relation == "!=":
            return False if difference == 0 else True if difference.is_number else None
        if relation == "<":
            if getattr(difference, "is_negative", None) is True:
                return True
            if getattr(difference, "is_nonnegative", None) is True:
                return False
        if relation == "<=":
            if getattr(difference, "is_nonpositive", None) is True:
                return True
            if getattr(difference, "is_positive", None) is True:
                return False
        if relation == ">":
            if getattr(difference, "is_positive", None) is True:
                return True
            if getattr(difference, "is_nonpositive", None) is True:
                return False
        if relation == ">=":
            if getattr(difference, "is_nonnegative", None) is True:
                return True
            if getattr(difference, "is_negative", None) is True:
                return False
        return None


class _FiniteExpressionEvaluator:
    """Private exact evaluator shared by finite and counterexample adapters."""

    def __init__(self, config: FiniteVerifierConfig, variable: str) -> None:
        if not _IDENTIFIER_RE.fullmatch(variable) or variable.startswith("_"):
            raise ValueError("variable")
        self.config = config
        self.variable = variable

    def evaluate(self, predicate: str, value: Fraction) -> bool:
        if not isinstance(predicate, str) or not predicate.strip() or len(predicate) > self.config.max_expression_chars:
            raise ValueError("expression_length")
        tree = ast.parse(predicate, mode="eval")
        if len(list(ast.walk(tree))) > self.config.max_ast_nodes:
            raise ValueError("ast_size")
        result = self._eval(tree.body, value)
        if not isinstance(result, bool):
            raise ValueError("predicate_not_boolean")
        return result

    def _eval(self, node: ast.AST, value: Fraction) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            if abs(node.value) > self.config.max_abs_value:
                raise ValueError("integer_limit")
            return Fraction(node.value)
        if isinstance(node, ast.Name) and node.id == self.variable:
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            operand = self._eval(node.operand, value)
            if isinstance(node.op, ast.Not):
                if not isinstance(operand, bool):
                    raise ValueError("not_operand")
                return not operand
            if isinstance(operand, bool):
                raise ValueError("numeric_operand")
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            parts = [self._eval(item, value) for item in node.values]
            if not all(isinstance(item, bool) for item in parts):
                raise ValueError("boolean_operand")
            return all(parts) if isinstance(node.op, ast.And) else any(parts)
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow)
        ):
            left, right = self._eval(node.left, value), self._eval(node.right, value)
            if isinstance(left, bool) or isinstance(right, bool):
                raise ValueError("numeric_operand")
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if right == 0 and isinstance(node.op, (ast.Div, ast.Mod, ast.FloorDiv)):
                raise ZeroDivisionError("division_by_zero")
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.FloorDiv):
                return Fraction(left // right)
            if not right.denominator == 1 or abs(int(right)) > self.config.max_exponent:
                raise ValueError("exponent")
            return left ** int(right)
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, value)
            checks: list[bool] = []
            for operator_node, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, value)
                if isinstance(left, bool) or isinstance(right, bool):
                    raise ValueError("comparison_operand")
                check = {
                    ast.Eq: operator.eq,
                    ast.NotEq: operator.ne,
                    ast.Lt: operator.lt,
                    ast.LtE: operator.le,
                    ast.Gt: operator.gt,
                    ast.GtE: operator.ge,
                }.get(type(operator_node))
                if check is None:
                    raise ValueError("comparison")
                checks.append(bool(check(left, right)))
                left = right
            return all(checks)
        raise ValueError("syntax")


def _to_fraction(value: Any, max_abs: int) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean_value")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+(?:/\d+)?", value.strip()):
        result = Fraction(value.strip())
    else:
        raise ValueError("domain_value")
    if abs(result.numerator) > max_abs or result.denominator > max_abs:
        raise ValueError("domain_value_limit")
    return result


class FiniteDomainAdapter:
    """Check a predicate over one explicit finite domain only."""

    name = "finite-domain"

    def __init__(self, config: FiniteVerifierConfig | None = None) -> None:
        self.config = config or FiniteVerifierConfig()

    def check_all(
        self,
        variable: str,
        predicate: str,
        values: Iterable[Any],
        *,
        claim_id: str = "",
    ) -> VerificationResult:
        try:
            raw_values = list(values)
        except TypeError:
            return _unknown(self.name, claim_id, "domain_type")
        if not raw_values or len(raw_values) > self.config.max_values:
            return _unknown(self.name, claim_id, "domain_empty_or_too_large")
        try:
            domain = [_to_fraction(value, self.config.max_abs_value) for value in raw_values]
            evaluator = _FiniteExpressionEvaluator(self.config, variable)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return _unknown(self.name, claim_id, f"domain_invalid:{type(exc).__name__}")
        try:
            for value in domain:
                if not evaluator.evaluate(predicate, value):
                    return _result(
                        "REFUTED",
                        self.name,
                        claim_id,
                        "finite_predicate_refuted",
                        result="False",
                        witness=f"{variable}={value}",
                        assumptions=("explicit finite domain only",),
                        error="predicate_false",
                    )
            return _result(
                "EXACT",
                self.name,
                claim_id,
                "finite_predicate_verified",
                result=f"checked={len(domain)}",
                assumptions=("explicit finite domain only",),
            )
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
            return _unknown(self.name, claim_id, f"predicate_invalid:{type(exc).__name__}")


class CounterexampleAdapter:
    """Search for a counterexample; no witness means ``UNKNOWN``, not proof."""

    name = "counterexample"

    def __init__(self, config: FiniteVerifierConfig | None = None) -> None:
        self._finite = FiniteDomainAdapter(config)

    def find(
        self,
        variable: str,
        predicate: str,
        values: Iterable[Any],
        *,
        claim_id: str = "",
    ) -> VerificationResult:
        finite = self._finite.check_all(variable, predicate, values, claim_id=claim_id)
        if finite.status == "REFUTED":
            return VerificationResult(
                status="REFUTED",
                adapter=self.name,
                claim_id=finite.claim_id,
                evidence="counterexample_found",
                result=finite.result,
                witness=finite.witness,
                assumptions=("explicit finite search domain only",),
                error="counterexample_found",
            )
        if finite.status == "EXACT":
            return _result(
                "UNKNOWN",
                self.name,
                claim_id,
                "no_counterexample_in_finite_domain",
                result=finite.result,
                assumptions=("absence of a finite witness is not a universal proof",),
            )
        return _result(
            "UNKNOWN",
            self.name,
            claim_id,
            "counterexample_search_unknown",
            error=finite.error or "finite_check_unknown",
        )


__all__ = [
    "CounterexampleAdapter",
    "FiniteDomainAdapter",
    "FiniteVerifierConfig",
    "SymbolicConstraintAdapter",
    "SymbolicVerifierConfig",
    "VerificationResult",
]
