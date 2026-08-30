"""PRE0-JUDGE-001: three-judge format calibration over the frozen 120-case corpus.

Zero model calls.  Judges:
  J1 contract   — user_agent extraction + evaluate_dev conservative three-state judge
  J2 hendrycks  — last-boxed extraction + strip_string equality (faithful port of
                  lm-evaluation-harness lm_eval/tasks/hendrycks_math/utils.py, Apache-2.0)
  J3 math_verify— fixed math-verify version, parse fail-closed, verify(gold, pred)
                  direction frozen (gold first), parser timeouts disabled (Windows)

Gates (preregistration §4): gold self-score 120/120 per judge; zero false
positives on non_equivalent; unparseable fail-closed without exception leaks;
ARH dual-form positional/last-boxed canonical equality; coverage + diff tables
recorded without any threshold tuning.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from user_agent import _extract_boxed_answers, extract_final_answer, normalize_answer  # noqa: E402
from scripts.evaluate_dev import judge_correct  # noqa: E402

EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-JUDGE-001"

# ── J2: faithful port of lm-eval hendrycks_math/utils.py (Apache-2.0) ─────────


def _last_boxed_only_string(string: str) -> str | None:
    idx = string.rfind("\\boxed")
    if "\\boxed " in string:
        return "\\boxed " + string.split("\\boxed ")[-1].split("$")[0]
    if idx < 0:
        idx = string.rfind("\\fbox")
        if idx < 0:
            return None
    i = idx
    right_brace_idx = None
    num_left_braces_open = 0
    while i < len(string):
        if string[i] == "{":
            num_left_braces_open += 1
        if string[i] == "}":
            num_left_braces_open -= 1
            if num_left_braces_open == 0:
                right_brace_idx = i
                break
        i += 1
    if right_brace_idx is None:
        return None
    return string[idx : right_brace_idx + 1]


def _remove_boxed(s: str) -> str | None:
    if s is None:
        return None
    if "\\boxed " in s:
        left = "\\boxed "
        if s[: len(left)] != left:
            return None
        return s[len(left):]
    left = "\\boxed{"
    if not (s.startswith(left) and s.endswith("}")):
        return None
    return s[len(left):-1]


def _remove_right_units(string: str) -> str:
    if "\\text{ " in string:
        splits = string.split("\\text{ ")
        if len(splits) == 2:
            return splits[0]
    return string


def _fix_fracs(string: str) -> str:
    substrs = string.split("\\frac")
    new_str = substrs[0]
    if len(substrs) > 1:
        for substr in substrs[1:]:
            new_str += "\\frac"
            if substr and substr[0] == "{":
                new_str += substr
            else:
                if len(substr) < 2:
                    return string
                a, b = substr[0], substr[1]
                if b != "{":
                    if len(substr) > 2:
                        new_str += "{" + a + "}{" + b + "}" + substr[2:]
                    else:
                        new_str += "{" + a + "}{" + b + "}"
                else:
                    if len(substr) > 2:
                        new_str += "{" + a + "}" + b + substr[2:]
                    else:
                        new_str += "{" + a + "}" + b
    return new_str


def _fix_a_slash_b(string: str) -> str:
    if len(string.split("/")) != 2:
        return string
    a, b = string.split("/")
    try:
        a_i, b_i = int(a), int(b)
        assert string == "{}/{}".format(a_i, b_i)
        return "\\frac{" + str(a_i) + "}{" + str(b_i) + "}"
    except (ValueError, AssertionError):
        return string


def _fix_sqrt(string: str) -> str:
    if "\\sqrt" not in string:
        return string
    splits = string.split("\\sqrt")
    new_string = splits[0]
    for split in splits[1:]:
        if split and split[0] != "{":
            new_string += "\\sqrt{" + split[0] + "}" + split[1:]
        else:
            new_string += "\\sqrt" + split
    return new_string


def _strip_string(string: str) -> str:
    string = str(string).strip()
    string = string.replace("\n", "")
    string = string.replace("\\!", "")
    string = string.replace("\\\\", "\\")
    string = string.replace("tfrac", "frac")
    string = string.replace("dfrac", "frac")
    string = string.replace("\\left", "")
    string = string.replace("\\right", "")
    string = string.replace("^{\\circ}", "")
    string = string.replace("^\\circ", "")
    string = string.replace("\\$", "")
    string = _remove_right_units(string)
    string = string.replace("\\%", "")
    string = string.replace("\%", "")  # noqa: W605
    string = string.replace(" .", " 0.")
    string = string.replace("{.", "{0.")
    if len(string) == 0:
        return string
    if string[0] == ".":
        string = "0" + string
    if len(string.split("=")) == 2 and len(string.split("=")[0]) <= 2:
        string = string.split("=")[1]
    string = _fix_sqrt(string)
    string = string.replace(" ", "")
    string = _fix_fracs(string)
    if string == "0.5":
        string = "\\frac{1}{2}"
    string = _fix_a_slash_b(string)
    return string


def _is_equiv(str1: str | None, str2: str | None) -> bool:
    if str1 is None and str2 is None:
        return True
    if str1 is None or str2 is None:
        return False
    try:
        return _strip_string(str1) == _strip_string(str2)
    except Exception:
        return str1 == str2


# ── the three judges ──────────────────────────────────────────────────────────


def judge_contract(gold: str, pred_response: str, ptype: str) -> tuple[str, str]:
    extracted = extract_final_answer(pred_response)
    if not extracted.strip():
        return "unparseable", ""
    verdict = judge_correct(extracted, gold, ptype)
    return verdict, extracted


def judge_hendrycks(gold: str, pred_response: str, _ptype: str) -> tuple[str, str]:
    boxed = _remove_boxed(_last_boxed_only_string(pred_response))
    if boxed is None or not str(boxed).strip():
        return "unparseable", ""
    return ("correct" if _is_equiv(str(boxed), gold) else "incorrect"), str(boxed)


def judge_math_verify(gold: str, pred_response: str, _ptype: str) -> tuple[str, str]:
    from math_verify import parse, verify

    try:
        pred = parse(pred_response, parsing_timeout=None)
    except Exception as exc:  # noqa: BLE001 — fail-closed, error recorded
        return "unparseable", f"parse_error:{type(exc).__name__}"
    if not pred:
        return "unparseable", ""
    try:
        gold_parsed = parse(f"${gold}$", parsing_timeout=None)
        if not gold_parsed:
            return "unparseable", "gold_unparseable"
        result = verify(gold_parsed, pred, timeout_seconds=None)
    except Exception as exc:  # noqa: BLE001
        return "unparseable", f"verify_error:{type(exc).__name__}"
    return ("correct" if result else "incorrect"), ""


def positional_marker_extract(dual_response: str) -> str:
    """Positional-hypothesis extraction: text after the 最终答案： marker line."""
    for line in dual_response.splitlines():
        if line.startswith("最终答案："):
            return line[len("最终答案："):].strip()
    return ""


def judge_dual_form(gold: str) -> str:
    return f"最终答案：{gold}\n$\\boxed{{{gold}}}$"


def main() -> None:
    parser = argparse.ArgumentParser(description="PRE0-JUDGE-001 calibration run")
    parser.add_argument("--cases", type=Path, default=EXPERIMENT_DIR / "cases_120.jsonl")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--skip-boundary-probes", action="store_true")
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) == 120, f"expected 120 cases, got {len(cases)}"
    corpus_sha = __import__("hashlib").sha256(args.cases.read_bytes()).hexdigest()

    import math_verify
    import sympy

    judges = {
        "J1_contract": judge_contract,
        "J2_hendrycks": judge_hendrycks,
        "J3_math_verify": judge_math_verify,
    }
    results = []
    exception_leaks = []
    for case in cases:
        row = {
            "case_id": case["case_id"], "answer_type": case["answer_type"],
            "category": case["category"], "gold": case["gold"],
        }
        for judge_name, judge_fn in judges.items():
            try:
                verdict, detail = judge_fn(case["gold"], case["pred_response"], case["answer_type"])
                error = None
            except Exception as exc:  # noqa: BLE001
                verdict, detail, error = "judge_crash", "", traceback.format_exc(limit=3)
                exception_leaks.append({"case_id": case["case_id"], "judge": judge_name,
                                        "error": f"{type(exc).__name__}: {exc}"})
            row[judge_name] = verdict
            row[f"{judge_name}_detail"] = detail
            if error:
                row[f"{judge_name}_error"] = error
        results.append(row)

    # gold self-score: each gold embedded in the frozen dual-form response
    gold_self = {name: 0 for name in judges}
    arh_failures = []
    for case in cases:
        dual = judge_dual_form(case["gold"])
        for judge_name, judge_fn in judges.items():
            try:
                verdict, _ = judge_fn(case["gold"], dual, case["answer_type"])
            except Exception:  # noqa: BLE001
                verdict = "judge_crash"
            if verdict == "correct":
                gold_self[judge_name] += 1
        positional = normalize_answer(positional_marker_extract(dual))
        boxed_entries = _extract_boxed_answers(dual)
        last_boxed = normalize_answer(boxed_entries[-1]) if boxed_entries else ""
        if not positional or not last_boxed or positional != last_boxed:
            arh_failures.append({
                "case_id": case["case_id"], "gold": case["gold"],
                "positional": positional, "last_boxed": last_boxed,
            })

    # ── boundary probes (recorded findings, not corpus cases) ────────────
    boundary_probes = {}
    if not args.skip_boundary_probes:
        probes = [
            ("percent_escaped_vs_25pct", "25%", "0.25\\%"),
            ("unit_mismatch_cm_vs_m", "15\\text{ cm}", "15\\text{ m}"),
        ]
        for name, gold, pred in probes:
            row = {}
            for judge_name, judge_fn in judges.items():
                try:
                    verdict, _ = judge_fn(gold, f"最终答案：{pred}\n$\\boxed{{{pred}}}$", "calculation")
                    row[judge_name] = verdict
                except Exception as exc:  # noqa: BLE001
                    row[judge_name] = f"crash:{type(exc).__name__}"
            boundary_probes[name] = {"gold": gold, "pred": pred, "verdicts": row}

    # ── gates ─────────────────────────────────────────────────────────────
    def verdict_of(row: dict, judge: str) -> str:
        return row[judge]

    gate2 = {}
    gate3 = {}
    coverage = {name: dict(correct=0, incorrect=0, unknown=0, unparseable=0, judge_crash=0) for name in judges}
    eq_coverage = {name: {} for name in judges}
    fp_cases = {name: [] for name in judges}
    for row in results:
        for judge_name in judges:
            verdict = verdict_of(row, judge_name)
            coverage[judge_name][verdict] = coverage[judge_name].get(verdict, 0) + 1
            if row["category"] == "non_equivalent" and verdict == "correct":
                fp_cases[judge_name].append(row["case_id"])
            if row["category"] == "equivalent":
                eq_coverage[judge_name].setdefault(row["answer_type"], {"correct": 0, "total": 0})
                eq_coverage[judge_name][row["answer_type"]]["total"] += 1
                if verdict == "correct":
                    eq_coverage[judge_name][row["answer_type"]]["correct"] += 1
    for judge_name in judges:
        gate2[judge_name] = len(fp_cases[judge_name]) == 0
        unparse_rows = [row for row in results if row["category"] == "unparseable"]
        bad_unparseable = [row["case_id"] for row in unparse_rows if row[judge_name] == "correct"]
        gate3[judge_name] = (len(bad_unparseable) == 0
                             and not any(row.get(f"{judge_name}_error") for row in results))

    diffsets = {}
    for left, right in (("J1_contract", "J3_math_verify"), ("J2_hendrycks", "J3_math_verify"),
                        ("J1_contract", "J2_hendrycks")):
        diffs = []
        for row in results:
            if row[left] != row[right]:
                diffs.append({"case_id": row["case_id"], "category": row["category"],
                              left: row[left], right: row[right]})
        diffsets[f"{left}_vs_{right}"] = diffs

    gates = {
        "gate1_gold_self_120": {name: (count == 120) for name, count in gold_self.items()},
        "gate2_zero_false_positives": gate2,
        "gate3_unparseable_fail_closed": gate3,
        "gate4_arh_dual_form": (len(arh_failures) == 0, arh_failures),
    }
    all_pass = (
        all(gates["gate1_gold_self_120"].values())
        and all(gate2.values())
        and all(gate3.values())
        and len(arh_failures) == 0
        and not exception_leaks
    )

    manifest = {
        "experiment": "PRE0-JUDGE-001",
        "attempt": args.attempt,
        "run_started_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "sympy_version": sympy.__version__,
        "math_verify_version": getattr(math_verify, "__version__", "0.8.0"),
        "corpus_path": str(args.cases),
        "corpus_sha256": corpus_sha,
        "judge_implementations": {
            "J1_contract": "user_agent.extract_final_answer + evaluate_dev.judge_correct (frozen)",
            "J2_hendrycks": "lm-eval hendrycks_math utils.py port (strip_string, last-boxed)",
            "J3_math_verify": "math-verify parse(parsing_timeout=None) + verify(gold, pred, timeout_seconds=None)",
        },
        "model_calls": 0,
    }
    output = {
        "manifest": manifest,
        "gates": {**gates, "gate1_counts": gold_self},
        "all_passed": all_pass,
        "summary": {"coverage": coverage, "equivalent_coverage_by_type": eq_coverage,
                    "false_positive_cases": fp_cases, "arh_failure_count": len(arh_failures)},
        "diffsets": diffsets,
        "boundary_probes": boundary_probes,
        "exception_leaks": exception_leaks,
        "results": results,
    }
    out_path = EXPERIMENT_DIR / f"judge_results_attempt{args.attempt}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "all_passed": all_pass,
        "gold_self": gold_self,
        "gate2": gate2,
        "gate3": gate3,
        "arh_failures": len(arh_failures),
        "exception_leaks": len(exception_leaks),
        "coverage": coverage,
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
