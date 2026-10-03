"""Gold-free task and candidate contracts for bounded answer recovery.

The contract describes what a solver may return; it never contains a gold
answer and never decides mathematical correctness.  Parsers and validators
consume these immutable objects at the host boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class AnswerType(str, Enum):
    """Supported answer shapes understood by the host contract."""

    INTEGER = "integer"
    RATIONAL = "rational"
    EXPRESSION = "expression"
    TUPLE = "tuple"
    SET = "set"
    CHOICE = "choice"
    PROOF = "proof"
    UNKNOWN = "unknown"


class Completeness(str, Enum):
    """Candidate closure states used by recovery decisions."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Verification(str, Enum):
    """Host verification states; UNKNOWN is fail-closed."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaskContract:
    """Describe output requirements inferred from a problem statement."""

    answer_type: AnswerType = AnswerType.UNKNOWN
    required_fields: tuple[str, ...] = ()
    allowed_equivalence: tuple[str, ...] = ("surface",)
    completeness_rule: str = "one_closed_candidate"
    rejection_rule: str = "placeholder_or_conflict"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe contract representation."""
        return {
            "answer_type": self.answer_type.value,
            "required_fields": list(self.required_fields),
            "allowed_equivalence": list(self.allowed_equivalence),
            "completeness_rule": self.completeness_rule,
            "rejection_rule": self.rejection_rule,
        }


@dataclass(frozen=True)
class Candidate:
    """Store one host-extracted answer independently from final text."""

    value: str
    answer_type: AnswerType
    source: str
    completeness: Completeness = Completeness.COMPLETE
    confidence: str = "unverified"
    reasoning_status: str = "unknown"
    verification: Verification = Verification.UNKNOWN
    raw_span_hash: str = ""
    rejection_reason: str = ""
    canonical_value: str = ""

    @property
    def accepted(self) -> bool:
        """Return true only for non-empty complete candidates without rejection."""
        return bool(self.value.strip()) and self.completeness == Completeness.COMPLETE and not self.rejection_reason

    def as_dict(self) -> dict[str, Any]:
        """Return a compact diagnostic representation without raw response text."""
        return {
            "value": self.value,
            "answer_type": self.answer_type.value,
            "source": self.source,
            "completeness": self.completeness.value,
            "confidence": self.confidence,
            "reasoning_status": self.reasoning_status,
            "verification": self.verification.value,
            "raw_span_hash": self.raw_span_hash,
            "rejection_reason": self.rejection_reason,
            "canonical_value": self.canonical_value,
        }


def infer_task_contract(problem: str) -> TaskContract:
    """Infer a conservative contract from generic wording, without gold data."""
    text = str(problem or "")
    if re.search(r"证明|求证|\bprove\b|\bshow\s+that\b", text, re.I):
        answer_type = AnswerType.PROOF
        fields = ("proof",)
    elif re.search(r"选择|选项|\bchoose\b|\bselect\b", text, re.I):
        answer_type = AnswerType.CHOICE
        fields = ("choice",)
    elif re.search(r"所有解|解集|所有可能|solution\s+set|all\s+solutions", text, re.I):
        answer_type = AnswerType.SET
        fields = ("value",)
    elif re.search(r"向量|元组|坐标|vector|tuple|coordinates", text, re.I):
        answer_type = AnswerType.TUPLE
        fields = ("value",)
    elif re.search(r"整数|integer|余数|remainder", text, re.I):
        answer_type = AnswerType.INTEGER
        fields = ("value",)
    elif re.search(r"分数|有理数|rational|fraction", text, re.I):
        answer_type = AnswerType.RATIONAL
        fields = ("value",)
    else:
        answer_type = AnswerType.EXPRESSION if re.search(r"表达式|expression|函数|function", text, re.I) else AnswerType.UNKNOWN
        fields = ("value",)
    return TaskContract(answer_type=answer_type, required_fields=fields)


__all__ = ["AnswerType", "Candidate", "Completeness", "TaskContract", "Verification", "infer_task_contract"]
