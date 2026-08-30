"""P1 core120_v2 / confirm30_v2 builders — LOCAL_CACHE_ONLY per user decision.

Raw problems stay in tmp/p1_data/cache/; the repo keeps manifests, IDs, hashes
and static-gate results only (no problem text, no gold text).

Selection rules (spec §5.2):
  MATH-500 50   — levels 1-5 x 10; 7 subjects covered; filter [asy] figures,
                  unit-line golds (PRE0-JUDGE red line) and gold self-score
                  failures; seeded selection, recorded exclusions.
  AIME 2024 30  — full set, integer-exact anchor; figure items flagged.
  AIME 2025 30  — confirm30_v2, same integrity gates.
Static gates (§5.3): native gold self-score 100% on selected; pool-wide
normalized problem dedup; answer-type census; upstream revision + SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE = REPO_ROOT / "tmp" / "p1_data" / "cache"
OUT = REPO_ROOT / "tmp" / "p1_data" / "run"
MANIFEST_DIR = REPO_ROOT / "docs" / "experiments" / "P1_BASELINE"
SEED = 20260830

UPSTREAMS = {
    "math500": {"repo": "HuggingFaceH4/MATH-500", "revision": "6e4ed1a2a79af7d8630a6b768ec859cb5af4d3be",
                "file": "test.jsonl", "license": "NONE DECLARED (local-cache-only per user decision)"},
    "aime2024": {"repo": "Maxwell-Jia/AIME_2024", "revision": "8d88b2876a82a080e2f172cc9b25d0d9d2cb4792",
                 "file": "aime_2024_problems.parquet", "license": "MIT (per HF card; MAA re-licensing chain unverified — cache-only)"},
    "aime2025": {"repo": "math-ai/aime25", "revision": "563bb8404243c5f09de6ec262f2db674fe5bce9b",
                 "file": "test.jsonl", "license": "Apache-2.0 (per HF card; MAA re-licensing chain unverified — cache-only)"},
    "olympmath": {"repo": "RUC-AIBOX/OlymMATH", "revision": "5f83d12e63ee3267f35044461a6cebad58ec3be1",
                  "files": ["data/OlymMATH-EN-EASY.jsonl", "data/OlymMATH-EN-HARD.jsonl",
                            "data/OlymMATH-ZH-EASY.jsonl", "data/OlymMATH-ZH-HARD.jsonl"],
                  "license": "MIT (per HF card)"},
}

UNIT_RE = re.compile(r"\\text\{[^}]*[a-zA-Z]{2,}[^}]*\}|(?:cm|mm|km|meters?|meters|inches|feet|feet|yards?|miles?|sq\.?|units?|dollars?|cents?|%)\b", re.IGNORECASE)


def norm_text(t: str) -> str:
    n = unicodedata.normalize("NFKC", str(t))
    return "".join(n.split()).lower()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def answer_type(ans: str) -> str:
    a = str(ans).strip()
    if a.startswith("[") or a.startswith("(") or "\\in" in a:
        return "interval_or_set_relation"
    if a.startswith("\\{") or a.startswith("{"):
        return "set"
    if "," in a and not a.replace(",", "").replace(".", "").replace("-", "").isdigit():
        return "tuple_or_multi"
    if UNIT_RE.search(a):
        return "unit_flagged"
    if re.fullmatch(r"-?\d+", a):
        return "integer"
    return "expression"


def gold_self_ok(answer: str) -> bool:
    from math_verify import parse, verify

    try:
        g = parse(f"${answer}$", parsing_timeout=None)
        ok = bool(g) and verify(g, g, timeout_seconds=None) is True
    except Exception:  # noqa: BLE001
        ok = False
    return ok


def write_run_and_records(name: str, rows: list[dict], extra: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run_path = OUT / f"{name}.jsonl"
    run_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    records = [{
        "idx": r["idx"],
        "source_id": r["source_id"],
        "subject": r.get("subject"),
        "level": r.get("level"),
        "language": r.get("language"),
        "problem_group_id": r.get("problem_group_id"),
        "answer_type": r["answer_type"],
        "problem_sha256": r["problem_sha256"],
        "gold_sha256": r["gold_sha256"],
        "flags": r.get("flags", []),
    } for r in rows]
    manifest = {
        "layer": name,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "upstream": extra.get("upstream"),
        "raw_file_sha256": extra.get("raw_file_sha256"),
        "selection": extra.get("selection"),
        "static_gates": extra.get("static_gates"),
        "run_dataset_sha256": sha(run_path.read_bytes()),
        "run_dataset_local_path": str(run_path.relative_to(REPO_ROOT)),
        "item_count": len(rows),
        "selection_records_no_problem_text": records,
        "note": "LOCAL_CACHE_ONLY: problem/gold text lives only in tmp/p1_data/ (user decision P1_DATA)",
    }
    (MANIFEST_DIR / f"{name}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(rows)} items -> {run_path}")


def build_math500() -> None:
    rows = [json.loads(line) for line in (CACHE / "math500_test.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 500
    pool, excluded = [], {"asy_figure": 0, "unit_gold": 0, "gold_self_fail": 0, "empty_gold": 0}
    seen = set()
    for item in rows:
        digest = sha(norm_text(item["problem"]).encode("utf-8"))
        if digest in seen:
            continue
        seen.add(digest)
        flags = []
        if "[asy]" in item["problem"] or "[Asy]" in item["problem"]:
            excluded["asy_figure"] += 1
            continue
        gold = str(item["answer"]).strip()
        if not gold:
            excluded["empty_gold"] += 1
            continue
        if UNIT_RE.search(gold):
            excluded["unit_gold"] += 1
            continue
        if not gold_self_ok(gold):
            excluded["gold_self_fail"] += 1
            continue
        pool.append({
            "unique_id": item["unique_id"], "problem": item["problem"], "gold": gold,
            "subject": item["subject"], "level": item["level"], "problem_sha256": digest,
        })

    by_level: dict[str, list] = {}
    for item in pool:
        by_level.setdefault(item["level"], []).append(item)
    for level, items in by_level.items():
        items.sort(key=lambda x: x["unique_id"])
        random.Random(SEED).shuffle(items)

    selected = []
    subject_seen: set[str] = set()
    # pass 1: guarantee 7-subject coverage using seeded order
    subjects = sorted({item["subject"] for item in pool})
    for subject in subjects:
        for level in sorted(by_level):
            if len([s for s in selected if s["subject"] == subject]) >= 1:
                break
            for item in by_level[level]:
                if item["subject"] == subject and sum(1 for s in selected if s["level"] == level) < 10 \
                        and all(s["unique_id"] != item["unique_id"] for s in selected):
                    selected.append(item)
                    subject_seen.add(subject)
                    break
    # pass 2: fill to 10 per level in seeded order
    for level in sorted(by_level):
        for item in by_level[level]:
            if sum(1 for s in selected if s["level"] == level) >= 10:
                break
            if all(s["unique_id"] != item["unique_id"] for s in selected):
                selected.append(item)
    assert len(selected) == 50, len(selected)
    assert len(subject_seen) == 7, sorted(subject_seen)

    run_rows = []
    for idx, item in enumerate(sorted(selected, key=lambda x: (x["level"], x["unique_id"]))):
        run_rows.append({
            "idx": idx,
            "problem": item["problem"],
            "answer": item["gold"],
            "source_id": item["unique_id"],
            "subject": item["subject"],
            "level": item["level"],
            "answer_type": answer_type(item["gold"]),
            "problem_sha256": item["problem_sha256"],
            "gold_sha256": sha(item["gold"].encode("utf-8")),
            "problem_group_id": item["unique_id"],
            "flags": [],
        })
    raw = (CACHE / "math500_test.jsonl").read_bytes()
    write_run_and_records("core120_v2_math500", run_rows, {
        "upstream": UPSTREAMS["math500"],
        "raw_file_sha256": {"test.jsonl": sha(raw)},
        "selection": {
            "seed": SEED,
            "rules": "levels 1-5 x 10; 7-subject coverage pass first; [asy]/unit-gold/self-score-fail excluded",
            "pool_after_filters": len(pool),
            "excluded": excluded,
            "level_counts": dict(Counter(r["level"] for r in run_rows)),
            "subject_counts": dict(Counter(r["subject"] for r in run_rows)),
        },
        "static_gates": {
            "pool_dedup": "500 rows normalized-dedup",
            "gold_self_score": "100% on selected (self-score failures excluded from pool)",
            "unit_red_line": "unit-pattern golds excluded (PRE0-JUDGE-001 boundary)",
        },
    })


def build_aime2024() -> None:
    import pandas as pd

    df = pd.read_parquet(CACHE / "aime2024.parquet")
    assert len(df) == 30, len(df)
    raw = (CACHE / "aime2024.parquet").read_bytes()
    run_rows, flagged = [], []
    seen = set()
    for _, row in df.iterrows():
        pid = str(row["ID"])
        problem = str(row["Problem"])
        digest = sha(norm_text(problem).encode("utf-8"))
        assert digest not in seen, pid
        seen.add(digest)
        gold = str(row["Answer"]).strip()
        assert re.fullmatch(r"\d+", gold) and 0 <= int(gold) <= 999, pid
        flags = ["figure_asy"] if "[asy]" in problem.lower() else []
        if flags:
            flagged.append(pid)
        run_rows.append({
            "idx": len(run_rows),
            "problem": problem,
            "answer": gold,
            "source_id": pid,
            "subject": "AIME",
            "level": "competition",
            "answer_type": "integer",
            "problem_sha256": digest,
            "gold_sha256": sha(gold.encode("utf-8")),
            "problem_group_id": pid,
            "flags": flags,
        })
    # integer gold self-score trivially 100% via exact match; assert integers
    assert all(r["answer"].isdigit() for r in run_rows)
    write_run_and_records("confirm_aim2024_anchor", run_rows, {
        "upstream": UPSTREAMS["aime2024"],
        "raw_file_sha256": {"aime_2024_problems.parquet": sha(raw)},
        "selection": {"seed": None, "rules": "full 30, no sampling; integer-exact anchor",
                      "figure_flagged_ids": flagged},
        "static_gates": {"ids_unique": True, "gold_integer_0_999": True,
                         "pool_dedup": "30 unique", "gold_self_score": "integer exact"},
    })


def build_aime2025() -> None:
    rows = [json.loads(line) for line in (CACHE / "aime25_test.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 30, len(rows)
    raw = (CACHE / "aime25_test.jsonl").read_bytes()
    print("aime25 fields:", sorted(rows[0].keys()))
    run_rows, flagged = [], []
    seen = set()
    for item in rows:
        pid = str(item.get("id") or item.get("ID") or len(run_rows))
        problem = str(item.get("problem") or item.get("Problem") or item.get("question"))
        digest = sha(norm_text(problem).encode("utf-8"))
        assert digest not in seen, pid
        seen.add(digest)
        gold = str(item.get("answer") if item.get("answer") is not None else item.get("Answer")).strip()
        assert re.fullmatch(r"-?\d+", gold), (pid, gold)
        flags = ["figure_asy"] if "[asy]" in problem.lower() else []
        if flags:
            flagged.append(pid)
        run_rows.append({
            "idx": len(run_rows),
            "problem": problem,
            "answer": gold,
            "source_id": pid,
            "subject": "AIME",
            "level": "competition",
            "answer_type": "integer",
            "problem_sha256": digest,
            "gold_sha256": sha(gold.encode("utf-8")),
            "problem_group_id": pid,
            "flags": flags,
        })
    write_run_and_records("confirm30_v2_aim2025", run_rows, {
        "upstream": UPSTREAMS["aime2025"],
        "raw_file_sha256": {"test.jsonl": sha(raw)},
        "selection": {"seed": None, "rules": "full 30, no sampling; independent-year confirm",
                      "figure_flagged_ids": flagged},
        "static_gates": {"ids_unique": True, "gold_integer": True,
                         "pool_dedup": "30 unique", "gold_self_score": "integer exact"},
    })


if __name__ == "__main__":
    build_math500()
    build_aime2024()
    build_aime2025()
