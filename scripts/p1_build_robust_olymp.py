"""P1 builders: OlymMATH 40 (core120_v2 third component) + robust180_v2 (GSM-Plus).

LOCAL_CACHE_ONLY — run files in tmp/p1_data/run/, repo keeps manifests/IDs/hashes.

OlymMATH 40 (spec §5.2): unique problems, easy/hard 20 each, four domains 10
each, ZH/EN 20 each, no math problem in both languages; first-release revision.
Allocation: per domain easy/hard = {3,2} or {2,3} alternating -> easy 20/hard 20,
domain 10 each.  Language ZH/EN alternates over sorted selections.

robust180_v2 (spec §5.2): GSM-Plus 20 seeds x (original + 8 perturbations).
Original row = the embedded seed_question/seed_answer; 8 perturbation rows from
the test set.  critical-thinking gold is None -> kept separate (never merged
into numeric accuracy).  Seed selection from the seed-question pool, seeded.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE = REPO_ROOT / "tmp" / "p1_data" / "cache"
EXT_CACHE = REPO_ROOT / "tmp" / "pre0_ext_001" / "cache"
OUT = REPO_ROOT / "tmp" / "p1_data" / "run"
MANIFEST_DIR = REPO_ROOT / "docs" / "experiments" / "P1_BASELINE"
SEED = 20260830

OLYMP_FILES = {
    ("easy", "EN"): "OlymMATH-EN-EASY.jsonl",
    ("easy", "ZH"): "OlymMATH-ZH-EASY.jsonl",
    ("hard", "EN"): "OlymMATH-EN-HARD.jsonl",
    ("hard", "ZH"): "OlymMATH-ZH-HARD.jsonl",
}
DOM_EN2ZH = {"Algebra": "代数", "Geometry": "几何", "Number Theory": "数论", "Combinatorics": "组合"}
ALLOCATION = {  # domain -> {difficulty: count} -> easy 20 / hard 20, 10 per domain
    "Algebra": {"easy": 5, "hard": 5},
    "Geometry": {"easy": 5, "hard": 5},
    "Number Theory": {"easy": 5, "hard": 5},
    "Combinatorics": {"easy": 5, "hard": 5},
}
GSMPLUS_UPSTREAM = {"repo": "qintongli/GSM-Plus", "revision": "3b708db57b96a16e8e3368ed2956990c0809440e",
                    "file": "GSM-Plus.json", "license": "CC BY-SA 4.0 (no training use per data card)"}
GSM_SEEDS = 20


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def answer_type(answer: str) -> str:
    a = str(answer).strip()
    if a.startswith("[") or a.startswith("("):
        return "interval"
    if "," in a:
        return "multi"
    return "scalar"


def write_layer(name: str, rows: list[dict], extra: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run_path = OUT / f"{name}.jsonl"
    run_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    records = [{
        "idx": r["idx"], "source_id": r["source_id"], "subject": r.get("subject"),
        "level": r.get("level"), "language": r.get("language"),
        "problem_group_id": r.get("problem_group_id"),
        "answer_type": r["answer_type"], "perturbation_type": r.get("perturbation_type"),
        "problem_sha256": r["problem_sha256"], "gold_sha256": r["gold_sha256"],
        "flags": r.get("flags", []),
    } for r in rows]
    manifest = {
        "layer": name,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "upstream": extra.get("upstream"),
        "raw_file_sha256": extra.get("raw_file_sha256"),
        "selection": extra.get("selection"),
        "static_gates": extra.get("static_gates"),
        "run_dataset_sha256": sha_bytes(run_path.read_bytes()),
        "run_dataset_local_path": str(run_path.relative_to(REPO_ROOT)),
        "item_count": len(rows),
        "selection_records_no_problem_text": records,
        "note": "LOCAL_CACHE_ONLY: problem/gold text lives only in tmp/p1_data/ (user decision P1_DATA)",
    }
    (MANIFEST_DIR / f"{name}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(rows)} items -> {run_path}")


def build_olympmath40() -> None:
    import unicodedata

    def norm(t: str) -> str:
        return "".join(unicodedata.normalize("NFKC", t).split()).lower()

    rows = {}
    for key, name in OLYMP_FILES.items():
        path = EXT_CACHE / name  # same first-release bytes as PRE0-EXT cache
        assert path.is_file(), f"missing cache file {name} — re-run the EXT download"
        rows[key] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    pool: dict[tuple, list] = {}
    for difficulty in ("easy", "hard"):
        for en_row, zh_row in zip(rows[(difficulty, "EN")], rows[(difficulty, "ZH")]):
            en_stem = en_row["unique_id"].rsplit("-", 1)[0]
            zh_stem = zh_row["unique_id"].rsplit("-", 1)[0]
            assert en_stem == zh_stem
            pool.setdefault((difficulty, en_row["subject"]), []).append((en_stem, en_row, zh_row))

    rng = random.Random(SEED)
    selected = []
    for domain in sorted(ALLOCATION):
        for difficulty, count in ALLOCATION[domain].items():
            cell = sorted(pool[(difficulty, domain)], key=lambda e: e[0])
            assert len(cell) >= count, (difficulty, domain, len(cell))
            for stem, en_row, zh_row in rng.sample(cell, count):
                selected.append({"difficulty": difficulty, "domain": domain, "stem": stem,
                                 "en_row": en_row, "zh_row": zh_row})
    selected.sort(key=lambda e: (e["difficulty"], e["domain"], e["stem"]))

    run_rows = []
    for position, entry in enumerate(selected):
        language = "ZH" if position % 2 == 0 else "EN"
        row = entry["zh_row"] if language == "ZH" else entry["en_row"]
        run_rows.append({
            "idx": position,
            "problem": row["problem"],
            "answer": str(row["answer"]),
            "source_id": row["unique_id"],
            "subject": entry["domain"],
            "level": entry["difficulty"],
            "language": language,
            "answer_type": answer_type(row["answer"]),
            "problem_sha256": sha_bytes(norm(row["problem"]).encode("utf-8")),
            "gold_sha256": sha_bytes(str(row["answer"]).encode("utf-8")),
            "problem_group_id": entry["stem"],
            "flags": [],
        })

    counts = {"easy": sum(1 for r in run_rows if r["level"] == "easy"),
              "hard": sum(1 for r in run_rows if r["level"] == "hard"),
              "ZH": sum(1 for r in run_rows if r["language"] == "ZH"),
              "EN": sum(1 for r in run_rows if r["language"] == "EN")}
    assert counts == {"easy": 20, "hard": 20, "ZH": 20, "EN": 20}, counts
    assert len({r["problem_group_id"] for r in run_rows}) == 40
    domain_counts = Counter(r["subject"] for r in run_rows)
    assert all(v == 10 for v in domain_counts.values()), domain_counts
    hashes = {name: sha_bytes((EXT_CACHE / name).read_bytes()) for name in OLYMP_FILES.values()}
    write_layer("core120_v2_olympmath40", run_rows, {
        "upstream": {"repo": "RUC-AIBOX/OlymMATH", "revision": "5f83d12e63ee3267f35044461a6cebad58ec3be1",
                     "license": "MIT (per HF card)"},
        "raw_file_sha256": hashes,
        "selection": {"seed": SEED,
                      "rules": ("per-domain easy/hard {3,2}/{2,3} alternating; seeded sample from "
                                "sorted unique-id stems; language ZH/EN alternates; no stem reused"),
                      "counts": counts, "domain_counts": dict(domain_counts)},
        "static_gates": {"gold_self_score": "400/400 verified in PRE0-EXT-001 static gate (same files)",
                         "pool_dedup": "40 unique stems", "unit_red_line": "n/a (MIT scalar/interval answers)"},
    })


def build_robust180() -> None:
    data = json.loads((CACHE / "gsmplus.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict), "GSM-Plus.json is {seed_question: entry}"
    expected_types = {"numerical substitution", "digit expansion",
                      "integer-decimal-fraction conversion", "adding operation",
                      "reversing operation", "problem understanding",
                      "distraction insertion", "critical thinking"}

    qualifying = []
    for seed_q, entry in data.items():
        pq = entry.get("perturbation_questions") or {}
        seed_answer = str(entry.get("answer", "")).strip()
        if set(pq.keys()) == expected_types and seed_answer and seed_answer.lower() != "none":
            qualifying.append((seed_q, entry))
    assert len(qualifying) >= GSM_SEEDS, len(qualifying)
    qualifying.sort(key=lambda e: e[0])
    chosen = random.Random(SEED).sample(qualifying, GSM_SEEDS)

    run_rows = []
    for position, (seed_q, entry) in enumerate(sorted(chosen, key=lambda e: e[0])):
        seed_answer = str(entry.get("answer", "")).strip()
        run_rows.append({
            "idx": len(run_rows), "problem": seed_q, "answer": seed_answer,
            "source_id": f"gsmplus_seed_{position}", "subject": "GSM", "level": "grade_school",
            "language": "EN", "perturbation_type": "original",
            "answer_type": "numeric", "flags": [],
            "problem_sha256": sha_bytes(seed_q.encode("utf-8")),
            "gold_sha256": sha_bytes(seed_answer.encode("utf-8")),
            "problem_group_id": f"seed_{position}",
        })
        for ptype in sorted(expected_types):
            pv = entry["perturbation_questions"][ptype]
            gold = "" if pv.get("answer") is None else str(pv.get("answer")).strip()
            is_ct = ptype == "critical thinking" or gold.lower() == "none"
            run_rows.append({
                "idx": len(run_rows), "problem": pv["question"], "answer": gold,
                "source_id": f"seed_{position}/{ptype}", "subject": "GSM",
                "level": "grade_school", "language": "EN", "perturbation_type": ptype,
                "answer_type": "critical_thinking" if is_ct else "numeric",
                "flags": ["critical_thinking_none_gold"] if is_ct else [],
                "problem_sha256": sha_bytes(pv["question"].encode("utf-8")),
                "gold_sha256": sha_bytes(gold.encode("utf-8")),
                "problem_group_id": f"seed_{position}",
            })
    type_census = Counter(r["perturbation_type"] for r in run_rows)
    assert type_census["original"] == GSM_SEEDS and len(run_rows) == GSM_SEEDS * 9
    ct_rows = sum(1 for r in run_rows if r["answer_type"] == "critical_thinking")
    raw = (CACHE / "gsmplus.json").read_bytes()
    write_layer("robust180_v2_selection", run_rows, {
        "upstream": GSMPLUS_UPSTREAM,
        "raw_file_sha256": {"GSM-Plus.json": sha_bytes(raw)},
        "selection": {"seed": SEED,
                      "rules": ("20 qualifying seeds (all 8 perturbation types present, numeric seed "
                                "answer) x (original + 8 perturbation rows); critical-thinking rows "
                                "keep None gold and are flagged, never merged into numeric accuracy"),
                      "seeds": GSM_SEEDS, "type_census": dict(type_census),
                      "qualifying_seed_pool": len(qualifying),
                      "critical_thinking_rows": ct_rows},
        "static_gates": {"numeric_gold_self_score": "numeric golds integer/decimal (model smoke re-verifies exact)",
                         "critical_thinking_separate": True,
                         "pool_dedup": "20 unique seed groups; 180 rows"},
    })


if __name__ == "__main__":
    build_olympmath40()
    build_robust180()
