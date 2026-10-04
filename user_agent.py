"""Official competition facade for the bounded EACL reasoning agent.

The public platform imports only :class:`ReasoningAgent` and calls
``solve(problem, metadata)``.  Routing, candidate parsing, verification, and
serialization live in ``reasoning_agent``; this file intentionally contains no
legacy solver or retrieval implementation.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.answer_contract import AnswerType, TaskContract, infer_task_contract
from reasoning_agent.candidate_canonicalizer import canonicalize, parse_response
from reasoning_agent.eacl_agent import EACLReasoningAgent
from reasoning_agent.eacl_contracts import EACLConfig
from reasoning_agent.harness_contracts import value_equivalence


EACL_SUBMISSION_MODE = "grh-eacl-v1"
SUBMISSION_MODE = EACL_SUBMISSION_MODE
EACL_SUBMISSION_CONFIG = EACLConfig()
SUBMISSION_CONFIG = EACL_SUBMISSION_CONFIG
AgentConfig = EACLConfig

POLICY_PROMPT = (
    "你是严谨的数学推理智能体。解决题目并形成唯一候选。"
    "最后明确输出 FINAL_CANDIDATE: <答案>。无法确认时输出 UNKNOWN。"
)
ANSWER_FIRST_POLICY_PROMPT = POLICY_PROMPT
ANSWER_ONLY_POLICY_PROMPT = POLICY_PROMPT


class ReasoningAgent(EACLReasoningAgent):
    """Expose the competition ``solve`` contract on the EACL control plane."""

    def __init__(self, client: Any, config: EACLConfig | None = None, **_: Any) -> None:
        """Bind a bounded EACL configuration; reject legacy retrieval hooks."""

        super().__init__(client, config=config or EACL_SUBMISSION_CONFIG)


def build_submission_config(mode: str = SUBMISSION_MODE) -> EACLConfig:
    """Return the only active submission configuration."""

    if str(mode).strip().lower() not in {EACL_SUBMISSION_MODE, "eacl", "submission"}:
        raise ValueError(f"unknown_submission_mode:{mode!r}; use {EACL_SUBMISSION_MODE}")
    return EACLConfig()


def classify_problem_type(problem: str) -> str:
    """Return the contract answer type used by the host router."""

    return infer_task_contract(problem).answer_type.value


def extract_final_answer(response: str, problem: str = "") -> str:
    """Extract one canonical candidate from a model response."""

    contract = infer_task_contract(problem)
    parsed = parse_response(response, contract)
    return parsed.candidates[0].canonical_value if parsed.complete else ""


def extract_answer_first(response: str, problem: str = "") -> str:
    """Compatibility alias for the contract parser."""

    return extract_final_answer(response, problem)


def extract_numeric_answer(response: str, problem: str = "") -> str:
    """Extract a candidate only when its shape is numeric or explicitly typed."""

    answer = extract_final_answer(response, problem)
    return answer if answer and any(char.isdigit() for char in answer) else ""


def normalize_answer(answer: str) -> str:
    """Canonicalize a generic answer surface without changing ordering."""

    return canonicalize(answer, TaskContract(answer_type=AnswerType.UNKNOWN))


def answer_equivalence(left: str, right: str) -> str:
    """Compare two normalized answer surfaces using the shared host relation."""

    return value_equivalence(normalize_answer(left), normalize_answer(right))


def is_placeholder_answer(answer: str) -> bool:
    """Return whether a response contains no closed candidate."""

    return not bool(extract_final_answer(answer))


__all__ = [
    "AgentConfig",
    "ANSWER_FIRST_POLICY_PROMPT",
    "ANSWER_ONLY_POLICY_PROMPT",
    "EACL_SUBMISSION_CONFIG",
    "EACL_SUBMISSION_MODE",
    "POLICY_PROMPT",
    "ReasoningAgent",
    "SUBMISSION_CONFIG",
    "SUBMISSION_MODE",
    "answer_equivalence",
    "build_submission_config",
    "classify_problem_type",
    "extract_answer_first",
    "extract_final_answer",
    "extract_numeric_answer",
    "is_placeholder_answer",
    "normalize_answer",
]
