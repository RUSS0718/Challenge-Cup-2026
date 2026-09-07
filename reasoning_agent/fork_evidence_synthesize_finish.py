"""FESF v1: free/skill branches, evidence synthesis, and bounded finish.

This module is deliberately a small relay rather than a second agent
framework.  It owns a fixed five-call protocol and keeps every piece of
cross-stage state in a fresh :class:`SolveMemory`.
"""

from __future__ import annotations

import ast
import hashlib
import re
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterable

from .fesf_claim_protocol import ClaimExecutor
from .fesf_memory import SolveMemory
from .host_loop_context import HostLoopContext
from .fork_select_deepen_finish import (
    HARD_DEADLINE_SECONDS,
    L0_TOKEN_SEQUENCE,
    RelayResult,
    match_simple_arithmetic_expression,
)


METHOD_ID = "fork_evidence_synthesize_finish_v1"
STAGE_TOKEN_SEQUENCE = (2048, 2048, 2048, 8192, 4096)
SOFT_DEADLINE_SECONDS = 900.0
HARD_DEADLINE_SECONDS_FESF = HARD_DEADLINE_SECONDS
MAX_SKILL_BODY_CHARS = 8_000
MAX_PACKET_CHARS = 6_000
MAX_TOOL_REQUESTS = 3
MAX_INTEGER_BITS = 8_192
MAX_SYMBOLIC_OPS = 128

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_MARKER_RE = re.compile(r"(?im)^[ \t]*{marker}[ \t]*[:：][ \t]*(.*?)\s*$")
_FINAL_RE = re.compile(r"(?im)^[ \t]*(?:FINAL|最终答案|答案)[ \t]*[:：][ \t]*(.*?)\s*$")
_KNOWN_STAGE_MARKERS = (
    "SKILL_CHOICE", "APPLICABILITY", "GOAL", "ANSWER_TYPE", "CONSTRAINTS",
    "STRUCTURE", "BOTTLENECK", "BRANCH", "CLAIMS", "CANDIDATE", "CANDIDATE_B",
    "CANDIDATE_C", "OPEN", "EXACT_EVAL", "CLAIM_DSL", "VERIFY_DSL",
    "PRIMARY_BRANCH", "PRIMARY_REASON",
    "SUPPORTED_CLAIMS", "AUXILIARY_CLAIMS", "REFUTED_CLAIMS", "UNRESOLVED_CLAIMS",
    "CANDIDATE_D", "FINAL", "FINAL_D", "FINAL_D_FOR_CHECK",
)
_STOP_LINE_RE = re.compile(
    r"(?im)^\s*(?:" + "|".join(re.escape(x) for x in _KNOWN_STAGE_MARKERS) + r")\s*[:：]"
)
_D_REQUIRED_MARKERS = (
    "PRIMARY_BRANCH", "PRIMARY_REASON", "SUPPORTED_CLAIMS", "AUXILIARY_CLAIMS",
    "REFUTED_CLAIMS", "UNRESOLVED_CLAIMS", "CANDIDATE_D", "OPEN",
)
_D_MARKER_LINE_RE = re.compile(r"(?im)^[ \t]*([A-Z][A-Z0-9_]*)[ \t]*[:：]")
_RATIONAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\d+/\d+)$")


def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value or "")
    limit = max(0, int(limit))
    if len(text) <= limit:
        return text
    marker = "\n...[省略]...\n"
    if limit <= len(marker):
        return text[:limit]
    head = (limit - len(marker) + 1) // 2
    tail = limit - len(marker) - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def _trace_claim_id(value: Any, *, known: bool) -> str:
    """Keep only conventional branch IDs in the serialized diagnostic trace.

    The protocol accepts bounded arbitrary IDs for interoperability, but an ID
    itself is model-controlled text and can carry a secret.  Full IDs remain in
    the in-memory protocol state; trace output gets a stable alias or UNKNOWN.
    """
    text = str(value or "")
    if not known:
        return "UNKNOWN"
    return text if re.fullmatch(r"[BC][0-9]{1,2}", text) else "CLAIM"


def _closed_final(value: str) -> bool:
    """Reject an obviously truncated or unbalanced final answer."""
    stripped = value.strip()
    if not stripped or stripped.rstrip().endswith(("\\", "=", "+", "-", "*", "/", "^")):
        return False
    depth = 0
    for char in stripped:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _normalize_candidate_answer(value: str | None) -> str:
    """Normalize only representations whose equality can be proven locally."""
    if not isinstance(value, str):
        return ""
    compact = re.sub(r"\s+", "", value).strip().strip("`\"'").strip("。；;，,")
    compact = compact.replace("−", "-").replace("×", "*")
    if not compact:
        return ""
    if _RATIONAL_RE.fullmatch(compact):
        try:
            return str(Fraction(compact))
        except (ValueError, ZeroDivisionError):
            return compact
    return compact


def _candidate_answer_equivalence(left: str | None, right: str | None) -> str:
    """Conservative three-state comparison for the host-owned candidate gate."""
    normalized_left = _normalize_candidate_answer(left)
    normalized_right = _normalize_candidate_answer(right)
    if not normalized_left or not normalized_right:
        return "UNKNOWN"
    if normalized_left == normalized_right:
        return "EQUIVALENT"
    if _RATIONAL_RE.fullmatch(normalized_left) and _RATIONAL_RE.fullmatch(normalized_right):
        return "NOT_EQUIVALENT"
    return "UNKNOWN"


