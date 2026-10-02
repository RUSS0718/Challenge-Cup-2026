"""Deterministic, answer-safe projection of Intern1's 18 subject manuals."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from reference_reasoning_runtime.full_skill_loader import SKILL_ROOT, categories
from reference_reasoning_runtime.skill_excerpt import (
    _MODULE_RE,
    _split_modules,
    select_skill_excerpt,
)


SUBJECT_TERMS: dict[str, tuple[str, ...]] = {
    "抽象代数": ("群", "环", "域", "同态", "同构", "理想", "Galois", "有限域", "Sylow"),
    "高等代数": ("矩阵", "行列式", "特征值", "线性空间", "二次型", "多项式", "对角化"),
    "离散数学": ("图论", "顶点", "边", "图", "组合", "递推", "生成函数", "布尔", "博弈"),
    "初等几何": ("三角形", "圆", "角", "平行", "垂直", "几何", "相切"),
    "复分析": ("复数", "复变", "全纯", "解析函数", "留数", "围道", "洛朗", "极点", "复积分"),
    "数值分析": ("数值", "插值", "误差", "迭代", "收敛阶", "Runge", "Euler", "求积"),
    "数学分析": ("极限", "连续", "导数", "微分", "积分", "级数", "一致收敛", "反函数", "实数"),
    "测度积分": ("测度", "可测", "勒贝格", "几乎处处", "控制收敛", "Fubini", "Tonelli"),
    "微分几何": ("曲率", "测地", "曲面", "基本形式", "联络", "黎曼", "Gauss"),
    "代数几何": ("代数簇", "概形", "射影簇", "理想层", "scheme", "variety"),
    "概率论": ("概率", "随机变量", "期望", "方差", "分布", "独立", "条件概率"),
    "随机过程": ("马尔可夫", "随机过程", "平稳", "布朗", "泊松过程", "鞅", "转移概率"),
    "统计推断": ("统计量", "置信区间", "假设检验", "似然", "无偏", "p值", "回归"),
    "线性回归": ("线性回归", "最小二乘", "残差", "岭回归", "异方差", "回归系数"),
    "常微分方程": ("常微分方程", "初值问题", "通解", "特征方程", "稳定性", "Laplace"),
    "偏微分方程": ("偏微分方程", "热方程", "波动方程", "Laplace方程", "弱解", "PDE"),
    "拓扑学": ("拓扑", "同胚", "紧致", "连通", "开集", "闭集", "基本群"),
    "运筹学": ("线性规划", "单纯形", "对偶", "可行域", "网络流", "KKT"),
    "非基础及进阶课程": ("构造", "反例", "不变量", "整除", "竞赛", "存在性"),
}

_UNSAFE_MODULE_MARKERS = (
    "解法直达",
    "判分口径",
    "答案集",
    "官方答案",
    "本题核定结论",
    "题面校对口径",
)


def classify_skill_subject(problem: str) -> dict[str, Any]:
    text = str(problem or "").casefold()
    scored = []
    for category in categories():
        terms = SUBJECT_TERMS.get(category, ())
        matched = [term for term in terms if term.casefold() in text]
        scored.append((len(matched), category, matched))
    scored.sort(key=lambda item: (-item[0], item[1]))
    score, category, matched = scored[0]
    return {
        "category": category if score else "",
        "score": score,
        "matched_terms": matched,
        "candidates": [item[1] for item in scored if item[0]][:3],
    }


def _safe_document(document: str) -> str:
    preamble, modules = _split_modules(document, _MODULE_RE)
    if not modules:
        return "\n".join(
            line for line in document.splitlines()
            if not any(marker in line for marker in _UNSAFE_MODULE_MARKERS)
        )
    kept = []
    for module in modules:
        heading = module.split("\n", 1)[0]
        if any(marker in heading or marker in module for marker in _UNSAFE_MODULE_MARKERS):
            continue
        module = re.sub(r"(?m)^.*对应习题.*$\n?", "", module)
        module = re.sub(r"(?m)^\s*[-*]?\s*idx\s+\d+.*$\n?", "", module)
        kept.append(module)
    return preamble + "".join(kept)


@lru_cache(maxsize=1)
def _safe_documents() -> dict[str, str]:
    documents = {}
    for category in categories():
        paths = list((SKILL_ROOT / category).glob("*skill.md"))
        if paths:
            documents[category] = _safe_document(paths[0].read_text(encoding="utf-8"))
    return documents


def select_reference_skill_context(
    problem: str,
    *,
    limit: int = 3200,
    suppress: bool = False,
) -> tuple[str, dict[str, Any]]:
    route = classify_skill_subject(problem)
    category = route["category"]
    if suppress:
        return "", {"status": "suppressed_by_high_similarity", **route, "selected_chars": 0}
    if not category:
        return "", {"status": "no_subject_match", **route, "selected_chars": 0}
    document = _safe_documents().get(category, "")
    context = select_skill_excerpt(document, problem, max(0, int(limit)))
    if not context:
        return "", {"status": "empty", **route, "selected_chars": 0}
    rendered = (
        "参考学科 Skill（仅供方法规划；必须核对原题条件，不得把其中的示例结论当作本题答案）：\n"
        f"学科：{category}\n{context}"
    )[: max(0, int(limit))]
    return rendered, {
        "status": "used",
        **route,
        "selected_chars": len(rendered),
        "unsafe_projection": True,
    }


__all__ = ["classify_skill_subject", "select_reference_skill_context"]
