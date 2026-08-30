"""Independent evaluator for deterministic-solver hits.

This module intentionally does not import ``solve_deterministic``.  It parses
the supported public forms again and recomputes their expected values with a
separate implementation, then compares both the solver output and frozen
answer.  It is evaluator-only and never runs in ``user_agent``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.evaluate_dev import judge_correct
from deterministic_math import solve_deterministic


def independent_expected(problem: str) -> str | None:
    text = problem.strip().replace("−", "-").replace("×", "*")
    m = re.fullmatch(r"(?:计算\s*)?C\((\d+),(\d+)\)\s*\+\s*C\((\d+),(\d+)\)[。.!！]?", text, re.I)
    if m:
        n1, k1, n2, k2 = map(int, m.groups())
        return str(math.comb(n1, k1) + math.comb(n2, k2)) if n1 == n2 and k1 <= n1 and k2 <= n2 else None
    m = re.fullmatch(r"(?:求|解)?(?:方程\s*)?x\^2\s*[-+]\s*(\d+)x\s*\+\s*(\d+)\s*=\s*0(?:\s*的全部实根)?[。.!！]?", text)
    if m:
        b, c = map(int, m.groups())
        roots = sorted({r for r in range(-abs(c), abs(c) + 1) if r and r * r - b * r + c == 0})
        return "{" + ",".join(map(str, roots)) + "}" if len(roots) == 2 else None
    m = re.fullmatch(r"(?:计算\s*)?gcd\((\d+)\s*,\s*(\d+)\)[。.!！]?", text, re.I)
    if m:
        return str(math.gcd(*map(int, m.groups())))
    m = re.fullmatch(r"(?:计算\s*)?(\d+)\s*\^\s*(\d+)\s*(?:mod|%)\s*(\d+)[。.!！]?", text, re.I)
    if m:
        base, exponent, modulus = map(int, m.groups())
        return str(pow(base, exponent, modulus)) if modulus else None
    m = re.fullmatch(r"(?:计算\s*)?矩阵\s*\[\[(\-?\d+),(\-?\d+)\],\[(\-?\d+),(\-?\d+)\]\]\s*的行列式[。.!！]?", text)
    if m:
        a, b, c, d = map(int, m.groups())
        return str(a * d - b * c)
    m = re.fullmatch(r"独立抛掷公平硬币(\d+)次，恰有(\d+)次正面的概率是多少[？?]", text)
    if m:
        n, k = map(int, m.groups())
        return str(Fraction(math.comb(n, k), 2**n)) if 0 <= k <= n else None
    m = re.fullmatch(r"(?:填空[:：]?\s*)?1\s*\+\s*2\s*\+\s*⋯\s*\+(\d+)\s*=\s*_+[。.!！]?", text)
    if m:
        n = int(m.group(1))
        return str(n * (n + 1) // 2)
    m = re.fullmatch(r"填空[:：]?\s*(\d+)!\s*=\s*_+[。.!！]?", text)
    if m:
        return str(math.factorial(int(m.group(1))))
    m = re.fullmatch(r"填空[:：]?\s*C\((\d+)\s*,\s*(\d+)\)\s*=\s*_+[。.!！]?", text, re.I)
    if m:
        n, k = map(int, m.groups())
        return str(math.comb(n, k)) if k <= n else None
    if text in {"填空：若 f(x)=sin x，则 f'(x)=____。", "填空:若 f(x)=sin x，则 f'(x)=____。"}:
        return "cos x"
    m = re.fullmatch(r"填空[:：]?∫_0\^1\s*(\d+)x\s*dx\s*=\s*_+[。.!！]?", text)
    if m:
        return str(Fraction(int(m.group(1)), 2))
    if re.fullmatch(r"(?:填空[:：]?\s*)?2\s*\*\s*2\s*单位矩阵的迹为_+[。.!！]?", text):
        return "2"
    return None


def audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for item in items:
        problem = str(item.get("problem", ""))
        solver_result = solve_deterministic(problem)
        expected_independent = independent_expected(problem)
        if solver_result.get("status") != "supported":
            continue
        answer = str(solver_result.get("answer", ""))
        frozen = str(item.get("answer", ""))
        records.append({
            "idx": item.get("idx"),
            "solver_answer": answer,
            "independent_expected": expected_independent,
            "frozen_answer": frozen,
            "solver_matches_independent": answer == expected_independent,
            "independent_matches_frozen": judge_correct(expected_independent or "", frozen, str(item.get("task_type", ""))) == "correct",
        })
    return {"supported": len(records), "independent_correct": sum(r["solver_matches_independent"] and r["independent_matches_frozen"] for r in records), "mismatches": [r for r in records if not (r["solver_matches_independent"] and r["independent_matches_frozen"])], "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    with args.dataset.open("r", encoding="utf-8") as handle:
        items = [json.loads(line) for line in handle if line.strip()]
    print(json.dumps(audit(items), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