def _marker_value(text: str | None, marker: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(_MARKER_RE.pattern.format(marker=re.escape(marker)), text)
    return match.group(1).strip() if match else ""


def _marker_values(text: str | None, marker: str) -> list[str]:
    if not isinstance(text, str):
        return []
    pattern = _MARKER_RE.pattern.format(marker=re.escape(marker))
    return [m.group(1).strip() for m in re.finditer(pattern, text)]


def _is_placeholder(value: str | None) -> bool:
    if not isinstance(value, str):
        return True
    folded = value.strip().strip("`'\"“”‘’").strip("。.,，；;:：!?！？ ").casefold()
    return (
        not folded
        or folded in {"unknown", "none", "n/a", "tbd", "todo", "答案", "result", "output"}
        or folded in {"<answer>", "<result>", "<答案>", "[answer]", "[result]", "[答案]", "[option letter]", "[core answer]"}
        or "..." in folded
    )


def _error_category(exc: BaseException) -> str:
    category = str(getattr(exc, "category", "") or "").casefold()
    if "timeout" in category or "timeout" in type(exc).__name__.casefold():
        return "timeout"
    if "rate" in category or "429" in category:
        return "rate_limit"
    if "http" in category or "status" in category:
        return "http_status"
    return "model_error"


# ── Independent Skill metadata loader ─────────────────────────────────────


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    content_hash: str


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    text = text.replace("\r\n", "\n")
    if not isinstance(text, str) or not text.startswith("---\n"):
        raise ValueError("frontmatter_missing")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("frontmatter_unclosed")
    header = text[4:end].splitlines()
    values: dict[str, str] = {}
    index = 0
    while index < len(header):
        line = header[index]
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        key, raw = match.groups()
        if raw.strip() in {">", "|"}:
            chunks: list[str] = []
            index += 1
            while index < len(header) and (header[index].startswith(" ") or header[index].startswith("\t")):
                chunks.append(header[index].strip())
                index += 1
            values[key] = " ".join(chunks).strip()
            continue
        values[key] = raw.strip().strip("'\"")
        index += 1
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    return values, body


class SkillRegistry:
    """Scan only first-level skill folders and load one body on demand."""

    def __init__(self, root: Path | None = None, *, strict: bool = False) -> None:
        self.root = (root or Path(__file__).resolve().parent / "fesf_skills").resolve()
        self.strict = strict
        self.errors: list[str] = []
        self._skills: dict[str, SkillMetadata] = {}
        self._bodies: dict[str, str] = {}
        self._discover()

    def _discover(self) -> None:
        if not self.root.exists() or not self.root.is_dir():
            self.errors.append("root_missing")
            return
        try:
            entries = sorted(self.root.iterdir(), key=lambda p: p.name)
        except OSError:
            self.errors.append("root_unreadable")
            return
        for folder in entries:
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            path = folder / "SKILL.md"
            try:
                resolved = path.resolve()
                if resolved.parent != folder.resolve() or resolved.parent.parent != self.root:
                    raise ValueError("path_outside_registry")
                text = resolved.read_text(encoding="utf-8")
                front, _ = _parse_frontmatter(text)
                name = front.get("name", "").strip()
                description = front.get("description", "").strip()
                # Skill names are local metadata but are still copied into
                # bounded diagnostics.  Keep the registry contract finite so
                # a custom skill cannot smuggle an unbounded/secret marker
                # through the route event.
                if len(name) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
                    raise ValueError("invalid_name")
                if not description:
                    raise ValueError("description_missing")
                description_folded = description.casefold()
                # Every Skill must declare a positive applicability boundary
                # and an explicit non-applicability boundary.  Only tool
                # Skills need to mention the optional EXACT_EVAL protocol;
                # theorem/strategy Skills are valid without a tool marker.
                if not ("use when" in description_folded and "do not use" in description_folded):
                    raise ValueError("description_scope_missing")
                if name in self._skills:
                    raise ValueError("duplicate_name")
                self._skills[name] = SkillMetadata(
                    name=name,
                    description=description,
                    path=resolved,
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )
            except (OSError, UnicodeError, ValueError) as exc:
                self.errors.append(f"{folder.name}:{type(exc).__name__}:{str(exc)[:48]}")
                if self.strict:
                    raise ValueError(f"invalid_skill:{folder.name}:{str(exc)[:48]}") from exc

    def metadata(self) -> list[SkillMetadata]:
        return list(self._skills.values())

    def catalog_text(self) -> str:
        if not self._skills:
            return "SKILL_CATALOG: NONE"
        lines = ["SKILL_CATALOG:"]
        # Expose every registered metadata row under the bounded catalog cap;
        # silently showing only the first three made valid Skills unreachable.
        for item in self.metadata():
            lines.append(f"- {item.name}: {item.description}")
        return _clip("\n".join(lines), 4_500)

    def get(self, name: str) -> SkillMetadata | None:
        return self._skills.get(name)

    def load_body(self, name: str) -> tuple[SkillMetadata | None, str]:
        item = self.get(name)
        if item is None:
            return None, ""
        if name not in self._bodies:
            try:
                text = item.path.read_text(encoding="utf-8")
                _, body = _parse_frontmatter(text)
                self._bodies[name] = _clip(body.strip(), MAX_SKILL_BODY_CHARS)
            except (OSError, UnicodeError, ValueError):
                return item, ""
        return item, self._bodies.get(name, "")


# ── Restricted EXACT_EVAL tool ─────────────────────────────────────────────


def _safe_symbolic_eval(source: str) -> Any:
    import sympy  # imported by the host, never by a Skill or model request

    source = source.strip().replace("^", "**").replace("×", "*").replace("−", "-")
    if not source or len(source) > 256:
        raise ValueError("expression_length")
    tree = ast.parse(source, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 64:
        raise ValueError("ast_size")
    names = {node.id for node in nodes if isinstance(node, ast.Name)}
    if len(names) > 8 or any(name.startswith("_") for name in names):
        raise ValueError("symbols")
    symbols = {name: sympy.Symbol(name) for name in names}

    def numeric_coefficient_bits(value: Any) -> int:
        """Estimate the largest integer coefficient before materialising it."""
        if isinstance(value, sympy.Integer):
            return abs(int(value)).bit_length()
        if isinstance(value, sympy.Rational):
            numerator, denominator = value.as_numer_denom()
            return max(abs(int(numerator)).bit_length(), abs(int(denominator)).bit_length())
        if isinstance(value, sympy.Pow) and getattr(value.exp, "is_Integer", False):
            return numeric_coefficient_bits(value.base) * abs(int(value.exp))
        if isinstance(value, sympy.Basic):
            return min(
                MAX_INTEGER_BITS + 1,
                max((numeric_coefficient_bits(item) for item in value.args), default=0),
            )
        return 0

    def check_size(value: Any) -> Any:
        if isinstance(value, sympy.Integer):
            if abs(int(value)).bit_length() > MAX_INTEGER_BITS:
                raise ValueError("result_size")
        elif isinstance(value, sympy.Rational):
            numerator, denominator = value.as_numer_denom()
            if max(abs(int(numerator)).bit_length(), abs(int(denominator)).bit_length()) > MAX_INTEGER_BITS:
                raise ValueError("result_size")
        elif isinstance(value, sympy.Basic):
            if numeric_coefficient_bits(value) > MAX_INTEGER_BITS:
                raise ValueError("result_size")
            if sympy.count_ops(value) > MAX_SYMBOLIC_OPS:
                raise ValueError("symbolic_size")
        return value

    def evaluate(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool) and abs(node.value) <= 10**12:
            return sympy.Integer(node.value)
        if isinstance(node, ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            raise ValueError("syntax")
        left, right = evaluate(node.left), evaluate(node.right)
        if isinstance(node.op, ast.Add):
            return check_size(left + right)
        if isinstance(node.op, ast.Sub):
            return check_size(left - right)
        if isinstance(node.op, ast.Mult):
            return check_size(left * right)
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("division_by_zero")
            return check_size(left / right)
        if not getattr(right, "is_Integer", False) or abs(int(right)) > 12:
            raise ValueError("exponent")
        exponent = int(right)
        if numeric_coefficient_bits(left) * abs(exponent) > MAX_INTEGER_BITS:
            raise ValueError("result_size")
        return check_size(left**right)

    return evaluate(tree.body)


def _symbolic_denominators(source: str) -> list[str]:
    normalized = source.strip().replace("^", "**").replace("×", "*").replace("−", "-")
    tree = ast.parse(normalized, mode="eval")
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            denominator = ast.unparse(node.right).replace("**", "^")
            if any(isinstance(item, ast.Name) for item in ast.walk(node.right)):
                result.append(denominator)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = _constant_int(node.right)
            if any(isinstance(item, ast.Name) for item in ast.walk(node.left)):
                if exponent is None:
                    # The evaluator may simplify a symbolic exponent to a
                    # negative integer.  Without proving its sign, reject
                    # the request rather than silently accepting a pole.
                    result.append("__UNRESOLVED_POWER_DOMAIN__")
                elif exponent < 0:
                    result.append(ast.unparse(node.left).replace("**", "^"))
    return result


def _constant_int(node: ast.AST) -> int | None:
    """Evaluate only tiny integer exponent syntax, without SymPy execution."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return int(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _constant_int(node.operand)
        return value if value is None or isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        left, right = _constant_int(node.left), _constant_int(node.right)
        if left is None or right is None or abs(left) > 10**6 or abs(right) > 10**6:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        return left * right
    return None


def _has_explicit_nonzero(scope: str, denominator: str) -> bool:
    compact_denominator = re.sub(r"\s+", "", denominator).replace("^", "**")
    if not compact_denominator:
        return False
    pieces = [
        re.sub(r"\s+", "", item).replace("^", "**")
        for item in re.split(r"(?:,|;|，|；|且|\band\b)", scope, flags=re.I)
        if item.strip()
    ]
    for piece in pieces:
        while piece.startswith("(") and piece.endswith(")"):
            piece = piece[1:-1]
        match = re.fullmatch(r"(.+?)(?:!=|≠|不等于|不为)(0)", piece)
        if match and match.group(1) == compact_denominator:
            return True
        if piece.endswith("非零") and piece[:-2] == compact_denominator:
            return True
    return False


def _is_finite_value(value: Any) -> bool:
    import sympy

    if value in {sympy.zoo, sympy.oo, -sympy.oo, sympy.nan}:
        return False
    return getattr(value, "is_finite", None) is not False


def _claim_binds_tool(claim: Any, expression: str, result: str, expected: str) -> bool:
    if claim is None:
        return False
    compact_claim = re.sub(r"\s+", "", str(claim.content)).replace("^", "**")
    expr = re.sub(r"\s+", "", expression).replace("^", "**")
    value = re.sub(r"\s+", "", expected or result).replace("^", "**")
    # Only a standalone canonical equation is eligible for deterministic
    # support/refutation.  Narrative claims remain proposed/unresolved even
    # when they mention the same fragments or contain a larger conjunction.
    return bool(expr and value and compact_claim in {f"{expr}={value}", f"{expr}=={value}"})


def _parse_tool_payload(payload: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for piece in re.split(r"[;\n]", payload.strip().strip("`").strip()):
        if not piece.strip() or "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        key, value = key.strip().casefold(), value.strip()
        if key in {"claim_id", "expr", "expected", "scope"}:
            if key in fields:
                raise ValueError("duplicate_field")
            fields[key] = value
        else:
            raise ValueError("unknown_field")
    return fields


def evaluate_exact_request(request: str, request_index: int = 0) -> dict[str, Any]:
    """Execute one host-owned EXACT_EVAL DSL request.

    Every malformed or unsafe request returns ``UNKNOWN`` and a bounded error;
    it never executes arbitrary model text.
    """
    evidence_id = f"T{max(1, int(request_index) + 1)}"
    base = {
        "evidence_id": evidence_id,
        "source": "exact-evaluation",
        "status": "UNKNOWN",
        "execution_status": "rejected",
        "claim_id": "",
        "scope": "",
        "result": "",
        "assumptions": ["restricted arithmetic and symbolic grammar"],
        "error": None,
    }
    if not isinstance(request, str):
        base["error"] = "request_type"
        return base
    request = request.replace("```", "").strip()
    match = re.search(r"(?im)^\s*EXACT_EVAL\s*[:：]\s*(.*?)\s*$", request)
    if not match:
        base["error"] = "marker_missing"
        return base
    try:
        fields = _parse_tool_payload(match.group(1))
        claim_id, expr, scope = fields.get("claim_id", ""), fields.get("expr", ""), fields.get("scope", "")
        expected = fields.get("expected", "")
        if not _ID_RE.fullmatch(claim_id) or not expr.strip() or not scope.strip():
            raise ValueError("required_field")
        # Preserve identifiers in an UNKNOWN result so the host can report and
        # reject an out-of-scope request without leaking its expression.
        base["claim_id"], base["scope"] = claim_id, _clip(scope, 240)
        if _is_placeholder(expr) or _is_placeholder(scope):
            raise ValueError("placeholder")
        denominators = _symbolic_denominators(expr) + (_symbolic_denominators(expected) if expected.strip() else [])
        missing_domain = [item for item in denominators if not _has_explicit_nonzero(scope, item)]
        if missing_domain:
            raise ValueError("domain_assumption")
        import sympy
        actual_value = _safe_symbolic_eval(expr)
        if not _is_finite_value(actual_value):
            raise ValueError("undefined_result")
        actual_text = str(actual_value).replace("**", "^")
        status = "EXACT"
        if expected.strip():
            expected_value = _safe_symbolic_eval(expected)
            if not _is_finite_value(expected_value):
                raise ValueError("undefined_expected")
            if sympy.simplify(actual_value - expected_value) != 0:
                status = "REFUTED"
        base.update({
            "status": status,
            "execution_status": "ok",
            "claim_id": claim_id,
            "scope": _clip(scope, 240),
            "result": _clip(actual_text, 500),
            "assumptions": [
                "restricted arithmetic and symbolic grammar",
                *[f"{item} != 0" for item in dict.fromkeys(denominators)],
            ],
            "checked_expression": _clip(expr, 300),
            "checked_expected": _clip(expected, 300),
            "error": None,
        })
        return base
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        base["error"] = _clip(str(exc) or type(exc).__name__, 80)
        return base
    except Exception as exc:
        base["error"] = _clip(f"evaluator:{type(exc).__name__}", 80)
        return base


# ── FESF prompts and protocol parsing ──────────────────────────────────────


ANALYZE_PROMPT = """你负责 A / Analyze + route。只拆解原题并选择 Skill，不完成整题。
第一行必须是 SKILL_CHOICE: <已列出的 skill name> 或 NONE；第二行必须是
APPLICABILITY: YES 或 NO。随后输出 GOAL、ANSWER_TYPE、CONSTRAINTS、STRUCTURE、BOTTLENECK。
对 exact-evaluation 仅在题目目标可落到一个已经闭合、有限的算术/符号表达式时选 YES；
若仍需证明、推导、搜索、优化、存在性论证或几何解释，选 NONE/NO。只依据 Skill 的
name/description 判断适用性，不猜测未列出的 Skill。"""

FREE_BRANCH_PROMPT = """你负责 B / Free branch。保持自由求解，不加载或复述任何 Skill。
提出一条独立、可检查的解法，并用命题 ID 保存中间事实。严格输出：
BRANCH: B
CLAIMS:
B1: <完整命题>
（可继续 B2、B3；每条自含依据和结论）
CANDIDATE_B: <候选或 UNKNOWN>
OPEN: <仍需完成的义务>"""

SKILL_BRANCH_PROMPT = """你负责 C / Skill branch。使用宿主注入的这一份 Skill，形成与 B 互补的候选。
先完成推导；只有已经得到一个有限、闭合的表达式时才提出 Skill 允许的受限工具请求。
工具请求与命题必须一一对应：在 CLAIMS 中先写一条独立的规范等式命题，格式严格为
`C1: <expr>=<expected_or_result>`；这一行只能有等式本身，不能有解释、标签、单位或合取。
随后写 `EXACT_EVAL: claim_id=C1; expr=<同一表达式>; expected=<同一等式右侧（可选）>; scope=<具体范围>`。
每个请求只引用一个这样的命题；表达式未闭合、范围不清或不适用时不发请求。
不自行执行请求，不输出最终答案。严格输出：
BRANCH: C
CLAIMS:
C1: <standalone canonical equation>
（可继续 C2、C3；非工具命题可用自然语言，但不得绑定工具证据）
EXACT_EVAL: claim_id=C1; expr=<表达式>; expected=<可选表达式>; scope=<明确范围>
CANDIDATE_C: <候选或 UNKNOWN>
OPEN: <仍需完成的义务>
没有适用 Skill 时仍走互补自由求解，但不要伪造工具证据。"""

EVIDENCE_SYNTHESIS_PROMPT = """你负责 D / Evidence synthesis。只依据宿主给出的结构化 claims 和 evidence。
选择一条 PRIMARY_BRANCH 作为主线，但不要整体否定另一分支；可把另一分支的命题列为辅助。
逐条处理宿主 evidence：状态为 EXACT 的证据若 claim_id 已知，就把该命题连同 evidence_id
写入 SUPPORTED_CLAIMS；状态为 REFUTED 的证据同理写入 REFUTED_CLAIMS。先完成这一步，
再选择主线和整理其它命题；只要 EVIDENCE 中出现一条可用证据，相应列表就不能写 none。
例如 `T1 [evidence.status=EXACT; claim=C1]` 必须产生 `C1 <- T1`，即使 PRIMARY_BRANCH 选 B，C1
也应作为局部已支持事实保留。不要省略可用证据，但仍可把未被证据覆盖的 B/C 命题保留为
AUXILIARY 或 UNRESOLVED；不要把辅助分支整体否定。
只有引用存在且状态允许的 evidence 才能写入 SUPPORTED_CLAIMS/REFUTED_CLAIMS。严格输出每个字段一次：
PRIMARY_BRANCH: B 或 C
PRIMARY_REASON: <完整度、约束覆盖和证据依据>
SUPPORTED_CLAIMS: <claim_id <- evidence_id; ...>
AUXILIARY_CLAIMS: <claim_id; ...>
REFUTED_CLAIMS: <claim_id <- evidence_id; ...>
UNRESOLVED_CLAIMS: <claim_id; ...>
CANDIDATE_D: <当前候选或 UNKNOWN>
OPEN: <E 仍需完成的义务>
未被硬证据支持的命题可继续作为候选/未决，不能伪造确定性。"""

FINISH_PROMPT = """你负责 E / Finish。回到原题，利用 D 的主线、辅助命题、反证、未决义务和工具范围完成答案。
可以修正主线的局部错误，但不得恢复被硬证据反驳的命题。不要复述 B/C 原始全文。
宿主提供的 CANDIDATES 是唯一允许选择的候选集合；只能选择其中一个候选的答案，不能创造新答案。
如果候选集合为空、证据冲突或无法确定，必须写 FINAL: UNKNOWN。
最后一行必须且只能是 FINAL: <唯一答案>；确实无法确定时写 FINAL: UNKNOWN。"""


@dataclass
class _BranchPacket:
    branch: str
    claims: list[tuple[str, str]]
    candidate: str
    open_text: str
    tool_requests: list[str]


def _section_after_marker(text: str, marker: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(marker)}\s*[:：]\s*", text or "")
    if not match:
        return ""
    tail = text[match.end() :]
    stop = _STOP_LINE_RE.search(tail)
    return tail[: stop.start()] if stop else tail


def _parse_branch_packet(response: str, branch: str) -> _BranchPacket:
    expected = branch.upper()
    claims: list[tuple[str, str]] = []
    block = _section_after_marker(response, "CLAIMS")
    for line in block.splitlines():
        line = line.strip().lstrip("-* ")
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]{0,31})\s*[:：]\s*(.+)$", line)
        if not match:
            continue
        claim_id, content = match.groups()
        if _ID_RE.fullmatch(claim_id) and content.strip() and not _is_placeholder(content):
            claims.append((claim_id, _clip(content.strip(), 900)))
    # A compact fallback keeps compatibility with a model that follows the
    # older six-field branch packet while still producing a named claim.
    if not claims:
        pieces = []
        for marker in ("METHOD", "KEY_LEMMA", "PLAN", "EXPECTED_FORM", "RISK"):
            value = _marker_value(response, marker)
            if value and not _is_placeholder(value):
                pieces.append(f"{marker}={value}")
        if pieces:
            claims.append((f"{expected}1", _clip("；".join(pieces), 900)))
    candidate = ""
    for marker in (f"CANDIDATE_{expected}", "CANDIDATE", "ANSWER"):
        value = _marker_value(response, marker)
        if value and not _is_placeholder(value):
            candidate = _clip(value, 500)
            break
    open_text = _clip(_marker_value(response, "OPEN"), 500)
    requests = [
        line.strip().strip("` ")
        for line in (response or "").splitlines()
        if re.match(r"(?i)^\s*EXACT_EVAL\s*[:：]", line)
    ]
    return _BranchPacket(expected, claims, candidate, open_text, requests)


def _parse_ids(value: str, *, with_evidence: bool = False) -> list[tuple[str, list[str]]]:
    output: list[tuple[str, list[str]]] = []
    for piece in re.split(r"[,;\n]+", value or ""):
        piece = piece.strip().lstrip("-* ")
        if not piece:
            continue
        if "<-" in piece:
            left, right = piece.split("<-", 1)
            ids = re.findall(r"[A-Za-z][A-Za-z0-9_-]{0,31}", left)
            evidence = re.findall(r"[A-Za-z][A-Za-z0-9:_-]{0,31}", right)
            if ids and _ID_RE.fullmatch(ids[0]):
                output.append((ids[0], [x for x in evidence if _ID_RE.fullmatch(x)]))
        else:
            ids = re.findall(r"[A-Za-z][A-Za-z0-9_-]{0,31}", piece)
            for item in ids[:8]:
                if _ID_RE.fullmatch(item):
                    output.append((item, []))
    return output


def _parse_d_packet(response: str, memory: SolveMemory) -> dict[str, Any]:
    fields: dict[str, str] = {}
    missing: list[str] = []
    duplicate: list[str] = []
    illegal = [
        marker for marker in _D_MARKER_LINE_RE.findall(response or "")
        if marker not in _D_REQUIRED_MARKERS
    ]
    if illegal:
        return {
            "protocol_ok": False,
            # Marker names are model-controlled text and can contain secrets;
            # keep diagnostics enumerable without copying their contents.
            "protocol_error": "illegal_marker",
            "primary": "",
            "supported": [],
            "auxiliary": [],
            "refuted": [],
            "unresolved": [],
            "candidate_present": False,
        }
    for marker in _D_REQUIRED_MARKERS:
        values = _marker_values(response, marker)
        if not values:
            missing.append(marker)
        elif len(values) != 1:
            duplicate.append(marker)
        else:
            fields[marker] = values[0]
    if missing or duplicate:
        return {
            "protocol_ok": False,
            "protocol_error": "missing=" + ",".join(missing) + ";duplicate=" + ",".join(duplicate),
            "primary": "",
            "supported": [],
            "auxiliary": [],
            "refuted": [],
            "unresolved": [],
            "candidate_present": False,
        }

    primary = fields["PRIMARY_BRANCH"].upper()
    available_sources = {claim.source for claim in memory.claims}
    if primary not in {"B", "C"} or primary not in available_sources:
        return {
            "protocol_ok": False,
            "protocol_error": "primary_branch_invalid",
            "primary": primary,
            "supported": [],
            "auxiliary": [],
            "refuted": [],
            "unresolved": [],
            "candidate_present": False,
        }
    primary_reason = _clip(fields["PRIMARY_REASON"], 700)
    if _is_placeholder(primary_reason):
        return {
            "protocol_ok": False,
            "protocol_error": "primary_reason_missing",
            "primary": primary,
            "supported": [],
            "auxiliary": [],
            "refuted": [],
            "unresolved": [],
            "candidate_present": False,
        }
    supported_refs = _parse_ids(fields["SUPPORTED_CLAIMS"], with_evidence=True)
    auxiliary_refs = _parse_ids(fields["AUXILIARY_CLAIMS"])
    refuted_refs = _parse_ids(fields["REFUTED_CLAIMS"], with_evidence=True)
    unresolved_refs = _parse_ids(fields["UNRESOLVED_CLAIMS"])
    claim_map = {claim.id: claim for claim in memory.claims}
    evidence_map = {item.id: item for item in memory.evidence}

    # Keep category membership separate from evidence validation.  A claim
    # that appears in more than one D list is a protocol conflict, even when
    # one of the attached evidence references is malformed; fail closed by
    # placing it in UNRESOLVED with no inherited evidence IDs.
    refs_by_category: dict[str, list[tuple[str, list[str]]]] = {
        "supported": supported_refs,
        "auxiliary": auxiliary_refs,
        "refuted": refuted_refs,
        "unresolved": unresolved_refs,
    }
    memberships: dict[str, set[str]] = {}
    evidence_by_claim: dict[tuple[str, str], list[str]] = {}
    for category, refs in refs_by_category.items():
        for claim_id, evidence_ids in refs:
            if claim_id not in claim_map:
                continue
            memberships.setdefault(claim_id, set()).add(category)
            if evidence_ids:
                evidence_by_claim.setdefault((category, claim_id), []).extend(evidence_ids)

    supported: list[str] = []
    auxiliary: list[str] = []
    refuted: list[str] = []
    unresolved: list[str] = []
    for claim in memory.claims:
        categories = memberships.get(claim.id, set())
        if len(categories) != 1:
            unresolved.append(claim.id)
            memory.set_claim_status(claim.id, "UNRESOLVED")
            continue
        category = next(iter(categories))
        if category == "supported":
            evidence_ids = list(dict.fromkeys(evidence_by_claim.get((category, claim.id), [])))
            valid = bool(evidence_ids) and all(
                (evidence_map.get(eid) is not None
                 and evidence_map[eid].status == "EXACT"
                 and evidence_map[eid].claim_id == claim.id)
                for eid in evidence_ids
            )
            if valid and memory.set_claim_status(claim.id, "SUPPORTED", evidence_ids):
                supported.append(claim.id)
            else:
                unresolved.append(claim.id)
                memory.set_claim_status(claim.id, "UNRESOLVED")
        elif category == "refuted":
            evidence_ids = list(dict.fromkeys(evidence_by_claim.get((category, claim.id), [])))
            valid = bool(evidence_ids) and all(
                (evidence_map.get(eid) is not None
                 and evidence_map[eid].status == "REFUTED"
                 and evidence_map[eid].claim_id == claim.id)
                for eid in evidence_ids
            )
            if valid and memory.set_claim_status(claim.id, "REFUTED", evidence_ids):
                refuted.append(claim.id)
            else:
                unresolved.append(claim.id)
                memory.set_claim_status(claim.id, "UNRESOLVED")
        elif category == "auxiliary":
            auxiliary.append(claim.id)
            memory.set_claim_status(claim.id, "PROPOSED")
        else:
            unresolved.append(claim.id)
            memory.set_claim_status(claim.id, "UNRESOLVED")
    unresolved = list(dict.fromkeys(unresolved))
    memory.set_synthesis(
        primary_branch=primary,
        primary_reason=primary_reason,
        supported=supported,
        auxiliary=auxiliary,
        refuted=refuted,
        unresolved=unresolved,
        open_obligations=[fields["OPEN"]],
    )
    candidate = fields["CANDIDATE_D"]
    if candidate and not _is_placeholder(candidate):
        memory.add_candidate(primary or "B", candidate, supported + auxiliary)
    return {
        "protocol_ok": True,
        "protocol_error": "",
        "primary": primary,
        "supported": supported,
        "auxiliary": auxiliary,
        "refuted": refuted,
        "unresolved": unresolved,
        "candidate_present": bool(candidate and not _is_placeholder(candidate)),
    }


class ForkEvidenceSynthesizeFinishRelay:
    """Fixed-budget FESF relay with a per-solve memory object."""

    def __init__(
        self,
        client: Any,
        clock: Callable[[], float] = time.monotonic,
        registry: SkillRegistry | None = None,
        *,
        enable_exact_eval: bool = False,
        memory_factory: Callable[[], SolveMemory] | None = None,
        host_context: HostLoopContext | None = None,
        claim_executor: ClaimExecutor | None = None,
    ) -> None:
        self.client = client
        self.clock = clock
        self.registry = registry or SkillRegistry()
        self.enable_exact_eval = bool(enable_exact_eval)
        self.memory_factory = memory_factory or SolveMemory
        self.host_context = host_context
        self.claim_executor = claim_executor

    def solve(self, problem: str, problem_type: str) -> RelayResult:
        problem_text = problem if isinstance(problem, str) else str(problem)
        memory = self.memory_factory()
        memory.answer_type = problem_type
        memory.remaining_calls = 5
        memory.remaining_stage_tokens = {
            stage: tokens for stage, tokens in zip(
                ("analyze", "fork_b", "fork_c", "synthesize", "finish"), STAGE_TOKEN_SEQUENCE
            )
        }
        trace: list[dict[str, Any]] = []
        if self.host_context is not None:
            intake_event = self.host_context.trace_event()
            self._event(
                trace,
                memory,
                intake_event["stage"],
                intake_event["status"],
                profile=intake_event["profile"],
                obligation_count=intake_event["obligation_count"],
                obligation_truncated=intake_event["obligation_truncated"],
                metadata_rejections=intake_event["metadata_rejections"],
            )
        started = self.clock()
        if problem_type == "calculation" and match_simple_arithmetic_expression(problem_text) is not None:
            response = self._call(memory, trace, "l0", "直接计算并只输出 FINAL: <答案>。", problem_text, 0.6, L0_TOKEN_SEQUENCE[0], started)
            final = self._extract_final(response)
            return self._result(memory, trace, final, "l0_final" if final != "UNKNOWN" else "unknown")

        analysis_user = f"原题：\n{problem_text}\n\n{self.registry.catalog_text()}"
        if self.host_context is not None:
            analysis_user += "\n\n" + self.host_context.prompt_hints()
        response_a = self._call(memory, trace, "analyze", ANALYZE_PROMPT,
                                analysis_user, 0.2, 2048, started)
        skill_name, applicability = self._ingest_analysis(response_a, memory)
        skill: SkillMetadata | None = None
        skill_body = ""
        if skill_name and applicability:
            skill, skill_body = self.registry.load_body(skill_name)
            if skill and skill_body:
                memory.mark_loaded_skill(skill.name, skill.content_hash)
            else:
                skill_name, skill_body = "", ""
        analysis_lines = [line.strip() for line in (response_a or "").splitlines() if line.strip()]
        analysis_parse_ok = bool(
            len(analysis_lines) >= 2
            and re.match(r"(?i)^SKILL_CHOICE\s*[:：]", analysis_lines[0])
            and re.match(r"(?i)^APPLICABILITY\s*[:：]", analysis_lines[1])
        )
        raw_applicability = _marker_value(response_a, "APPLICABILITY").strip().casefold()
        applicability_diag = raw_applicability if raw_applicability in {"yes", "no"} else "unknown"
        self._event(
            trace,
            memory,
            "route",
            "ok" if skill_name else "none",
            skill_name=skill_name or "NONE",
            skill_choice_parsed=analysis_parse_ok,
            applicability=applicability_diag,
        )

        response_b = self._call(memory, trace, "fork_b", FREE_BRANCH_PROMPT,
                                self._branch_user(problem_text, memory, "B", self.host_context), 0.6, 2048, started)
        packet_b = _parse_branch_packet(response_b or "", "B")
        for claim_id, content in packet_b.claims:
            memory.add_claim(claim_id, content, "B")
        if packet_b.candidate:
            memory.add_candidate("B", packet_b.candidate, [cid for cid, _ in packet_b.claims])
        if packet_b.open_text:
            memory.open_obligations.append(_clip(f"B: {packet_b.open_text}", 500))

        skill_context = skill_body if skill_body else "NONE（没有加载 Skill 正文；按互补自由求解）"
        c_user = self._branch_user(problem_text, memory, "C", self.host_context) + (
            f"\n\n宿主加载的 Skill：{skill_name or 'NONE'}\n"
            f"Skill 正文（仅此一份）：\n{skill_context}"
        )
        if self.claim_executor is not None:
            c_user += (
                "\n\n可选 Claim DSL：每行一个 JSON。"
                "CLAIM_DSL 登记局部命题；VERIFY_DSL 只引用 claim_id，不得改写表达式。"
            )
        response_c = self._call(memory, trace, "fork_c", SKILL_BRANCH_PROMPT,
                                c_user, 0.6, 2048, started)
        packet_c = _parse_branch_packet(response_c or "", "C")
        for claim_id, content in packet_c.claims:
            if not memory.add_claim(claim_id, content, "C"):
                # A malformed duplicate cannot overwrite B's source record.
                continue
        if packet_c.candidate:
            memory.add_candidate("C", packet_c.candidate, [cid for cid, _ in packet_c.claims])
        if packet_c.open_text:
            memory.open_obligations.append(_clip(f"C: {packet_c.open_text}", 500))
        if self.claim_executor is not None:
            for extra in self.claim_executor.verify("C", response_c or "", memory):
                self._event(
                    trace,
                    memory,
                    extra.get("stage") or "tool_claim_dsl",
                    extra.get("status") or "UNKNOWN",
                    evidence_id=extra.get("evidence_id") or "",
                    claim_id=extra.get("claim_id") or "UNKNOWN",
                    error=extra.get("error") or "none",
                    execution_status=extra.get("execution_status") or "unknown",
                    claim_known=bool(extra.get("claim_known")),
                    binding_ok=bool(extra.get("binding_ok")),
                    tool_request_valid=bool(extra.get("tool_request_valid")),
                )

        # A route is active only after an applicable, registered Skill body
        # was actually loaded.  A's explicit NO/unknown applicability must
        # never enable host tools merely because it named a Skill.
        skill_route_active = bool(skill_name and skill_body and memory.loaded_skills)
        if self.enable_exact_eval and skill_name == "exact-evaluation" and skill_route_active:
            for index, request in enumerate(packet_c.tool_requests[:MAX_TOOL_REQUESTS]):
                evidence = evaluate_exact_request(request, index)
                claim_id = str(evidence.get("claim_id") or "")
                claim = next((item for item in memory.claims if item.id == claim_id), None)
                known_claim = bool(claim_id and claim is not None)
                expression = str(evidence.get("checked_expression") or "")
                expected = str(evidence.get("checked_expected") or "")
                if known_claim and evidence.get("status") in {"EXACT", "REFUTED"} and not _claim_binds_tool(
                    claim, expression, str(evidence.get("result") or ""), expected
                ):
                    evidence["status"] = "UNKNOWN"
                    evidence["execution_status"] = "rejected"
                    evidence["error"] = "claim_binding"
                if claim_id and not known_claim:
                    evidence["status"] = "UNKNOWN"
                    evidence["execution_status"] = "rejected"
                    evidence["error"] = "unknown_claim"
                evidence_id = str(evidence.get("evidence_id") or f"T{index + 1}")
                # An evidence record with an unknown claim id is not allowed
                # into D/E state; the bounded trace still records that the
                # request was rejected.
                if known_claim:
                    memory.add_evidence(
                        evidence_id,
                        str(evidence.get("source") or "exact-evaluation"),
                        str(evidence.get("status") or "UNKNOWN"),
                        str(evidence.get("scope") or ""),
                        str(evidence.get("result") or ""),
                        evidence.get("assumptions") or [],
                        claim_id,
                        checked_expression=expression,
                        checked_expected=expected,
                    )
                binding_ok: bool | None = None
                if known_claim and expression:
                    binding_ok = _claim_binds_tool(
                        claim, expression, str(evidence.get("result") or ""), expected
                    )
                self._event(
                    trace,
                    memory,
                    "tool_exact_eval",
                    str(evidence.get("status") or "UNKNOWN"),
                    evidence_id=evidence_id,
                    claim_id=_trace_claim_id(claim_id, known=known_claim),
                    error=_clip(str(evidence.get("error") or ""), 80) or "none",
                    execution_status=str(evidence.get("execution_status") or "unknown"),
                    claim_known=known_claim,
                    binding_ok=binding_ok if binding_ok is not None else False,
                    tool_request_valid=not bool(evidence.get("error")),
                )

        d_context = memory.render_for_d(MAX_PACKET_CHARS)
        d_user = f"原题：\n{problem_text}\n\n结构化状态：\n{d_context}"
        if self.host_context is not None:
            d_user += "\n\n" + self.host_context.prompt_hints()
        response_d = self._call(memory, trace, "synthesize", EVIDENCE_SYNTHESIS_PROMPT,
                                d_user, 0.2, 8192, started)
        d_protocol_ok = False
        if response_d:
            d_summary = _parse_d_packet(response_d, memory)
            d_protocol_ok = bool(d_summary.get("protocol_ok"))
            consumed_evidence_ids = {
                evidence_id
                for claim in memory.claims
                if claim.status in {"SUPPORTED", "REFUTED"}
                for evidence_id in claim.evidence_ids
            }
            for event in trace:
                if event.get("stage") == "tool_exact_eval":
                    event["evidence_consumed"] = event.get("evidence_id") in consumed_evidence_ids
            if not d_protocol_ok:
                self._fallback_synthesis(memory)
                self._event(
                    trace,
                    memory,
                    "synthesize",
                    "protocol_failed",
                    error_category="invalid_response",
                    protocol_error=_clip(str(d_summary.get("protocol_error") or "invalid_response"), 240),
                )
        else:
            d_summary = self._fallback_synthesis(memory)
            for event in trace:
                if event.get("stage") == "tool_exact_eval":
                    event["evidence_consumed"] = False
        if response_d is None:
            self._event(trace, memory, "synthesize", "protocol_failed", error_category="empty_response")

        e_context = memory.render_for_e(MAX_PACKET_CHARS)
        if not d_protocol_ok:
            e_context = "D_PROTOCOL: INVALID; final response will be rejected.\n" + e_context
        e_user = f"原题：\n{problem_text}\n\nD/E 证据状态：\n{e_context}"
        if self.host_context is not None:
            e_user += "\n\n" + self.host_context.prompt_hints()
        response_e = self._call(memory, trace, "finish", FINISH_PROMPT,
                                e_user, 0.0, 4096, started)
        final = self._extract_final(response_e) if d_protocol_ok else "UNKNOWN"
        final, gate_source = self._apply_candidate_gate(memory, final, d_protocol_ok, trace)
        source = gate_source if final != "UNKNOWN" else "unknown"
        return self._result(memory, trace, final, source, d_summary=d_summary)

    @staticmethod
    def _branch_user(
        problem: str,
        memory: SolveMemory,
        branch: str,
        host_context: HostLoopContext | None = None,
    ) -> str:
        analysis = (
            f"GOAL: {memory.goal}\nANSWER_TYPE: {memory.answer_type}\n"
            f"CONSTRAINTS: {' | '.join(memory.constraints[:6])}"
        )
        text = f"原题：\n{problem}\n\nA 分析摘要：\n{_clip(analysis, 1_500)}\n\n当前分支：{branch}"
        if host_context is not None:
            text += "\n\n" + host_context.prompt_hints()
        return text

    def _ingest_analysis(self, response: str | None, memory: SolveMemory) -> tuple[str, bool]:
        lines = [line.strip() for line in (response or "").splitlines() if line.strip()]
        first_ok = bool(lines and re.match(r"(?i)^SKILL_CHOICE\s*[:：]", lines[0]))
        second_ok = bool(len(lines) > 1 and re.match(r"(?i)^APPLICABILITY\s*[:：]", lines[1]))
        skill_choice = _marker_value(response, "SKILL_CHOICE") if first_ok and second_ok else ""
        applicability_value = _marker_value(response, "APPLICABILITY").strip().casefold() if first_ok and second_ok else ""
        # Keep the router binary: only a literal YES activates a Skill.  NO,
        # explanations, MAYBE, and unknown values all fall back to NONE.
        applicability = applicability_value == "yes"
        if "|" in skill_choice:
            skill_choice = skill_choice.split("|", 1)[0].strip()
        if skill_choice.casefold() == "none":
            skill_choice = ""
        if not skill_choice or not applicability or self.registry.get(skill_choice) is None:
            skill_choice = ""
            applicability = False
        memory.goal = _clip(_marker_value(response, "GOAL"), 700)
        memory.answer_type = _clip(_marker_value(response, "ANSWER_TYPE") or memory.answer_type, 180)
        constraints = _marker_value(response, "CONSTRAINTS")
        memory.constraints = [_clip(x.strip(), 240) for x in re.split(r"[|；;\n]", constraints) if x.strip()][:8]
        return skill_choice, applicability

    @staticmethod
    def _fallback_synthesis(memory: SolveMemory) -> dict[str, Any]:
        primary = "B" if any(c.source == "B" for c in memory.claims) else ("C" if memory.claims else "")
        unresolved = [c.id for c in memory.claims]
        memory.set_synthesis(primary_branch=primary, primary_reason="D 响应不可用；保留已解析命题为未决", unresolved=unresolved)
        return {"primary": primary, "supported": [], "auxiliary": [], "refuted": [], "unresolved": unresolved}

    @staticmethod
    def _extract_final(response: str | None) -> str:
        text = response or ""
        matches = list(_FINAL_RE.finditer(text))
        # A finish packet has one authoritative marker and it must terminate
        # the non-empty response.  Duplicate markers include explicit
        # withdrawals and are therefore fail-closed.
        if len(matches) != 1:
            return "UNKNOWN"
        if text[matches[0].end():].strip():
            return "UNKNOWN"
        value = matches[0].group(1).strip().strip("`").strip()
        if re.fullmatch(r"(?i)unknown[.。!?！？]?", value):
            return "UNKNOWN"
        if _is_placeholder(value) or not value or not _closed_final(value):
            return "UNKNOWN"
        return _clip(value, 2_000)

    @staticmethod
    def _apply_candidate_gate(
        memory: SolveMemory,
        final: str,
        d_protocol_ok: bool,
        trace: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Bind E's answer to a host-owned, non-refuted candidate.

        Parsing ``FINAL`` is only an output-hygiene check.  The semantic gate is
        deliberately separate: a well-formed but novel value (for example
        ``FINAL: 99`` when every parsed candidate is ``3``) is rejected.
        """
        candidates = memory.candidate_rows_for_e() if d_protocol_ok else []
        if final == "UNKNOWN":
            reason = "no_final" if d_protocol_ok else "d_protocol_invalid"
            ForkEvidenceSynthesizeFinishRelay._event(
                trace, memory, "candidate_gate", "rejected",
                candidate_count=len(memory.candidates), eligible_count=len(candidates),
                candidate_gate=reason,
            )
            return "UNKNOWN", "unknown"
        for candidate_id, candidate in candidates:
            relation = _candidate_answer_equivalence(final, candidate.answer)
            if relation == "EQUIVALENT":
                ForkEvidenceSynthesizeFinishRelay._event(
                    trace, memory, "candidate_gate", "accepted",
                    candidate_count=len(memory.candidates), eligible_count=len(candidates),
                    matched_candidate_id=candidate_id,
                    candidate_gate="equivalent",
                )
                return final, "finish_final_candidate"
        ForkEvidenceSynthesizeFinishRelay._event(
            trace, memory, "candidate_gate", "rejected",
            candidate_count=len(memory.candidates), eligible_count=len(candidates),
            candidate_gate="not_in_candidate_set",
        )
        return "UNKNOWN", "unknown"

    def _call(
        self,
        memory: SolveMemory,
        trace: list[dict[str, Any]],
        stage: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        started: float,
    ) -> str | None:
        if memory.remaining_calls <= 0:
            self._event(trace, memory, stage, "skipped", error_category="call_budget")
            return None
        elapsed = self.clock() - started
        if elapsed >= HARD_DEADLINE_SECONDS_FESF:
            self._event(trace, memory, stage, "skipped", error_category="hard_deadline")
            return None
        if elapsed >= SOFT_DEADLINE_SECONDS:
            self._event(trace, memory, stage, "skipped", error_category="soft_deadline")
            return None
        memory.consume_call(stage, max_tokens)
        try:
            response = self.client.chat(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            self._event(trace, memory, stage, "failed", error_category=_error_category(exc))
            return None
        if not isinstance(response, str) or not response.strip():
            self._event(trace, memory, stage, "failed", error_category="invalid_response")
            return None
        self._event(trace, memory, stage, "ok", packet_present=True)
        return response.strip()

    @staticmethod
    def _event(trace: list[dict[str, Any]], memory: SolveMemory, stage: str, status: str, **extra: Any) -> None:
        event = {
            "method": METHOD_ID,
            "stage": stage,
            "status": status,
            "model_calls": 5 - memory.remaining_calls,
            "max_tokens": memory.remaining_stage_tokens.get(stage, 0),
        }
        allowed = {
            "packet_present", "error_category", "skill_name", "evidence_id", "claim_id",
            "fallback_source", "final_present", "selected_branch", "supported_count",
            "auxiliary_count", "refuted_count", "unresolved_count", "skill_loaded",
            "skill_choice_parsed", "applicability", "error", "execution_status",
            "claim_known", "binding_ok", "tool_request_valid", "evidence_consumed",
            "protocol_error",
            "candidate_gate", "candidate_count", "eligible_count", "matched_candidate_id",
            "profile", "obligation_count", "obligation_truncated", "metadata_rejections",
        }
        event.update({key: value for key, value in extra.items() if key in allowed})
        trace.append(event)

    def _result(
        self,
        memory: SolveMemory,
        trace: list[dict[str, Any]],
        final: str,
        source: str,
        *,
        d_summary: dict[str, Any] | None = None,
    ) -> RelayResult:
        final = final.strip() if isinstance(final, str) and final.strip() else "UNKNOWN"
        summary = d_summary or {
            "supported": memory.supported_claim_ids,
            "auxiliary": memory.auxiliary_claim_ids,
            "refuted": memory.refuted_claim_ids,
            "unresolved": memory.unresolved_claim_ids,
        }
        self._event(
            trace,
            memory,
            "finalize",
            "ok" if final != "UNKNOWN" else "unknown",
            fallback_source=source,
            final_present=final != "UNKNOWN",
            selected_branch=memory.selected_branch or "UNKNOWN",
            supported_count=len(summary.get("supported", [])),
            auxiliary_count=len(summary.get("auxiliary", [])),
            refuted_count=len(summary.get("refuted", [])),
            unresolved_count=len(summary.get("unresolved", [])),
            skill_loaded=bool(memory.loaded_skills),
        )
        return RelayResult(final_response=final, extracted_answer=final if final != "UNKNOWN" else "", trace=trace)


__all__ = [
    "ForkEvidenceSynthesizeFinishRelay",
    "SkillRegistry",
    "SkillMetadata",
    "evaluate_exact_request",
    "METHOD_ID",
    "STAGE_TOKEN_SEQUENCE",
    "L0_TOKEN_SEQUENCE",
    "SOFT_DEADLINE_SECONDS",
    "HARD_DEADLINE_SECONDS_FESF",
]
