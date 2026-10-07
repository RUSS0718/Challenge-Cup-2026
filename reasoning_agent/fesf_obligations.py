"""A bounded, rule-based obligation extractor for the experimental Host Loop.

This is intentionally *not* a general semantic parser.  It recognises a small
set of explicit markers and mathematical completeness signals that can be
checked deterministically.  Unknown language is left alone rather than being
converted into a guessed obligation.  Symbolic denominators stay ``OPEN``:
the extractor may remind the host that a domain check is needed, but it
never claims the domain is already satisfied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .host_intake import normalize_problem


MAX_OBLIGATION_TEXT_CHARS = 12_000
MAX_OBLIGATION_ITEMS = 8
MAX_OBLIGATION_FRAGMENT_CHARS = 360

_EXPLICIT_RE = re.compile(
    r"(?im)^\s*(?:OPEN|OBLIGATION|UNRESOLVED|RISK|未决义务|待检查|风险)\s*[:：]\s*(.*?)\s*$"
)
# A slash is a symbolic denominator only when the left token is already
# mathematical: a number, a closing parenthesis, or a short variable.  Natural
# language units such as ``km/h`` and English pairs such as ``and/or`` are
# therefore left alone instead of being guessed into a new obligation.
_DENOMINATOR_RE = re.compile(
    r"(?P<left>\d+|[A-Za-z][A-Za-z0-9_]*|\))\s*(?:/|÷)\s*"
    r"(?:\((?P<paren>[A-Za-z][A-Za-z0-9_]*)\)|(?P<bare>[A-Za-z][A-Za-z0-9_]*))"
    r"(?![A-Za-z0-9_(])"
)
_MATH_VARIABLE_RE = re.compile(r"^[A-Za-z](?:_[A-Za-z0-9]+|[0-9]*)?$")
_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "PROOF_COMPLETENESS",
        re.compile(r"(?:证明|求证|prove|show\s+that)", re.I),
        "证明链必须覆盖题目要求的结论",
    ),
    (
        "UNIVERSAL_COVERAGE",
        re.compile(r"(?:任意|所有|全部|每个|任何|∀|for\s+all|for\s+every)", re.I),
        "需要覆盖全称条件，有限样本不能单独证明全称命题",
    ),
    (
        "EXISTENCE_WITNESS",
        re.compile(r"(?:存在|至少一个|there\s+exists)", re.I),
        "需要给出存在性见证或构造",
    ),
    (
        "FINITE_COVERAGE",
        re.compile(r"(?:枚举|逐一|分类讨论|穷举|case\s+analysis|enumerate)", re.I),
        "需要说明有限情形是否已经完整覆盖",
    ),
    (
        "SUBSTITUTION_CHECK",
        re.compile(r"(?:代回|代入|检验|核对|verify|check\s+by\s+substitution)", re.I),
        "需要代回原条件检查候选",
    ),
    (
        "DOMAIN_SPECIFICATION",
        re.compile(r"(?:定义域|取值范围|范围|非零|domain|range)", re.I),
        "需要明确变量定义域或边界条件",
    ),
    (
        "ENUMERATE_ALL_SOLUTIONS",
        re.compile(r"(?:全部实根|所有解|全部解|all\s+roots|all\s+solutions)", re.I),
        "需要确认没有遗漏解或重复解",
    ),
)


@dataclass(frozen=True)
class Obligation:
    """One bounded obligation emitted by a deterministic rule."""

    id: str
    kind: str
    text: str
    source: str
    state: str = "OPEN"
    rule: str = ""


@dataclass(frozen=True)
class ObligationExtraction:
    """Bounded extraction result; no raw model response is retained."""

    obligations: tuple[Obligation, ...]
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligations": [asdict(item) for item in self.obligations],
            "truncated": self.truncated,
        }


def _fragment(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:MAX_OBLIGATION_FRAGMENT_CHARS]


def extract_bounded_obligations(
    text: str,
    *,
    source: str = "problem",
    max_items: int = MAX_OBLIGATION_ITEMS,
) -> ObligationExtraction:
    """Extract only explicit/completeness obligations from bounded text.

    The order is stable: explicit ``OPEN`` markers, denominator-domain checks,
    then fixed keyword rules.  A rule never claims that a proof is complete;
    it only records what still needs checking.
    """

    normalized = normalize_problem(text, max_chars=MAX_OBLIGATION_TEXT_CHARS)
    source_text = _fragment(str(source or "problem")) or "problem"
    limit = max(0, min(int(max_items), MAX_OBLIGATION_ITEMS))
    found: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, state: str = "OPEN", rule: str = "") -> None:
        compact = _fragment(value)
        if not compact or (kind, compact.casefold()) in seen:
            return
        seen.add((kind, compact.casefold()))
        found.append((kind, compact, state, rule))

    for match in _EXPLICIT_RE.finditer(normalized):
        add("OPEN_ITEM", match.group(1), rule="explicit_marker")

    denominators = []
    for match in _DENOMINATOR_RE.finditer(normalized):
        left = match.group("left")
        name = match.group("paren") or match.group("bare")
        if not name or not _MATH_VARIABLE_RE.fullmatch(name):
            continue
        if "÷" not in match.group(0) and left != ")" and not left.isdigit() and not _MATH_VARIABLE_RE.fullmatch(left):
            continue
        if name.casefold() not in {item.casefold() for item in denominators}:
            denominators.append(name)
    for name in denominators:
        # Automatic COVERED was withdrawn after RETRY5.  A nearby ``x != 0``
        # string is not a domain proof, so every symbolic denominator stays OPEN
        # until a dedicated claim DSL can bind assumptions.
        add(
            "DOMAIN_CHECK",
            f"分母 {name} 必须满足 {name} != 0",
            "OPEN",
            rule="symbolic_denominator",
        )

    for kind, pattern, message in _RULES:
        if pattern.search(normalized):
            add(kind, message, rule="keyword_signal")

    truncated = len(found) > limit
    selected = found[:limit]
    return ObligationExtraction(
        obligations=tuple(
            Obligation(
                id=f"O{index}",
                kind=kind,
                text=value,
                source=source_text,
                state=state,
                rule=rule,
            )
            for index, (kind, value, state, rule) in enumerate(selected, start=1)
        ),
        truncated=truncated,
    )


__all__ = [
    "MAX_OBLIGATION_ITEMS",
    "Obligation",
    "ObligationExtraction",
    "extract_bounded_obligations",
]
