"""Offline semantic reference-example RAG adapted from intern1's runtime."""

from __future__ import annotations

import re
from typing import Any

from reference_reasoning_runtime.retrieval import DatabaseClient, normalize, select_runtime_references


HIGH_SIMILARITY = 0.90
MEDIUM_SIMILARITY = 0.65
QUERY_CANDIDATES = 24


def _clip(value: Any, limit: int) -> str:
    return str(value or "")[: max(0, int(limit))]


def _number_diff(problem: str, example: str) -> str:
    ours = list(dict.fromkeys(re.findall(r"(?<![A-Za-z_])\d{2,}(?![A-Za-z_])", problem or "")))
    theirs = list(dict.fromkeys(re.findall(r"(?<![A-Za-z_])\d{2,}(?![A-Za-z_])", example or "")))
    only_ours = [item for item in ours if item not in theirs][:6]
    only_theirs = [item for item in theirs if item not in ours][:6]
    if not only_ours and not only_theirs:
        return ""
    parts = []
    if only_ours:
        parts.append(f"本题独有参数 {only_ours}")
    if only_theirs:
        parts.append(f"示例独有参数 {only_theirs}")
    return "⚠ 参数不同，不能直接搬用示例结论：" + "；".join(parts) + "。\n"


def render_reference_context(problem: str, references: list[dict[str, Any]], max_chars: int = 4000) -> str:
    """Render selected examples as bounded method hints, never as a direct answer."""
    if not references or max_chars <= 0:
        return ""
    top = references[0]
    try:
        similarity = float(top.get("similarity") or 0.0)
    except (TypeError, ValueError):
        similarity = 0.0
    detail_limit = 3000 if similarity >= HIGH_SIMILARITY else 1200
    parts = [
        "\n\n相似题参考（向量近邻，不是本题答案；只借鉴方法，必须按原题重新推导）：\n",
        "先核对参数、边界、变量角色和目标；任一条件不同，示例结论不可直接迁移。\n",
    ]
    for index, reference in enumerate(references[:2], start=1):
        example_problem = _clip(reference.get("problem"), 3500 if index == 1 else 1000)
        solution_limit = detail_limit if index == 1 else 500
        parts.append(
            f"\n示例 {index}（相似度 {float(reference.get('similarity') or 0.0):.3f}，仅供参考）\n"
            + _number_diff(problem, example_problem)
            + f"题目：{example_problem}\n"
            + f"解法提示：{_clip(reference.get('solution'), solution_limit)}\n"
        )
    return "".join(parts)[: int(max_chars)]


class ReferenceRagRetriever:
    """Compatibility seam for the current candidate-generation path.

    The index and embedding model are loaded lazily by ``DatabaseClient``.
    Retrieval failures return no context so the existing solver remains usable.
    """

    def __init__(self, database: Any | None = None, *, query_candidates: int = QUERY_CANDIDATES) -> None:
        self.database = database if database is not None else DatabaseClient()
        self.query_candidates = max(2, min(100, int(query_candidates)))

    def search(self, query: str, top_k: int = 2) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip() or top_k <= 0:
            return []
        try:
            rows = self.database.query(query, top_k=self.query_candidates)
            rows = [
                row for row in rows
                if normalize(row.get("problem", "")) != normalize(query)
            ]
            valid, _ = select_runtime_references(rows)
        except Exception:
            return []
        if not valid:
            return []
        try:
            top_similarity = float(valid[0].get("similarity") or 0.0)
        except (TypeError, ValueError):
            return []
        if top_similarity < MEDIUM_SIMILARITY:
            return []
        return [dict(row) for row in valid[: max(1, int(top_k))]]


__all__ = [
    "HIGH_SIMILARITY",
    "MEDIUM_SIMILARITY",
    "ReferenceRagRetriever",
    "render_reference_context",
]
