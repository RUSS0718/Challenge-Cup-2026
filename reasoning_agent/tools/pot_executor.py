"""Restricted in-process interpreter for model-provided programs of thought.

Safety model mirrors ``sympy_adapter.py``: a fixed grammar whitelist, no
exec/eval/import/subprocess/network/file IO/recursion, post-hoc soft timeout
reported honestly instead of a hard interrupt. Deterministic by construction;
the interpreter implements ``print`` as an internal output sink and never
touches real stdout. Answers are normalized with ``user_agent.normalize_answer``
so executor output joins the same equivalence grouping as agent answers.
"""

from __future__ import annotations

import ast
import operator
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PotExecutorConfig:
    max_source_chars: int = 4000
    max_ast_nodes: int = 300
    max_symbols: int = 12
    max_loop_span: int = 10000
    max_int_exponent: int = 64
    soft_timeout_seconds: float = 10.0


_SYMPY_FUNCTION_NAMES = frozenset({
    "simplify", "expand", "factor", "solve", "nsimplify", "sqrt", "Abs",
    "log", "exp", "sin", "cos", "tan", "diff", "integrate", "Sum", "N",
    "factorial", "binomial",
})
_SYMPY_FACTORY_NAMES = frozenset({"Symbol", "Rational", "Integer"})
_CONSTANT_NAMES = frozenset({"pi", "E", "I", "oo"})
_BUILTIN_CALL_NAMES = frozenset({
    "print", "int", "float", "abs", "min", "max", "sum", "round", "range",
})
_KNOWN_NAMES = (
    _SYMPY_FUNCTION_NAMES | _SYMPY_FACTORY_NAMES | _CONSTANT_NAMES | _BUILTIN_CALL_NAMES
)

_BANNED_CONSTRUCTS = {
    ast.If: "if",
    ast.While: "while",
    ast.FunctionDef: "def",
    ast.AsyncFunctionDef: "def",
    ast.ClassDef: "class",
    ast.Lambda: "lambda",
    ast.Import: "import",
    ast.ImportFrom: "from",
    ast.Try: "try",
    ast.With: "with",
    ast.AsyncWith: "with",
    ast.AsyncFor: "for",
    ast.Delete: "del",
    ast.Global: "global",
    ast.Nonlocal: "nonlocal",
    ast.AugAssign: "augassign",
    ast.AnnAssign: "annassign",
    ast.Assert: "assert",
    ast.Raise: "raise",
    ast.Return: "return",
    ast.Attribute: "attribute",
    ast.Subscript: "subscript",
    ast.Starred: "starred",
    ast.ListComp: "listcomp",
    ast.SetComp: "setcomp",
    ast.DictComp: "dictcomp",
    ast.GeneratorExp: "generator",
    ast.JoinedStr: "fstring",
    ast.FormattedValue: "fstring",
    ast.Await: "await",
    ast.Yield: "yield",
    ast.YieldFrom: "yield",
    ast.Dict: "dict",
    ast.Set: "set",
}
for _name, _token in (("TryStar", "try"), ("Match", "match"), ("NamedExpr", "walrus")):
    _node_type = getattr(ast, _name, None)
    if _node_type is not None:
        _BANNED_CONSTRUCTS[_node_type] = _token

_COMPARE_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_STATIC_POW_EXPONENT_LIMIT = 256
_STATIC_MAGNITUDE_LIMIT = 10**1000


class _Rejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ExecutionFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _NotStatic(Exception):
    pass


class _TooBig(Exception):
    pass


