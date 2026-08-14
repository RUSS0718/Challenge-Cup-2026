"""F0 离线对照：在同一批原始响应上比较 C2+D 解析 vs F 三状态行解析（只针对非数值题型）。

不花模型调用。读 --save-raw-dir 产出的完整响应，对每题主调用原始响应分别跑
C2+D 与 F 解析，验证 F 的离线晋升门槛：

1. 原本干净响应保持不变（C2+D 已 clean 且 correct 的题，F 也 clean 且可判定）；
2. 不删除有效证明正文（F body 非空）；
3. 不把元分析识别成答案（F answer 不含 thinking 前缀）；
4. 无可靠答案和正文结构时明确返回「不具备重建条件」。

用法：
  python scripts/compare_f_parser.py docs/13_2/raw_dump/raw_token3072_temp0.6.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from user_agent import (  # noqa: E402
    _NON_NUMERIC_TASK_TYPES,
    parse_structure_f,
    reconstruct_final_response,
    reconstruct_final_response_f,
)

# 与 evaluate_token_ladder._detect_thinking 一致（精确匹配 thinking 前缀，不含结构标记）。
_THINKING_RE = re.compile(
    r"Thinking\s*Process|thinking\s*process|Here['\u2019]?s?\s+a?\s*thinking"
    r"|the\s+user\s+wants\s+me\s+to|Let\s+me\s+(?:think|analyze|solve|derive)",
    re.IGNORECASE,
)


def _has_thinking(text: str) -> bool:
    return bool(text and _THINKING_RE.search(text))


def main() -> None:
    raw_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/13_2/raw_dump/raw_token3072_temp0.6.jsonl")
    records = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 只对照非数值题型（derivation/proof/explanation），数值题型走 compact 答案不走正文解析。
    records = [r for r in records if r["problem_type"] in _NON_NUMERIC_TASK_TYPES]

    stats = {"total": 0, "structured": 0, "no_answer": 0, "no_body": 0,
             "clean_total": 0, "clean_kept": 0, "meta_misparsed": 0,
             "c2d_think": 0, "f_think": 0, "body_empty": 0}

    for r in records:
        raw = r["raw_responses"][0] if r["raw_responses"] else ""
        ptype = r["problem_type"]
        c2d_clean = not r["final_response_thinking"]
        verdict = r["verdict"]

        parsed = parse_structure_f(raw, ptype)
        f_rebuilt = reconstruct_final_response_f(raw, ptype)

        stats["total"] += 1
        if parsed["status"] == "structured":
            stats["structured"] += 1
            if not parsed["body"].strip():
                stats["body_empty"] += 1
        elif parsed["status"] == "no_answer_block":
            stats["no_answer"] += 1
        else:
            stats["no_body"] += 1

        # 门槛 1：C2+D clean 且 correct 的题，F 应 structured 且重建干净且答案非空
        if c2d_clean and verdict == "correct":
            stats["clean_total"] += 1
            if parsed["status"] == "structured" and parsed["answer"] and not _has_thinking(f_rebuilt):
                stats["clean_kept"] += 1

        # 门槛 3：raw 含 thinking 但 F 把 thinking 文本当答案
        if parsed["status"] == "structured" and _has_thinking(parsed["answer"]):
            stats["meta_misparsed"] += 1

        # 门槛 4：F 重建输出仍含 thinking 前缀（应比 C2+D 少）
        if _has_thinking(f_rebuilt):
            stats["f_think"] += 1
        if _has_thinking(reconstruct_final_response(raw, ptype)):
            stats["c2d_think"] += 1

    print(f"=== F0 离线对照（非数值题型 {stats['total']} 题）===")
    print(f"F status 分布: structured={stats['structured']} "
          f"no_answer_block={stats['no_answer']} no_body={stats['no_body']}")
    print(f"  structured 中 body 为空的题数: {stats['body_empty']}")
    print(f"门槛1 干净响应保持: {stats['clean_kept']}/{stats['clean_total']}")
    print(f"门槛3 元分析误判为答案: {stats['meta_misparsed']}")
    print(f"门槛4 重建后仍含 thinking 前缀: C2+D={stats['c2d_think']} F={stats['f_think']}")
    print()
    # 逐题明细
    for r in records:
        raw = r["raw_responses"][0] if r["raw_responses"] else ""
        parsed = parse_structure_f(raw, r["problem_type"])
        ans = (parsed["answer"] or "")[:30]
        body_len = len((parsed.get("body") or ""))
        print(f"  {r['idx']:4d} {r['problem_type']:12s} verdict={r['verdict']:9s} "
              f"status={parsed['status']:15s} body_len={body_len:4d} answer={ans!r}")


if __name__ == "__main__":
    main()
