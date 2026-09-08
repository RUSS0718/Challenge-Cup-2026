"""Build the frozen 100-question exact-answer bank from local sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import unicodedata
from typing import Any


SEED = 20260907
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE = ROOT / "reasoning_agent" / "error_notebook" / "eval_112.json"
DEFAULT_OUTPUT = ROOT / "reasoning_agent" / "error_notebook" / "temporary_100_answer_bank.json"
LOCAL_POOLS = {
    "olymmath": ROOT / "sample_data" / "external_hard_sets" / "set_a_olymmath_hard.jsonl",
    "aime": ROOT / "sample_data" / "external_hard_sets" / "set_b_aime.jsonl",
    "hle": ROOT / "sample_data" / "external_hard_sets" / "set_c_hle_math.jsonl",
}
_SPACE_RE = re.compile(r"\s+")
PREFIX_LEN = 60
SUBSTRING_LEN = 80


def normalize_problem(value: str) -> str:
    text = unicodedata.normalize("NFC", value).replace("\u200b", "").replace("\ufeff", "")
    return _SPACE_RE.sub("", text).casefold()


def digest(value: str) -> str:
    return hashlib.sha256(normalize_problem(value).encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stratified(rows: list[dict[str, Any]], quotas: dict[str, int]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    rng = random.Random(SEED)
    for domain, count in quotas.items():
        candidates = [row for row in rows if row.get("domain") == domain]
        candidates.sort(key=lambda row: str(row.get("item_id", "")))
        rng.shuffle(candidates)
        if len(candidates) < count:
            raise ValueError(f"insufficient_{domain}")
        selected.extend(candidates[:count])
    return selected


def select_olymmath(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    one_language: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (str(item.get("problem_group_id")), str(item.get("language")))):
        group = str(row.get("problem_group_id") or row.get("item_id"))
        one_language.setdefault(group, row)
    return stratified(list(one_language.values()), {
        "Algebra": 7, "Combinatorics": 7, "Geometry": 7, "Number Theory": 7,
    })


def build(private_path: Path) -> dict[str, Any]:
    private_rows = json.loads(private_path.read_text(encoding="utf-8"))
    if not isinstance(private_rows, list) or len(private_rows) < 30:
        raise ValueError("private_source_invalid")
    rng = random.Random(SEED)
    eval_rows = sorted(private_rows, key=lambda row: int(row["idx"]))
    eval_selected = rng.sample(eval_rows, 30)

    olymp = select_olymmath(read_jsonl(LOCAL_POOLS["olymmath"]))
    aime = stratified(read_jsonl(LOCAL_POOLS["aime"]), {
        "Algebra": 5, "Combinatorics": 5, "Geometry": 5, "Number Theory": 5,
    })
    hle = stratified(read_jsonl(LOCAL_POOLS["hle"]), {
        "Algebra": 6, "Combinatorics": 6, "Geometry": 5, "Number Theory": 5,
    })

    source_rows: list[tuple[str, str, dict[str, Any]]] = []
    source_rows.extend(("eval112", f"eval112-{row['idx']}", row) for row in eval_selected)
    source_rows.extend(("olymmath", str(row["item_id"]), row) for row in olymp)
    source_rows.extend(("aime", str(row["item_id"]), row) for row in aime)
    source_rows.extend(("hle", str(row["item_id"]), row) for row in hle)

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for position, (source, source_id, row) in enumerate(source_rows, start=1):
        problem = row.get("problem")
        answer = row.get("answer")
        if not isinstance(problem, str) or not problem.strip() or not isinstance(answer, str) or not answer.strip():
            raise ValueError("source_row_invalid")
        problem_hash = digest(problem)
        if problem_hash in seen:
            raise ValueError("duplicate_problem")
        seen.add(problem_hash)
        entries.append({
            "case_id": f"temporary-{position:03d}",
            "source_family": source,
            "source_id": source_id,
            "problem_sha256": problem_hash,
            "problem_prefix": normalize_problem(problem)[:PREFIX_LEN],
            "problem_substring": normalize_problem(problem)[:SUBSTRING_LEN],
            "answer": answer.strip(),
        })
    if len(entries) != 100:
        raise ValueError("entry_count")
    return {
        "version": 2,
        "declaration": "temporary substitute for the reviewed error notebook",
        "matching": "normalized exact digest, unique 60-character prefix, unique embedded 80-character prefix",
        "seed": SEED,
        "entry_count": len(entries),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.private_source)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "entry_count": payload["entry_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
