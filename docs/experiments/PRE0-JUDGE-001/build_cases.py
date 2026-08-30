"""PRE0-JUDGE-001 corpus builder: 12 answer types x 10 fixed cases = 120.

Writes cases_120.jsonl (frozen corpus) exactly once; drafts go to
tmp/pre0_judge_draft/ for authoring-time validity checks (gold self-score and
ARH dual-form feasibility) before the freeze.  Per preregistration each type
contributes 4 equivalent + 3 non_equivalent + 3 unparseable cases.

Pred wrapping styles (realistic final_response shapes):
  dual   = "最终答案：X\n$\\boxed{X}$"      (ARH frozen emission format)
  marker = "所以最终答案：X"
  boxed  = "答案是 $\\boxed{X}$"
  bare   = "X"                              (standalone short answer line)
  truncated / placeholder / empty          (the three unparseable shapes)
"""
from __future__ import annotations

import json
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
CALC = "calculation"


def dual(pred: str) -> str:
    return f"最终答案：{pred}\n$\\boxed{{{pred}}}$"


def wrap(style: str, pred: str) -> str:
    if style == "dual":
        return dual(pred)
    if style == "marker":
        return f"所以最终答案：{pred}"
    if style == "boxed":
        return f"答案是 $\\boxed{{{pred}}}$"
    if style == "bare":
        return pred
    raise ValueError(style)


UNPARSEABLE_STYLES = ("truncated", "placeholder", "empty")


