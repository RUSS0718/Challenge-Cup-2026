# -*- coding: utf-8 -*-
"""校验 13.2 复杂能力冻结集的完整性、分布、隔离与可判定性。

校验项：
1. 总量 = 48，idx 唯一且为 int（6000 段）
2. 题型分布精确匹配（choice6/fill_blank6/calc6/derivation10/proof10/explanation10）
3. 长条件 >= 12、跨方向 >= 12
4. 字段完整性（problem/answer/task_type/subject/source/adaptation/verification 非空；教材集 source_url 必填）
5. 题干去重
6. 与 public_regression_112.jsonl 题干隔离（不相交）
7. classify_problem_type(problem) == task_type（分类一致性）
8. 答案自洽：judge_correct(answer, answer, task_type) == "correct"
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from user_agent import classify_problem_type  # noqa: E402
from scripts.evaluate_dev import judge_correct, load_items  # noqa: E402

FREEZE = REPO_ROOT / "sample_data" / "complex_capability_freeze_48.jsonl"
REGRESSION = REPO_ROOT / "sample_data" / "public_regression_112.jsonl"

EXPECTED_TYPES = Counter({
    "choice": 6, "fill_blank": 6, "calculation": 6,
    "derivation": 10, "proof": 10, "explanation": 10,
})
REQUIRED_FIELDS = ("problem", "answer", "task_type", "subject", "source", "adaptation", "verification")
TASK_TYPES = set(EXPECTED_TYPES)
PURE_PROPOSITION_IDX = {6013, 6041}  # √2 / √3 无理，judge 判 unknown、人工复核


def check() -> list[str]:
    errors: list[str] = []
    items = load_items(FREEZE)

    # 1. 总量与 idx
    if len(items) != 48:
        errors.append(f"total:{len(items)}")
    idxs = [it.get("idx") for it in items]
    if not all(isinstance(i, int) for i in idxs):
        errors.append("idx_not_all_int")
    elif len(set(idxs)) != len(idxs):
        errors.append("duplicate_idx")
    if any(not (6000 <= i <= 6047) for i in idxs if isinstance(i, int)):
        errors.append("idx_out_of_6000_range")

    # 2. 题型分布
    tc = Counter(it.get("task_type") for it in items)
    if tc != EXPECTED_TYPES:
        errors.append(f"task_type_dist:{dict(tc)}")
    unknown_types = set(tc) - TASK_TYPES
    if unknown_types:
        errors.append(f"unknown_task_type:{unknown_types}")

    # 3. 长条件 / 跨方向
    n_long = sum(1 for it in items if it.get("is_long"))
    n_multi = sum(1 for it in items if it.get("is_multi_domain"))
    if n_long < 12:
        errors.append(f"is_long:{n_long}")
    if n_multi < 12:
        errors.append(f"is_multi_domain:{n_multi}")

    # 4. 字段完整性
    for it in items:
        for f in REQUIRED_FIELDS:
            if not str(it.get(f, "")).strip():
                errors.append(f"empty_{f}:{it.get('idx')}")
        if it.get("source") != "ai_generated" and not str(it.get("source_url", "")).startswith("https://"):
            errors.append(f"missing_source_url:{it.get('idx')}")

    # 5. 题干去重
    problems = [str(it.get("problem", "")).strip() for it in items]
    if len(set(problems)) != len(problems):
        errors.append("duplicate_problem")

    # 6. 与 112 题隔离
    reg_problems = {str(it.get("problem", "")).strip() for it in load_items(REGRESSION)}
    overlap = set(problems) & reg_problems
    if overlap:
        errors.append(f"overlap_with_112:{len(overlap)}")

    # 7. 分类一致性
    mismatch = []
    for it in items:
        actual = classify_problem_type(it["problem"])
        if actual != it["task_type"]:
            mismatch.append((it["idx"], it["task_type"], actual))
    if mismatch:
        errors.append(f"classify_mismatch:{mismatch}")

    # 8. 答案自洽（judge 能判自己为 correct）
    for it in items:
        if judge_correct(it["answer"], it["answer"], it["task_type"]) != "correct":
            errors.append(f"answer_not_judgeable:{it['idx']}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("FAIL")
        for e in errors:
            print("  -", e)
        return 1
    items = load_items(FREEZE)
    tc = Counter(it.get("task_type") for it in items)
    n_long = sum(1 for it in items if it.get("is_long"))
    n_multi = sum(1 for it in items if it.get("is_multi_domain"))
    print(f"PASS: {len(items)} 题 | 题型 {dict(tc)} | 长条件 {n_long} | 跨方向 {n_multi} | 纯命题 {len(PURE_PROPOSITION_IDX)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
