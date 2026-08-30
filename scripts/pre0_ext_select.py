"""PRE0-EXT-001 selection: 12 unique OlymMATH problems per the frozen algorithm.

Preregistration §4: pool = unique problems whose gold self-scores in both
languages (static gate: 400/400 pass).  Allocation per domain (easy/hard):
Algebra 2/1, Geometry 1/2, Number Theory 2/1, Combinatorics 1/2 -> 6 easy,
6 hard, 3 per domain.  Language ZH/EN alternates over the sorted 12 selections
(6/6); a problem is used in exactly one language.  Seed 20260830.

Writes the runnable dataset (with problem text) to tmp/pre0_ext_001/cache/
ext12_run.jsonl and a repo-side selection manifest WITHOUT problem text.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE = REPO_ROOT / "tmp" / "pre0_ext_001" / "cache"
EXPERIMENT_DIR = REPO_ROOT / "docs" / "experiments" / "PRE0-EXT-001"
REVISION = "5f83d12e63ee3267f35044461a6cebad58ec3be1"
SEED = 20260830

FILES = {
    ("easy", "EN"): "OlymMATH-EN-EASY.jsonl",
    ("easy", "ZH"): "OlymMATH-ZH-EASY.jsonl",
    ("hard", "EN"): "OlymMATH-EN-HARD.jsonl",
    ("hard", "ZH"): "OlymMATH-ZH-HARD.jsonl",
}
SUBJECT_MAP = {"Combinatorics": "组合", "Geometry": "几何", "Algebra": "代数", "Number Theory": "数论"}
DOM_EN2ZH = {"Algebra": "代数", "Geometry": "几何", "Number Theory": "数论", "Combinatorics": "组合"}
# domain -> {difficulty: count}
ALLOCATION = {
    "Algebra": {"easy": 2, "hard": 1},
    "Geometry": {"easy": 1, "hard": 2},
    "Number Theory": {"easy": 2, "hard": 1},
    "Combinatorics": {"easy": 1, "hard": 2},
}


def answer_type(answer: str) -> str:
    a = str(answer).strip()
    if a.startswith("[") or a.startswith("("):
        return "interval"
    if "," in a:
        return "multi"
    return "scalar"


def main() -> None:
    rows = {}
    for key, name in FILES.items():
        rows[key] = [json.loads(line) for line in (CACHE / name).read_text(encoding="utf-8").splitlines() if line.strip()]

    # pool: per (difficulty, domain_EN) -> list of (stem, en_row, zh_row),
    # requiring the id stems to correspond and both rows to exist.
    pool: dict[tuple, list] = {}
    for difficulty in ("easy", "hard"):
        for en_row, zh_row in zip(rows[(difficulty, "EN")], rows[(difficulty, "ZH")]):
            en_stem = en_row["unique_id"].rsplit("-", 1)[0]
            zh_stem = zh_row["unique_id"].rsplit("-", 1)[0]
            assert en_stem == zh_stem, (en_row["unique_id"], zh_row["unique_id"])
            domain = en_row["subject"]
            pool.setdefault((difficulty, domain), []).append((en_stem, en_row, zh_row))

    rng = random.Random(SEED)
    selected = []
    for domain in sorted(ALLOCATION):
        for difficulty, count in ALLOCATION[domain].items():
            cell = sorted(pool[(difficulty, domain)], key=lambda entry: entry[0])
            if len(cell) < count:
                raise SystemExit(f"cell_underfilled:{difficulty}/{domain}: {len(cell)} < {count}")
            for stem, en_row, zh_row in rng.sample(cell, count):
                selected.append({"difficulty": difficulty, "domain": domain, "stem": stem,
                                 "en_row": en_row, "zh_row": zh_row})

    selected.sort(key=lambda entry: (entry["difficulty"], entry["domain"], entry["stem"]))
    language_by_position = ["ZH", "EN"]

    run_rows = []
    selection_records = []
    for position, entry in enumerate(selected):
        language = language_by_position[position % 2]
        row = entry["zh_row"] if language == "ZH" else entry["en_row"]
        run_rows.append({
            "idx": position,
            "problem": row["problem"],
            "answer": str(row["answer"]),
            "unique_id": row["unique_id"],
            "problem_group_id": entry["stem"],
            "subject": row["subject"],
            "subject_en": entry["domain"],
            "difficulty": entry["difficulty"],
            "language": language,
            "answer_type": answer_type(row["answer"]),
        })
        selection_records.append({
            "idx": position,
            "problem_group_id": entry["stem"],
            "difficulty": entry["difficulty"],
            "domain_en": entry["domain"],
            "language": language,
            "unique_id": row["unique_id"],
            "answer_type": answer_type(row["answer"]),
        })

    counts = {
        "easy": sum(1 for r in run_rows if r["difficulty"] == "easy"),
        "hard": sum(1 for r in run_rows if r["difficulty"] == "hard"),
        "ZH": sum(1 for r in run_rows if r["language"] == "ZH"),
        "EN": sum(1 for r in run_rows if r["language"] == "EN"),
    }
    assert counts == {"easy": 6, "hard": 6, "ZH": 6, "EN": 6}, counts
    stems = [r["problem_group_id"] for r in run_rows]
    assert len(set(stems)) == 12, "no math problem may appear in both languages"

    run_path = CACHE / "ext12_run.jsonl"
    run_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in run_rows), encoding="utf-8")
    run_sha = hashlib.sha256(run_path.read_bytes()).hexdigest()

    file_hashes = {
        name: hashlib.sha256((CACHE / name).read_bytes()).hexdigest() for name in FILES.values()
    }
    manifest = {
        "experiment": "PRE0-EXT-001",
        "selected_utc": datetime.now(timezone.utc).isoformat(),
        "upstream": {
            "dataset": "RUC-AIBOX/OlymMATH",
            "revision": REVISION,
            "files_sha256": file_hashes,
            "license": "MIT (per HF dataset card; audit 2026-08-29 §3.4)",
            "download_date": "2026-08-30",
            "mirror": "hf-mirror.com",
        },
        "selection": {
            "seed": SEED,
            "algorithm": ("per-domain easy/hard quota {Algebra 2/1, Geometry 1/2, "
                          "Number Theory 2/1, Combinatorics 1/2}; within-cell seeded "
                          "sample from sorted unique-id stems; language alternates ZH/EN "
                          "over sorted selections; no stem reused across languages"),
            "counts": counts,
            "static_gate": "static_gate_result.json: 400/400 gold self-score, 0 parallel mismatches",
        },
        "run_dataset_sha256": run_sha,
        "note": "problem texts live only in the local cache (tmp/pre0_ext_001/cache/); the repo keeps IDs and hashes",
    }
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENT_DIR / "selection_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EXPERIMENT_DIR / "selection_records.json").write_text(
        json.dumps(selection_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": counts, "run_sha256": run_sha,
                      "stems": [r["problem_group_id"] for r in run_rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
