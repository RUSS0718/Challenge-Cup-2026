"""Constrained, optional SymPy evidence adapter for local experiments.

This module is deliberately not imported by ``user_agent``. It does not execute
model-provided Python code, access network or files, or start subprocesses.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SympyAdapterConfig:
    max_input_length: int = 128
    max_ast_nodes: int = 64
    max_symbols: int = 8
    soft_timeout_seconds: float = 5.0


class SympyEvidenceAdapter:
    """Check equivalence of a deliberately small arithmetic grammar."""

    def __init__(self, config: SympyAdapterConfig | None = None) -> None:
        self.config = config or SympyAdapterConfig()

    def check_equivalence(
        self, left: str, right: str, claim_id: str = "final_answer"
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        try:
            import sympy
        except ImportError:
            return self._result("UNAVAILABLE", "UNKNOWN", claim_id, "sympy_unavailable")

        try:
            left_expression = self._parse_expression(left, sympy)
            right_expression = self._parse_expression(right, sympy)
            equivalent = sympy.simplify(left_expression - right_expression) == 0
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError) as exc:
            return self._result("ERROR", "UNKNOWN", claim_id, f"unsupported_expression:{type(exc).__name__}")
        except Exception as exc:  # SymPy exception classes vary by supported version.
            return self._result("ERROR", "UNKNOWN", claim_id, f"sympy_error:{type(exc).__name__}")

        if time.monotonic() - started_at > self.config.soft_timeout_seconds:
            return self._result("TIMEOUT", "UNKNOWN", claim_id, "operation_exceeded_soft_timeout")
        claim_status = "SUPPORTED" if equivalent else "REFUTED"
        evidence = "expressions_equivalent" if equivalent else "expressions_differ"
        return self._result("SUCCESS", claim_status, claim_id, evidence)

    def _parse_expression(self, source: str, sympy: Any) -> Any:
        if not isinstance(source, str) or not source.strip() or len(source) > self.config.max_input_length:
            raise ValueError("input_length")
        tree = ast.parse(source, mode="eval")
        nodes = list(ast.walk(tree))
        if len(nodes) > self.config.max_ast_nodes:
            raise ValueError("ast_size")
        names = {node.id for node in nodes if isinstance(node, ast.Name)}
        if len(names) > self.config.max_symbols or any(name.startswith("_") for name in names):
            raise ValueError("symbols")
        return self._evaluate(tree.body, {name: sympy.Symbol(name) for name in names}, sympy)

    def _evaluate(self, node: ast.AST, symbols: dict[str, Any], sympy: Any) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and abs(node.value) < 10**12:
            return sympy.Integer(node.value)
        if isinstance(node, ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._evaluate(node.operand, symbols, sympy)
            return value if isinstance(node.op, ast.UAdd) else -value
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
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
            return left / right
        if not right.is_Integer or abs(int(right)) > 12:
            raise ValueError("exponent")
        return left**right

    @staticmethod
    def _result(
        execution_status: str, claim_status: str, claim_id: str, evidence: str
    ) -> dict[str, Any]:
        return {
            "execution_status": execution_status,
            "claim_status": claim_status,
            "claim_id": claim_id,
            "scope": "final_answer",
            "result": None,
            "evidence": evidence,
            "deterministic": True,
            "assumptions": ["integer and symbolic arithmetic grammar only"],
            "warnings": ["soft timeout is post-operation because no subprocess is allowed"],
            "error": None if execution_status == "SUCCESS" else evidence,
        }