class _CompatibilityRejected(Exception):
    def __init__(self, reason: str, raw_rejection: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw_rejection = raw_rejection
        self.actions: list[str] = []


_COMPAT_IMPORTS = {
    "math": {
        "sqrt": "sqrt", "factorial": "factorial", "comb": "binomial",
        "pi": "pi", "e": "E", "exp": "exp", "log": "log",
        "sin": "sin", "cos": "cos", "tan": "tan", "fabs": "Abs",
    },
    "sympy": {
        **{name: name for name in _SYMPY_FUNCTION_NAMES | _SYMPY_FACTORY_NAMES},
        **{name: name for name in _CONSTANT_NAMES},
    },
}


def _compatibility_rewrite(source: str) -> tuple[ast.AST, list[str], str | None]:
    if not isinstance(source, str) or not source.strip():
        raise _Rejected("empty_source")
    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError):
        raise _Rejected("syntax_error")

    modules: set[str] = set()
    imported_names: dict[str, str] = {}
    actions: list[str] = []
    raw_rejection: str | None = None

    def add_action(action: str) -> None:
        if action not in actions:
            actions.append(action)

    def reject(reason: str, raw_rejection: str) -> None:
        error = _CompatibilityRejected(reason, raw_rejection)
        error.actions = list(actions)
        raise error

    class Rewrite(ast.NodeTransformer):
        def __init__(self) -> None:
            super().__init__()
            self._attribute_call_depth = 0

        def visit_Import(self, node: ast.Import) -> ast.AST | None:
            nonlocal raw_rejection
            for alias in node.names:
                if alias.asname:
                    reject("unsupported:import_alias", "unsupported:import")
                if alias.name not in _COMPAT_IMPORTS:
                    reject("unsupported:import", "unsupported:import")
                modules.add(alias.name)
                raw_rejection = raw_rejection or "unsupported:import"
                add_action(f"import {alias.name}")
            return None

        def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
            nonlocal raw_rejection
            module = node.module or ""
            if node.level or module not in _COMPAT_IMPORTS:
                reject("unsupported:import", "unsupported:from")
            if any(alias.name == "*" for alias in node.names):
                reject("unsupported:import_star", "unsupported:from")
            allowed = _COMPAT_IMPORTS[module]
            for alias in node.names:
                if alias.asname:
                    reject("unsupported:import_alias", "unsupported:from")
                mapped = allowed.get(alias.name)
                if mapped is None:
                    reject(f"unsupported:import_name:{module}.{alias.name}", "unsupported:from")
                imported_names[alias.name] = mapped
                raw_rejection = raw_rejection or "unsupported:from"
                add_action(f"{alias.name}->{mapped}")
            return None

        def visit_Call(self, node: ast.Call) -> ast.AST:
            if isinstance(node.func, ast.Attribute):
                self._attribute_call_depth += 1
                try:
                    node.func = self.visit(node.func)
                finally:
                    self._attribute_call_depth -= 1
                node.args = [self.visit(argument) for argument in node.args]
                node.keywords = [self.visit(keyword) for keyword in node.keywords]
                return node
            return self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> ast.AST:
            target_names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if target_names & (set(imported_names) | modules):
                reject("unsupported:dynamic_alias", "unsupported:alias")
            if isinstance(node.value, ast.Name) and node.value.id in imported_names:
                reject("unsupported:dynamic_alias", "unsupported:alias")
            return self.generic_visit(node)

        def visit_For(self, node: ast.For) -> ast.AST:
            target_names = {
                subnode.id
                for subnode in ast.walk(node.target)
                if isinstance(subnode, ast.Name)
            }
            if target_names & (set(imported_names) | modules):
                reject("unsupported:dynamic_alias", "unsupported:alias")
            return self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
            if isinstance(node.value, ast.Name) and node.value.id in modules:
                if not isinstance(node.ctx, ast.Load) or self._attribute_call_depth == 0:
                    reject("unsupported:attribute", "unsupported:attribute")
                module = node.value.id
                mapped = _COMPAT_IMPORTS[module].get(node.attr)
                if mapped is None:
                    reject("unsupported:attribute", "unsupported:attribute")
                add_action(f"{module}.{node.attr}->{mapped}")
                return ast.copy_location(ast.Name(id=mapped, ctx=ast.Load()), node)
            return self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> ast.AST:
            mapped = imported_names.get(node.id)
            if mapped is None:
                return node
            return ast.copy_location(ast.Name(id=mapped, ctx=node.ctx), node)

    rewritten = Rewrite().visit(tree)
    ast.fix_missing_locations(rewritten)
    return rewritten, actions, raw_rejection


def _with_compatibility(result: dict[str, Any], telemetry: dict[str, Any], active: bool) -> dict[str, Any]:
    if active:
        result["compatibility"] = telemetry
    return result