def unparseable_response(style: str, gold: str) -> str:
    """Truncated responses cut the gold mid-token: a full trailing gold would be
    extractable by unanchored parsers and would fake a 'correct' verdict."""
    if style == "truncated":
        hint = "".join(ch for ch in gold if ch.isalnum())[:6]
        cut = hint[: len(hint) // 2] if len(hint) > 1 else ""
        tail = cut if cut and cut != gold else "其中"
        return f"我们对上式继续化简，代入原条件后整理{tail}"
    if style == "placeholder":
        return "最终答案：[答案]"
    if style == "empty":
        return ""
    raise ValueError(style)


# type -> (judge ptype, gold per case index [(case_key, gold), ...],
#          equivalent preds, non_equivalent preds)
TYPES: dict[str, tuple] = {
    "integer": (
        CALC,
        "948",
        ["948", "948", "948", "948.0"],
        ["949", "-948", "489"],
    ),
    "fraction_decimal": (
        CALC,
        "\\frac{3}{4}",
        ["0.75", "\\frac{6}{8}", "\\dfrac{3}{4}", "3/4"],
        ["\\frac{4}{3}", "0.34", "\\frac{3}{5}"],
    ),
    "radical": (
        CALC,
        "4\\sqrt{15}-14",
        ["-14+4\\sqrt{15}", "\\sqrt{240}-14", "4\\sqrt{15} - 14", "4\\sqrt{15}-14"],
        ["14-4\\sqrt{15}", "4\\sqrt{15}", "4\\sqrt{15}+14"],
    ),
    "symbolic": (
        CALC,
        "x^2+2x+1",
        ["(x+1)^2", "1+2x+x^2", "x\\cdot x+2x+1", "x^2+2x+1"],
        ["x^2-2x+1", "(x+1)^3", "x^2+2x"],
    ),
    "unordered_set": (
        CALC,
        "\\{-1,1\\}",
        ["\\{1,-1\\}", "\\{-1, 1\\}", "\\{1,1,-1\\}", "\\{-1,1\\}"],
        ["\\{-1,2\\}", "\\{1\\}", "\\{-1,0,1\\}"],
    ),
    "interval": (
        CALC,
        "[-1, 2)",
        ["[-1,2)", "\\left[-1, 2\\right)", "[−1, 2)", "[-1, 2)"],
        ["[-1, 2]", "(-1, 2)", "[-2, 2)"],
    ),
    "inequality": (
        CALC,
        "x \\geq 3",
        ["x\\ge 3", "3 \\leq x", "x\\geqslant 3", "x \\geq 3"],
        ["x > 3", "x \\leq 3", "x \\geq 4"],
    ),
    "tuple_vector": (
        CALC,
        "(3, -2)",
        ["(3,-2)", "\\left(3, -2\\right)", "( 3, -2 )", "(3, -2)"],
        ["(3, 2)", "(-3, -2)", "(2, 3)"],
    ),
    "matrix": (
        CALC,
        "\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}",
        [
            "\\begin{pmatrix}1 & 2 \\\\ 3 & 4\\end{pmatrix}",
            "\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}",
            "\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}",
            "\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}",
        ],
        [
            "\\begin{pmatrix}1&3\\\\2&4\\end{pmatrix}",
            "\\begin{pmatrix}1&2\\\\3&5\\end{pmatrix}",
            "\\begin{pmatrix}1&2\\\\3&-4\\end{pmatrix}",
        ],
    ),
    "choice": (
        "choice",
        "C",
        ["C", "C", "c", "\\text{C}"],
        ["B", "D", "AB"],
    ),
    "unit_percent": (
        CALC,
        None,  # mixed golds: percent and unit sub-golds
        ["25\\%", "0.25", "15\\text{cm}", "15cm"],
        ["26%", "16\\text{ cm}", "0.26"],
    ),
    "truncated_placeholder": (
        CALC,
        "42",
        ["42", "42", "42", "42"],
        ["43", "4/2", "41"],
    ),
}

EQ_STYLES = ["dual", "marker", "boxed", "bare"]
NE_STYLES = ["dual", "dual", "dual"]

UNIT_PERCENT_GOLDS = ["25%", "25%", "15\\text{ cm}", "15\\text{ cm}"]
TRUNCATED_NE_PREDS = ["43", "4/2", "41"]


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for type_name, (ptype, gold, eq_preds, ne_preds) in TYPES.items():
        for i, pred in enumerate(eq_preds):
            case_gold = gold
            if type_name == "unit_percent":
                case_gold = UNIT_PERCENT_GOLDS[i]
            if type_name == "truncated_placeholder" and i == 2:
                pred = "42"
            rows.append({
                "case_id": f"{type_name}-eq{i + 1}",
                "answer_type": type_name,
                "category": "equivalent",
                "gold": case_gold,
                "pred_response": wrap(EQ_STYLES[i], pred),
                "note": "",
            })
        for i, pred in enumerate(ne_preds):
            case_gold = gold
            if type_name == "unit_percent":
                case_gold = "25%" if i == 0 or i == 2 else "15\\text{ cm}"
            if type_name == "truncated_placeholder":
                pred = TRUNCATED_NE_PREDS[i]
            rows.append({
                "case_id": f"{type_name}-ne{i + 1}",
                "answer_type": type_name,
                "category": "non_equivalent",
                "gold": case_gold,
                "pred_response": wrap(NE_STYLES[i], pred),
                "note": "",
            })
        for i, style in enumerate(UNPARSEABLE_STYLES):
            case_gold = gold
            if type_name == "unit_percent":
                case_gold = "25%" if i < 2 else "15\\text{ cm}"
            rows.append({
                "case_id": f"{type_name}-up{i + 1}",
                "answer_type": type_name,
                "category": "unparseable",
                "gold": case_gold,
                "pred_response": unparseable_response(style, case_gold),
                "note": f"unparseable shape: {style}",
            })
    return rows


def main() -> None:
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else EXPERIMENT_DIR / "cases_120.jsonl"
    rows = build_rows()
    assert len(rows) == 120, len(rows)
    ids = [row["case_id"] for row in rows]
    assert len(set(ids)) == 120
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    assert counts == {"equivalent": 48, "non_equivalent": 36, "unparseable": 36}, counts
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"wrote {len(rows)} cases to {target}")


if __name__ == "__main__":
    main()
