"""Freeze official_like_hard20_v1 for V4-HARD20-DUAL-001."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLYMP_PATH = ROOT / "tmp" / "p1_data" / "run" / "olympmath_hard20.jsonl"
AIME_PATH = ROOT / "tmp" / "p1_data" / "run" / "aime2024_30.jsonl"
OUT_DIR = ROOT / "docs" / "experiments" / "V4-HARD20-DUAL-001"
DATASET_PATH = OUT_DIR / "official_like_hard20_v1.jsonl"
MANIFEST_PATH = OUT_DIR / "dataset_manifest.json"
SEED = 20260903
DOMAINS = ("Algebra", "Combinatorics", "Geometry", "Number Theory")
DOMAIN_LANG_COUNTS = {
    "Algebra": {"ZH": 2, "EN": 1},
    "Combinatorics": {"ZH": 1, "EN": 2},
    "Geometry": {"ZH": 2, "EN": 1},
    "Number Theory": {"ZH": 1, "EN": 2},
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def pick_olymp(rows: list[dict], rng: random.Random) -> list[dict]:
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        by_key.setdefault((row["subject"], row["language"]), []).append(row)
    selected: list[dict] = []
    for domain in DOMAINS:
        for lang, count in DOMAIN_LANG_COUNTS[domain].items():
            pool = sorted(by_key[(domain, lang)], key=lambda r: r["source_id"])
            rng.shuffle(pool)
            if len(pool) < count:
                raise SystemExit(f"not enough {domain}/{lang}: {len(pool)} < {count}")
            selected.extend(pool[:count])
    return selected


def pick_aime(rows: list[dict], rng: random.Random) -> list[dict]:
    pool = sorted(rows, key=lambda r: r["source_id"])
    rng.shuffle(pool)
    return pool[:8]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    olymp = load_jsonl(OLYMP_PATH)
    aime = load_jsonl(AIME_PATH)
    rng = random.Random(SEED)
    olymp_sel = pick_olymp(olymp, rng)
    aime_sel = pick_aime(aime, rng)

    frozen: list[dict] = []
    for row in olymp_sel:
        frozen.append(
            {
                "item_id": row["source_id"],
                "problem_group_id": row["problem_group_id"],
                "source_family": "OlymMATH",
                "source_id": row["source_id"],
                "language": row["language"],
                "subject": row["subject"],
                "level": row["level"],
                "answer_type": row.get("answer_type", "scalar"),
                "problem": row["problem"],
                "answer": row["answer"],
                "problem_sha256": row["problem_sha256"],
                "gold_sha256": row["gold_sha256"],
            }
        )
    for row in aime_sel:
        frozen.append(
            {
                "item_id": row["source_id"],
                "problem_group_id": row["problem_group_id"],
                "source_family": "AIME",
                "source_id": row["source_id"],
                "language": "EN",
                "subject": "AIME",
                "level": row.get("level", "competition"),
                "answer_type": "integer",
                "problem": row["problem"],
                "answer": str(row["answer"]),
                "problem_sha256": row["problem_sha256"],
                "gold_sha256": row["gold_sha256"],
            }
        )

    if len(frozen) != 20:
        raise SystemExit(f"expected 20, got {len(frozen)}")
    problems = [row["problem"].strip() for row in frozen]
    if len(set(problems)) != 20:
        raise SystemExit("duplicate problems")

    olymp_rows = [r for r in frozen if r["source_family"] == "OlymMATH"]
    aime_rows = [r for r in frozen if r["source_family"] == "AIME"]
    lang = Counter(r["language"] for r in olymp_rows)
    subj = Counter(r["subject"] for r in olymp_rows)
    if lang != Counter({"ZH": 6, "EN": 6}):
        raise SystemExit(f"language mix {lang}")
    if any(subj[d] != 3 for d in DOMAINS):
        raise SystemExit(f"domain mix {subj}")
    if len(aime_rows) != 8:
        raise SystemExit("need 8 AIME")

    aime2025 = ROOT / "tmp" / "p1_data" / "cache" / "aime25_test.jsonl"
    aime2025_problems = set()
    if aime2025.exists():
        for line in aime2025.read_text(encoding="utf-8").splitlines():
            if line.strip():
                aime2025_problems.add(json.loads(line).get("problem", "").strip())
    overlap = [r["item_id"] for r in frozen if r["problem"].strip() in aime2025_problems]
    if overlap:
        raise SystemExit(f"overlap with AIME 2025 fidelity: {overlap}")

    for row in frozen:
        if not row["problem"].strip() or not str(row["answer"]).strip():
            raise SystemExit(f"incomplete {row['item_id']}")

    lines = [json.dumps(row, ensure_ascii=False) + "\n" for row in frozen]
    DATASET_PATH.write_text("".join(lines), encoding="utf-8")
    dataset_sha = sha256_bytes(DATASET_PATH.read_bytes())
    manifest = {
        "dataset_id": "official_like_hard20_v1",
        "seed": SEED,
        "n": 20,
        "olymp_hard": 12,
        "aime2024": 8,
        "selection_rule": {
            "olymp_source": str(OLYMP_PATH.relative_to(ROOT)).replace("\\", "/"),
            "aime_source": str(AIME_PATH.relative_to(ROOT)).replace("\\", "/"),
            "domain_lang_counts": DOMAIN_LANG_COUNTS,
            "aime_take": 8,
            "sort_key": "source_id",
            "shuffle": "random.Random(seed).shuffle after source_id sort",
        },
        "language": dict(lang),
        "subject": dict(subj),
        "item_ids": [r["item_id"] for r in frozen],
        "problem_sha256s": [r["problem_sha256"] for r in frozen],
        "dataset_sha256": dataset_sha,
        "overlap_aime2025": [],
        "static_gate": {
            "complete_20": True,
            "unique_problems": True,
            "lang_6_6": True,
            "domain_3_each": True,
            "gold_present": True,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": 20, "dataset_sha256": dataset_sha, "ids": manifest["item_ids"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