def execute_program(
    source: Any,
    config: PotExecutorConfig | None = None,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one whitelisted program and return a machine-readable result.

    Returns {status: SUCCESS|UNSUPPORTED|ERROR, reason: str|None, answer:
    str|None}; ``answer`` is the normalized final printed value. Never raises
    and never starts processes, threads, network or file access.
    """
    started_at = time.monotonic()
    active_config = config or PotExecutorConfig()

    try:
        import sympy
    except ImportError:
        return {"status": "ERROR", "reason": "sympy_unavailable", "answer": None}
    try:
        from user_agent import normalize_answer
    except ImportError:
        return {"status": "ERROR", "reason": "normalize_unavailable", "answer": None}

    if environment is not None:
        if any(not isinstance(name, str) or not name.isidentifier() for name in environment):
            return {"status": "UNSUPPORTED", "reason": "unsupported:environment_name", "answer": None}
        if any(callable(value) for value in environment.values()):
            return {"status": "UNSUPPORTED", "reason": "unsupported:environment_value", "answer": None}
    initial_environment = dict(environment or {})
    deadline = started_at + active_config.soft_timeout_seconds
    outputs: list[str] = []
    execution_environment: dict[str, Any] = initial_environment
    compatibility = {"raw_rejection": None, "actions": [], "post_status": None}
    compatibility_active = False

    try:
        if not isinstance(source, str) or not source.strip():
            raise _Rejected("empty_source")
        if len(source) > active_config.max_source_chars:
            raise _Rejected("source_too_long")
        tree, actions, raw_rejection = _compatibility_rewrite(source)
        compatibility["actions"] = actions
        compatibility["raw_rejection"] = raw_rejection
        compatibility_active = bool(actions)
        plan = _validate(source, active_config, tree, set(initial_environment))
        _run_block(plan, execution_environment, outputs, deadline, active_config, sympy)
    except _CompatibilityRejected as rejected:
        compatibility["actions"] = rejected.actions
        compatibility["raw_rejection"] = rejected.raw_rejection
        compatibility["post_status"] = "UNSUPPORTED"
        return _with_compatibility(
            {"status": "UNSUPPORTED", "reason": rejected.reason, "answer": None},
            compatibility, True,
        )
    except _Rejected as rejected:
        compatibility["post_status"] = "UNSUPPORTED"
        return _with_compatibility(
            {"status": "UNSUPPORTED", "reason": rejected.reason, "answer": None},
            compatibility, compatibility_active,
        )
    except _ExecutionFailed as failed:
        compatibility["post_status"] = "ERROR"
        return _with_compatibility(
            {"status": "ERROR", "reason": failed.reason, "answer": None},
            compatibility, compatibility_active,
        )
    except Exception as exc:
        compatibility["post_status"] = "ERROR"
        return _with_compatibility({
            "status": "ERROR",
            "reason": f"runtime_error:{type(exc).__name__}",
            "answer": None,
        }, compatibility, compatibility_active)

    if time.monotonic() - started_at > active_config.soft_timeout_seconds:
        compatibility["post_status"] = "ERROR"
        return _with_compatibility(
            {"status": "ERROR", "reason": "timeout", "answer": None},
            compatibility, compatibility_active,
        )

    answer_line = next((line for line in reversed(outputs) if line.strip()), None)
    if answer_line is None:
        compatibility["post_status"] = "ERROR"
        return _with_compatibility(
            {"status": "ERROR", "reason": "no_output", "answer": None},
            compatibility, compatibility_active,
        )
    compatibility["post_status"] = "SUCCESS"
    return _with_compatibility({
        "status": "SUCCESS",
        "reason": None,
        "answer": normalize_answer(answer_line),
    }, compatibility, compatibility_active)


def _fold_static_int(node: ast.AST, known_ints: dict[str, int]) -> int:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _fold_static_int(node.operand, known_ints)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Name):
        if node.id in known_ints:
            return known_ints[node.id]
        raise _NotStatic()
    if not isinstance(node, ast.BinOp):
        raise _NotStatic()
    left = _fold_static_int(node.left, known_ints)
    right = _fold_static_int(node.right, known_ints)
    if isinstance(node.op, ast.Add):
        value = left + right
    elif isinstance(node.op, ast.Sub):
        value = left - right
    elif isinstance(node.op, ast.Mult):
        value = left * right
    elif isinstance(node.op, ast.FloorDiv):
        if right == 0:
            raise _NotStatic()
        value = left // right
    elif isinstance(node.op, ast.Mod):
        if right == 0:
            raise _NotStatic()
        value = left % right
    elif isinstance(node.op, ast.Pow):
        if abs(right) > _STATIC_POW_EXPONENT_LIMIT:
            raise _TooBig()
        value = left**right
    else:
        raise _NotStatic()
    if abs(value) > _STATIC_MAGNITUDE_LIMIT:
        raise _TooBig()
    return value


def _validate(
    source: Any,
    config: PotExecutorConfig,
    tree: ast.AST | None = None,
    environment_names: set[str] | None = None,
) -> list[tuple]:
    if not isinstance(source, str) or not source.strip():
        raise _Rejected("empty_source")
    if len(source) > config.max_source_chars:
        raise _Rejected("source_too_long")
    if tree is None:
        try:
            tree = ast.parse(source, mode="exec")
        except (SyntaxError, ValueError):
            raise _Rejected("syntax_error")
    nodes = list(ast.walk(tree))
    if len(nodes) > config.max_ast_nodes:
        raise _Rejected("ast_too_large")

    for node in nodes:
        construct = _BANNED_CONSTRUCTS.get(type(node))
        if construct is not None:
            raise _Rejected(f"unsupported:{construct}")
        if isinstance(node, ast.keyword):
            raise _Rejected("unsupported:kwargs")
        if isinstance(node, ast.Compare) and len(node.ops) > 1:
            raise _Rejected("unsupported:compare_chain")

    assigned_names = set()
    for node in nodes:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for subnode in ast.walk(target):
                    if isinstance(subnode, ast.Name):
                        assigned_names.add(subnode.id)
        elif isinstance(node, ast.For):
            for subnode in ast.walk(node.target):
                if isinstance(subnode, ast.Name):
                    assigned_names.add(subnode.id)

    environment_names = environment_names or set()
    if assigned_names & environment_names:
        raise _Rejected("unsupported:environment_rebind")

    unknown = sorted({
        node.id
        for node in nodes
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in assigned_names
        and node.id not in _KNOWN_NAMES
        and node.id not in environment_names
    })
    if unknown:
        raise _Rejected(f"unsupported:unknown_name:{unknown[0]}")

    symbol_argument_ids = {
        id(node.args[0])
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Symbol"
        and node.args
    }
    for_header_iter_ids = {
        id(node.iter)
        for node in nodes
        if isinstance(node, ast.For)
    }
    for node in nodes:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and id(node) not in for_header_iter_ids
        ):
            raise _Rejected("invalid_range_call")
    for node in nodes:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in symbol_argument_ids
        ):
            raise _Rejected("unsupported:string_literal")

    known_ints: dict[str, int] = {}
    for node in nodes:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            try:
                known_ints[node.targets[0].id] = _fold_static_int(node.value, known_ints)
            except (_NotStatic, _TooBig):
                continue

    for node in nodes:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            try:
                exponent_value = _fold_static_int(node.right, known_ints)
            except _TooBig:
                raise _Rejected("exponent_too_large")
            except _NotStatic:
                continue
            if abs(exponent_value) > config.max_int_exponent:
                raise _Rejected("exponent_too_large")

    has_print = False

    def build_block(statements: list[ast.stmt]) -> list[tuple]:
        nonlocal has_print
        block: list[tuple] = []
        for stmt in statements:
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                    raise _Rejected("unsupported:assign_target")
                block.append(("assign", stmt.targets[0].id, stmt.value))
            elif isinstance(stmt, ast.Expr):
                call = stmt.value
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "print"
                ):
                    raise _Rejected("unsupported:bare_call")
                has_print = True
                block.append(("print", list(call.args)))
            elif isinstance(stmt, ast.For):
                if not isinstance(stmt.target, ast.Name):
                    raise _Rejected("unsupported:assign_target")
                iterator = stmt.iter
                if not (
                    isinstance(iterator, ast.Call)
                    and isinstance(iterator.func, ast.Name)
                    and iterator.func.id == "range"
                    and len(iterator.args) == 2
                    and not iterator.keywords
                ):
                    raise _Rejected("invalid_range_call")
                try:
                    lower_bound = _fold_static_int(iterator.args[0], known_ints)
                    upper_bound = _fold_static_int(iterator.args[1], known_ints)
                except _NotStatic:
                    raise _Rejected("loop_bound_not_static")
                except _TooBig:
                    raise _Rejected("loop_span")
                if upper_bound - lower_bound > config.max_loop_span:
                    raise _Rejected("loop_span")
                if stmt.orelse:
                    raise _Rejected("unsupported:for_else")
                block.append((
                    "for",
                    stmt.target.id,
                    lower_bound,
                    upper_bound,
                    build_block(stmt.body),
                ))
            elif isinstance(stmt, ast.Pass):
                continue
            else:
                fallback = _BANNED_CONSTRUCTS.get(type(stmt), type(stmt).__name__.lower())
                raise _Rejected(f"unsupported:{fallback}")
        return block

    plan = build_block(tree.body)
    if not has_print:
        raise _Rejected("no_print")
    if len(assigned_names) > config.max_symbols:
        raise _Rejected("symbol_limit")
    return plan


def _run_block(
    block: list[tuple],
    environment: dict[str, Any],
    outputs: list[str],
    deadline: float,
    config: PotExecutorConfig,
    sympy: Any,
) -> None:
    for entry in block:
        if time.monotonic() > deadline:
            raise _ExecutionFailed("timeout")
        kind = entry[0]
        if kind == "assign":
            _, name, value_expression = entry
            environment[name] = _evaluate(value_expression, environment, config, sympy)
        elif kind == "print":
            _, arguments = entry
            rendered = [
                str(_evaluate(argument, environment, config, sympy)) for argument in arguments
            ]
            outputs.append(" ".join(rendered))
        else:
            _, loop_variable, lower_bound, upper_bound, body = entry
            for index in range(lower_bound, upper_bound):
                if time.monotonic() > deadline:
                    raise _ExecutionFailed("timeout")
                environment[loop_variable] = index
                _run_block(body, environment, outputs, deadline, config, sympy)


def _resolve_callable(name: str, sympy: Any) -> Any:
    if name in _SYMPY_FUNCTION_NAMES or name in _SYMPY_FACTORY_NAMES:
        return getattr(sympy, name)
    return {
        "int": int,
        "float": float,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "round": round,
    }[name]


def _ensure_number(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if getattr(value, "is_number", False) is True:
        return value
    raise TypeError("non-numeric comparison operand")


def _is_zero(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return value == 0
    return getattr(value, "is_zero", None) is True


def _evaluate(node: ast.AST, environment: dict[str, Any], config: PotExecutorConfig, sympy: Any) -> Any:
    if isinstance(node, ast.Constant):
        if type(node.value) is int:
            return sympy.Integer(node.value)
        if type(node.value) is float or type(node.value) is str:
            return node.value
        raise _Rejected("unsupported:literal")
    if isinstance(node, ast.Name):
        if node.id in environment:
            return environment[node.id]
        if node.id == "pi":
            return sympy.pi
        if node.id == "E":
            return sympy.E
        if node.id == "I":
            return sympy.I
        if node.id == "oo":
            return sympy.oo
        return _resolve_callable(node.id, sympy)
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate(item, environment, config, sympy) for item in node.elts)
    if isinstance(node, ast.List):
        return [_evaluate(item, environment, config, sympy) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate(node.operand, environment, config, sympy)
        return -operand if isinstance(node.op, ast.USub) else +operand
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, environment, config, sympy)
        right = _evaluate(node.right, environment, config, sympy)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if _is_zero(right):
                raise ZeroDivisionError("division by zero")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if _is_zero(right):
                raise ZeroDivisionError("floor division by zero")
            return left // right
        if isinstance(node.op, ast.Mod):
            if _is_zero(right):
                raise ZeroDivisionError("modulo by zero")
            return left % right
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, sympy.Integer)) and abs(int(right)) > config.max_int_exponent:
                raise _Rejected("exponent_too_large")
            return left**right
        raise _Rejected("unsupported:operator")
    if isinstance(node, ast.Compare):
        left = _ensure_number(_evaluate(node.left, environment, config, sympy))
        right = _ensure_number(_evaluate(node.comparators[0], environment, config, sympy))
        return _COMPARE_OPERATORS[type(node.ops[0])](left, right)
    if isinstance(node, ast.Call):
        if node.func.id in environment:
            callable_value = environment[node.func.id]
        else:
            callable_value = _resolve_callable(node.func.id, sympy)
        arguments = [_evaluate(arg, environment, config, sympy) for arg in node.args]
        return callable_value(*arguments)
    raise _Rejected(f"unsupported:{type(node).__name__.lower()}")
