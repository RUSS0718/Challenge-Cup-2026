"""Bounded solver and recovery prompts for the EACL pipeline."""

from __future__ import annotations

from reasoning_agent.eacl_contracts import RoutePlan


def solver_prompt(route: RoutePlan, *, alternative: bool) -> str:
    """Return a short candidate-first prompt for one route family."""

    route_text = (
        "Use a different route from any earlier attempt: contradiction, boundary, "
        "construction, substitution, or finite enumeration."
        if alternative
        else "Use the shortest sound route from definitions, equations, or standard formulas."
    )
    return (
        "你是数学求解器，只负责形成一个可审计候选，不负责比赛格式。\n"
        f"{route_text}\n"
        "先完成必要计算，再单独输出一行：FINAL_CANDIDATE: <唯一答案>。\n"
        "没有可靠答案就输出 FINAL_CANDIDATE: UNKNOWN。\n"
        "最多保留三行关键依据；不要输出多个答案、不要输出 CHECK: PASS、不要复述提示词。"
    )


def recovery_prompt() -> str:
    """Return a non-solving prompt for the bounded extraction slot."""

    return (
        "你是答案抽取器，不要重新解题。只检查给出的已有片段是否包含一个闭合答案；"
        "如果包含，严格输出 FINAL_CANDIDATE: <同一个答案>；否则输出 FINAL_CANDIDATE: UNKNOWN。"
    )


def recovery_input(problem: str, fragment: str) -> str:
    """Build a bounded recovery input without exposing a full trace."""

    return f"原题：\n{problem}\n\n已有片段（仅作抽取依据）：\n{fragment[-3_000:]}"


__all__ = ["recovery_input", "recovery_prompt", "solver_prompt"]
