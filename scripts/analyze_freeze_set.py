# -*- coding: utf-8 -*-
"""冻结集两轮基线结果分析：按 task_type 宏平均 + 失败类别归类。

读取 docs/13_2/freeze_round{1,2}.json 的 records，结合冻结集 task_type 标签，
输出：整体宏平均、各题型 correct/incorrect/unknown 明细、失败类别归类。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

FREEZE = REPO_ROOT / "sample_data" / "complex_capability_freeze_48.jsonl"
PURE_PROPOSITION = {6013, 6041}  # √2 / √3 无理


def load_freeze() -> dict[int, dict]:
    out: dict[int, dict] = {}
    for line in FREEZE.open(encoding="utf-8"):
        it = json.loads(line)
        out[it["idx"]] = it
    return out


def classify_failure(rec: dict, item: dict) -> str:
    """归类一题失败的原因（仅在 verdict != correct 时调用）。"""
    v = rec["verdict"]
    if v == "incorrect":
        return "incorrect（可判定但不匹配）"
    if v != "unknown":
        return v
    idx = rec["idx"]
    if idx in PURE_PROPOSITION:
        return "unknown-纯命题（人工复核）"
    ext = rec.get("extracted_answer", "")
    exp = rec.get("expected", "")
    if not ext or not ext.strip():
        return "unknown-空抽取"
    # 表示不一致：ext/exp 都非空但无法自动判定等价
    return "unknown-表示不一致"


def main() -> int:
    freeze = load_freeze()
    all_recs = []
    for round_name in ("round1", "round2"):
        path = REPO_ROOT / "docs" / "13_2" / f"freeze_{round_name}.json"
        if not path.exists():
            print(f"missing {path}")
            continue
        report = json.loads(path.read_text(encoding="utf-8"))[0]
        for rec in report["records"]:
            rec = dict(rec)
            rec["round"] = round_name
            all_recs.append(rec)

    by_type = defaultdict(list)
    for rec in all_recs:
        item = freeze[rec["idx"]]
        by_type[item["task_type"]].append(rec)

    print("=== 题型宏平均（两轮合并，按题计 2 次）===")
    type_order = ["choice", "fill_blank", "calculation", "derivation", "proof", "explanation"]
    accs = []
    for t in type_order:
        recs = by_type[t]
        c = sum(1 for r in recs if r["verdict"] == "correct")
        n = len(recs)
        acc = c / n if n else 0.0
        accs.append(acc)
        vc = Counter(r["verdict"] for r in recs)
        print(f"  {t:12s} n={n:2d}  correct={c:2d}  acc={acc*100:5.1f}%  verdicts={dict(vc)}")
    macro = sum(accs) / len(accs)
    print(f"  {'宏平均':12s} acc={macro*100:.1f}%")

    print("\n=== 逐题明细（round | idx | task_type | verdict | extracted vs expected）===")
    for rec in sorted(all_recs, key=lambda r: r["idx"]):
        item = freeze[rec["idx"]]
        t = item["task_type"]
        ext = str(rec.get("extracted_answer", ""))[:28].replace("\n", " ")
        exp = str(rec.get("expected", ""))[:20]
        flag = " [纯命题]" if rec["idx"] in PURE_PROPOSITION else ""
        print(f"  {rec['round'][-1]} {rec['idx']:4d} {t:12s} {rec['verdict']:9s} | {ext!r:32} vs {exp!r}{flag}")

    print("\n=== 失败类别汇总（两轮合并，verdict != correct）===")
    fail_cat = Counter()
    for rec in all_recs:
        if rec["verdict"] == "correct":
            continue
        item = freeze[rec["idx"]]
        fail_cat[classify_failure(rec, item)] += 1
    for cat, n in fail_cat.most_common():
        print(f"  {n:3d}  {cat}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
