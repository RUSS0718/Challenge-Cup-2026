"""Freeze the three external hard-problem pools for official-like regression.

Pools (per 2026-09-05 user-approved design):
  - set_a_olymmath_hard : OlymMATH HARD, 88 unique problems, bilingual ZH+EN rows
  - set_b_aime          : AIME 2024 (fresh 22) + AIME 2025 (30) = 52 integer-answer items
  - set_c_hle_math      : HLE Math, 120 exactMatch text-only items (30 per domain)

Domains follow the official_like_hard20_v1 taxonomy:
  Algebra / Combinatorics / Geometry / Number Theory.

Rules frozen before any model call:
  - Items already used by docs/experiments/V4-HARD20-DUAL-001/official_like_hard20_v1
    (12 OlymMATH + 8 AIME 2024) are excluded so the pools stay disjoint from that window.
  - OlymMATH ZH-i and EN-i are translations of the same problem (verified 100/100 same
    gold answer), so they share problem_group_id "olym-hard-<i>"; sampling must pick at
    most one language per group per round.
  - HLE items: category=Math, answer_type=exactMatch, answer<=40 chars, no figure
    references, question<=2200 chars.  Domain labels are keyword rules + manual review,
    assigned blind to any model result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "tmp" / "external_hard_sets_staging"
OUT_DIR = ROOT / "sample_data" / "external_hard_sets"
HARD20_PATH = ROOT / "docs" / "experiments" / "V4-HARD20-DUAL-001" / "official_like_hard20_v1.jsonl"
SEED = 20260905
DOMAINS = ("Algebra", "Combinatorics", "Geometry", "Number Theory")
DOMAIN_ZH = {"Algebra": "代数", "Combinatorics": "组合", "Geometry": "几何", "Number Theory": "数论"}

OLYM_ZH_SUBJ = {"代数": "Algebra", "组合": "Combinatorics", "几何": "Geometry", "数论": "Number Theory"}

# Manual domain labels for the 52 AIME pool items, assigned by reading the problems
# before any model run (blind to model results).  Keys are AIME source ids.
AIME_DOMAINS_2024 = {
    "2024-I-1": "Algebra", "2024-I-2": "Algebra", "2024-I-3": "Combinatorics",
    "2024-I-4": "Combinatorics", "2024-I-6": "Combinatorics", "2024-I-7": "Algebra",
    "2024-I-8": "Geometry", "2024-I-11": "Combinatorics", "2024-I-12": "Algebra",
    "2024-I-14": "Geometry", "2024-I-15": "Geometry", "2024-II-1": "Combinatorics",
    "2024-II-2": "Combinatorics", "2024-II-3": "Combinatorics", "2024-II-5": "Geometry",
    "2024-II-6": "Number Theory", "2024-II-7": "Number Theory", "2024-II-9": "Combinatorics",
    "2024-II-10": "Geometry", "2024-II-13": "Algebra", "2024-II-14": "Number Theory",
    "2024-II-15": "Geometry",
}
AIME_DOMAINS_2025 = {
    "0": "Number Theory", "1": "Geometry", "2": "Combinatorics", "3": "Number Theory",
    "4": "Combinatorics", "5": "Geometry", "6": "Combinatorics", "7": "Algebra",
    "8": "Geometry", "9": "Combinatorics", "10": "Algebra", "11": "Geometry",
    "12": "Combinatorics", "13": "Geometry", "14": "Number Theory", "15": "Geometry",
    "16": "Number Theory", "17": "Combinatorics", "18": "Algebra", "19": "Geometry",
    "20": "Geometry", "21": "Combinatorics", "22": "Number Theory", "23": "Algebra",
    "24": "Combinatorics", "25": "Combinatorics", "26": "Geometry", "27": "Algebra",
    "28": "Geometry", "29": "Algebra",
}

HLE_FIGURE_RE = re.compile(r"figure|image|diagram|shown| pictured|plot|如图|append|picture|attached", re.I)
# Topics outside the four competition domains (analysis/ODE/numerical/set theory/
# category theory/algebraic geometry) are excluded regardless of keywords.
HLE_TOPIC_REJECT = re.compile(
    r"simpson|boundary[- ]value|franchis|ordinal|vietoris|totally bounded|coclassifier"
    r"|moduli space|simplex category|jointly exchangeable|homotopy|bordism|\bschemes?\b"
    r"|lotka|birkhoff|stable (curve|genus)|stable reduction|entropy|wasserstein|stieltjes"
    r"|maclaurin|physical|physics|pandora|pioneer|interstellar|decibel|\bdB\b"
    r"|heat equation|evolution equation|zhigalkin|\\omega_1|\\omega_2|zfc|cohen generic"
    r"|mad famil|non-standard model|almost disjoint|cremona"
    r"|stone[- ]cech|stokes|density funct|random sample|diversification|robotic arm"
    r"|differential equation|\\partial_t|\\partial_x", re.I)
HLE_RULES = [
    ("Number Theory", re.compile(
        r"prime|divisor|modulo|congruen|gcd|\\bmod|\\pmod|diophantine|palindrom"
        r"|divisib|integer (solution|root)|number theory|totient|continued fraction"
        r"|last digit|digits? of|\\bmod\b", re.I)),
    ("Combinatorics", re.compile(
        r"probability|combinat|number of ways|expected (number|value|time|length)"
        r"|tournament|coloring|permutat|\bgame\b|graph\b|pigeonhole|seating|coins?\b"
        r"|cards?\b|dice|shuffle|randomly|at random|ways to|arrang|pairing|matchsticks"
        r"|hypergraph|\btree\b|poset|partial order|lattice path|markov|random walk"
        r"|partition|tiling|solve the ( following)? puzzle", re.I)),
    ("Geometry", re.compile(
        r"triangle|circle|polygon|angle|tetrahedron|\bcube\b|sphere|polytope|tangent"
        r"|dodecahedron|icosahedron|\bvolume\b|\barea\b|knot\b|pack(ed|ing)|origami"
        r"|pentagon|hexagon|rectangle|concyclic|inscribed|circumscribed|cross\s?section"
        r"|polyhedron|geodesic|tessellat|crease|circumcircle|parallelogram|cone\b"
        r"|cylinder|ellipsoid|hyperbolic|manifold", re.I)),
    ("Algebra", re.compile(
        r"polynomial|equation|function|matrix|group\b|integral|sequence|limit"
        r"|logarithm|complex number|vector space|field\b|sum of|product of|inequalit"
        r"|functional|derivative|series|recursion|algebraic|subgroup|homomorphism"
        r"|elliptic curve|representation|module\b|ring\b|eigen|galois|monoid|category"
        r"|cartan|splitting field|dyadic|valuation", re.I)),
]
# Scoring: strong tokens (domain-defining) weigh 3, weak tokens weigh 1.
HLE_STRONG = {
    "Number Theory": re.compile(r"prime|divisor|diophantine|modulo|congruen|\\pmod|\\bmod\b|palindrom|totient|continued fraction|gcd", re.I),
    "Combinatorics": re.compile(r"probability|number of ways|combinat|expected (number|value)|tournament|pigeonhole|randomly|at random|markov|random walk|coloring|permutat", re.I),
    "Geometry": re.compile(r"triangle|circle|polygon|polytope|polyhedron|knot\b|pack(ed|ing)|tangent|inscribed|circumscribed|circumcircle|tetrahedron|geodesic|crease|origami|hyperbolic", re.I),
    "Algebra": re.compile(r"polynomial|matrix|subgroup|galois|splitting field|monoid|representation|eigen|vector space|homomorphism", re.I),
}

# Manual review pass 2 (2026-09-05, blind to any model result): id suffixes excluded
# for unjudgeable answer forms, story-framed ambiguity, suspicious golds, or topics
# outside the four competition domains.
HLE_EXCLUDE_SUFFIXES: set[str] = {
    # ALG
    "05346e5ea4b8", "9bf5b7cbb56d", "577c714fb716", "89b0dc078880", "7038d6740a23",
    "438591f287ae", "80f50716f9aa", "580f2ee8644f", "a5695f011626", "b4044ebf52ca",
    "7e0854d18d56", "660211cd8a70", "21bf390c5a30", "db734f219dc7", "e464f8bff2aa",
    "b99dae47a110", "f629cc9236ce", "2c47ce3a7e99", "611553f598c7",
    # GEOM
    "745d79e8d8d1", "7720158c1110", "7e77ea5cb0cc", "dfe3fe77e973", "6ff79cdd82af",
    "02717339d851", "b71df6f486c0", "795856a5d0d2", "719a829dfbb1", "d0d6f864f6ec",
    "6318b6b4e256",
    # NUMB
    "64c505f3a69a", "0eef1bf0f9bf", "e090a02938fd", "5c2ffdebd8f5", "d63bff1b0a06",
    "3d2ccc360e4e", "70920ad3bd63", "476bbcaa32ef", "e52b26e2bbc8", "5509e462323e",
    "543498bdcbed",
    # pass-3 refills
    "b2a5a3a4b0a9", "a1349f1ffad7", "1a3045f62fef", "c38041aa96a3", "04907be142ee",
    "5b5224374708", "e6e83ce51dfb", "927c36a3eb71",
    "611553f598d6",
    "6bb4709de947", "2c47ce3a7eb5", "a3b093402460", "cf1a8b9b0845", "f687ee9b06d1",
    "18fefce14c6f", "355a51195cdf", "c707d50d6012",
    "3e6934c83626", "8b9cc471012d",
    # pass-4 refills
    "7a255a42fba1", "63d6945e7b18", "34a448a5e299", "dd4f56302c06", "7f70a38b9f63",
    "3012645b0124", "6b38af8c204b",
    # pass-5 ALG refills
    "a8e96a06901a", "db9711ec68d6", "6182ef02efae", "918bd2e788b8",
}


def hle_answer_ok(answer: str) -> bool:
    """Reject answer forms that the official-style judge cannot fairly compare."""
    a = answer.strip().strip("$")
    if len(a) > 40:
        return False
    if re.search(r"\bnone\b", a, re.I):
        return False
    if "%" in a or "O(" in a or "\\oplus" in a or "\\in" in a:
        return False
    if re.fullmatch(r"(?i)(yes|no)([\s,;.]*(yes|no))*[.!?]?", a):
        return False  # pure decision answers
    if re.search(r"[∣‖′]", a):
        return False
    if re.fullmatch(r"[A-Z]{3,}", a):
        return False
    if re.fullmatch(r"[A-Za-z]{1,2}", a):
        return False  # bare symbol answers like "N"
    if re.match(r"^\s*[A-Za-z]\w*\s*\([^)]*\)\s*=", a):
        return False  # function-definition answers like "f(n) = ..."
    if re.fullmatch(r"[A-Za-z]{3,}", a):
        return False  # single word answers like "countable"
    if re.fullmatch(r"[A-Z]{1,2}\d+", a):
        return False  # coded answers like "Y10"
    if re.search(r"\(\s*[A-Za-z]\s*\)", a):
        return False  # multi-part markers like "(a) No; (b) 7"
    if any(a.endswith(s) for s in (".;",)):
        return False
    # prose: two word-ish runs separated by space
    if re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", a):
        return False
    # numeric list sanity: allow lists/tuples; reject comma forms that mix
    # thousands separators with list semantics ("12, 481043" = two answers)
    if re.search(r"\d,\s+\d", a) and not re.search(r"\d,\d{3}(?!\d)", a.replace(" ", "")):
        return False
    return True


# Manual domain overrides for keyword mislabels retained after review.
HLE_DOMAIN_OVERRIDES: dict[str, str] = {}

HLE_TARGET_PER_DOMAIN = 20
HLE_MIN_PER_DOMAIN = 12


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def hard20_used() -> tuple[set[str], set[str]]:
    rows = load_jsonl(HARD20_PATH)
    olymp = {r["source_id"] for r in rows if r["source_family"] == "OlymMATH"}
    aime = {r["source_id"] for r in rows if r["source_family"] == "AIME"}
    return olymp, aime


def classify_hle(question: str) -> str | None:
    """Score-based keyword buckets (strong=3, weak=1); ties resolved by rule order."""
    if HLE_TOPIC_REJECT.search(question):
        return None
    scores: list[tuple[int, int, str]] = []
    for priority, (domain, pattern) in enumerate(HLE_RULES):
        score = len(pattern.findall(question))
        if HLE_STRONG[domain].search(question):
            score += 3
        if score:
            scores.append((-score, priority, domain))
    if not scores:
        return None
    return min(scores)[2]


def build_olymmath_pool(used_olymp: set[str]) -> tuple[list[dict], dict]:
    zh = load_jsonl(STAGING / "OlymMATH-ZH-HARD.jsonl")
    en = load_jsonl(STAGING / "OlymMATH-EN-HARD.jsonl")
    if len(zh) != 100 or len(en) != 100:
        raise SystemExit(f"olymmath hard files must have 100 rows each, got {len(zh)}/{len(en)}")
    zmap = {r["unique_id"]: r for r in zh}
    emap = {r["unique_id"]: r for r in en}
    # bilingual pairing integrity
    for i in range(100):
        z, e = zmap[f"OlymMATH-HARD-{i}-ZH"], emap[f"OlymMATH-HARD-{i}-EN"]
        if z["answer"].strip() != e["answer"].strip():
            raise SystemExit(f"pairing broken at index {i}")
        if OLYM_ZH_SUBJ[z["subject"]] != e["subject"]:
            raise SystemExit(f"subject mismatch at index {i}")

    usable = [i for i in range(100) if f"OlymMATH-HARD-{i}-ZH" not in used_olymp
              and f"OlymMATH-HARD-{i}-EN" not in used_olymp]
    rng = random.Random(SEED)
    pool_idx = sorted(usable)
    rng.shuffle(pool_idx)
    per_domain: Counter = Counter()
    selected_groups: list[int] = []
    for i in pool_idx:
        subj = OLYM_ZH_SUBJ[zmap[f"OlymMATH-HARD-{i}-ZH"]["subject"]]
        if per_domain[subj] >= 22:  # 88 unique = 22 x 4 domains
            continue
        per_domain[subj] += 1
        selected_groups.append(i)
    selected_groups.sort()
    if len(selected_groups) != 88:
        raise SystemExit(f"expected 88 unique olymmath groups, got {len(selected_groups)}")

    rows: list[dict] = []
    for i in selected_groups:
        group = f"olym-hard-{i}"
        for lang, src in (("ZH", zmap), ("EN", emap)):
            r = src[f"OlymMATH-HARD-{i}-{lang}"]
            domain = OLYM_ZH_SUBJ.get(r["subject"], r["subject"])
            rows.append({
                "item_id": r["unique_id"],
                "set_id": "set_a_olymmath_hard",
                "source_family": "OlymMATH-HARD",
                "source_id": r["unique_id"],
                "problem_group_id": group,
                "language": lang,
                "domain": domain,
                "domain_zh": DOMAIN_ZH[domain],
                "answer_type": "exact",
                "problem": r["problem"].strip(),
                "answer": str(r["answer"]).strip(),
                "problem_sha256": sha256_text(r["problem"].strip()),
                "notes": "",
            })
    manifest = {
        "unique_groups": 88,
        "rows": len(rows),
        "domain_unique_groups": dict(sorted(per_domain.items())),
        "excluded_hard20_groups": sorted(used_olymp),
    }
    return rows, manifest


def build_aime_pool(used_aime: set[str]) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for fname, year_label in (("aime2024_30.jsonl", "AIME 2024"), ("aime2025_30.jsonl", "AIME 2025")):
        for r in load_jsonl(STAGING / fname):
            sid = str(r["source_id"])
            if sid in used_aime:
                continue
            domain = AIME_DOMAINS_2024.get(sid) or AIME_DOMAINS_2025.get(sid)
            if domain is None:
                raise SystemExit(f"missing domain label for {sid}")
            problem = r["problem"].strip()
            rows.append({
                "item_id": f"aime-{sid}",
                "set_id": "set_b_aime",
                "source_family": "AIME",
                "source_id": sid,
                "problem_group_id": "",
                "language": "EN",
                "domain": domain,
                "domain_zh": DOMAIN_ZH[domain],
                "answer_type": "integer",
                "problem": problem,
                "answer": str(r["answer"]).strip(),
                "problem_sha256": sha256_text(problem),
                "notes": "aime2025 items previously used in a format-level fidelity probe (STATEFUL-TAIL-V1-FIDELITY-001); selection itself is blind" if year_label == "AIME 2025" else "",
            })
    if len(rows) != 52:
        raise SystemExit(f"expected 52 aime rows, got {len(rows)}")
    per_domain = Counter(r["domain"] for r in rows)
    manifest = {
        "rows": len(rows),
        "domain_rows": dict(sorted(per_domain.items())),
        "excluded_hard20_ids": sorted(used_aime),
    }
    return rows, manifest


def build_hle_pool() -> tuple[list[dict], dict]:
    rows_raw = load_jsonl(STAGING / "hle_text_columns.jsonl")
    clean = []
    for r in rows_raw:
        if r["category"] != "Math" or r["answer_type"] != "exactMatch":
            continue
        answer = str(r["answer"]).strip()
        question = str(r["question"]).strip()
        if not answer or len(answer) > 40 or HLE_FIGURE_RE.search(question) or len(question) > 2200:
            continue
        if not hle_answer_ok(answer):
            continue
        if any(str(r["id"]).endswith(sfx) for sfx in HLE_EXCLUDE_SUFFIXES):
            continue
        domain = classify_hle(question)
        if domain is None:
            continue
        clean.append({"domain": domain, "row": r, "answer": answer, "question": question})

    per_domain_avail = Counter(c["domain"] for c in clean)
    short = {d: per_domain_avail.get(d, 0) for d in DOMAINS if per_domain_avail.get(d, 0) < HLE_TARGET_PER_DOMAIN}
    if any(v < HLE_MIN_PER_DOMAIN for v in short.values()):
        raise SystemExit(f"HLE domain below minimum {HLE_MIN_PER_DOMAIN}: {short}")

    by_domain: dict[str, list[dict]] = {d: [] for d in DOMAINS}
    for c in clean:
        by_domain[c["domain"]].append(c)
    rng = random.Random(SEED)
    for d in DOMAINS:
        by_domain[d].sort(key=lambda c: str(c["row"]["id"]))
        rng.shuffle(by_domain[d])

    rows: list[dict] = []
    for d in DOMAINS:
        take = min(HLE_TARGET_PER_DOMAIN, len(by_domain[d]))
        for c in by_domain[d][:take]:
            r = c["row"]
            rows.append({
                "item_id": f"hle-{r['id']}",
                "set_id": "set_c_hle_math",
                "source_family": "HLE-Math",
                "source_id": str(r["id"]),
                "problem_group_id": "",
                "language": "EN",
                "domain": d,
                "domain_zh": DOMAIN_ZH[d],
                "answer_type": "exactMatch",
                "problem": c["question"],
                "answer": c["answer"],
                "problem_sha256": sha256_text(c["question"]),
                "notes": f"hle raw_subject={r['raw_subject']}",
            })
    manifest = {
        "rows": len(rows),
        "clean_pool": len(clean),
        "domain_availability": dict(sorted(per_domain_avail.items())),
        "domain_rows": {d: min(HLE_TARGET_PER_DOMAIN, len(by_domain[d])) for d in DOMAINS},
        "answer_form_gate": "rejects prose/multi-decision/percent/list-with-letters/uppercase-run/function-def answers; official-style judging must be able to compare",
    }
    return rows, manifest


def static_gates(pools: dict[str, list[dict]], manifests: dict[str, dict]) -> None:
    all_shas: list[str] = []
    for set_id, rows in pools.items():
        shas = [r["problem_sha256"] for r in rows]
        if len(set(shas)) != len(shas):
            raise SystemExit(f"{set_id}: duplicate problems")
        all_shas.extend(shas)
        for r in rows:
            if not r["problem"].strip() or not str(r["answer"]).strip():
                raise SystemExit(f"{set_id}: incomplete {r['item_id']}")
            if r["domain"] not in DOMAINS:
                raise SystemExit(f"{set_id}: bad domain {r['domain']}")
    if len(set(all_shas)) != len(all_shas):
        raise SystemExit("cross-pool duplicate problems")
    a_rows = pools["set_a_olymmath_hard"]
    groups: dict[str, list[str]] = {}
    for r in a_rows:
        groups.setdefault(r["problem_group_id"], []).append(r["language"])
    for group, langs in groups.items():
        if sorted(langs) != ["EN", "ZH"]:
            raise SystemExit(f"group {group} must have exactly one ZH + one EN row: {langs}")
    b_rows = pools["set_b_aime"]
    if any(not re.fullmatch(r"-?\d+", r["answer"]) for r in b_rows):
        raise SystemExit("set_b answers must be integers")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write pools + manifest (default: review only)")
    parser.add_argument("--review", type=int, default=0, metavar="N", help="print N sample rows per pool for manual review")
    args = parser.parse_args()

    used_olymp, used_aime = hard20_used()
    olymp_rows, olymp_manifest = build_olymmath_pool(used_olymp)
    aime_rows, aime_manifest = build_aime_pool(used_aime)
    hle_rows, hle_manifest = build_hle_pool()

    pools = {
        "set_a_olymmath_hard": olymp_rows,
        "set_b_aime": aime_rows,
        "set_c_hle_math": hle_rows,
    }
    manifests = {"set_a": olymp_manifest, "set_b": aime_manifest, "set_c": hle_manifest}
    static_gates(pools, manifests)

    for set_id, rows in pools.items():
        print(f"== {set_id}: {len(rows)} rows")
        print("   domains:", dict(sorted(Counter(r["domain"] for r in rows).items())))
        print("   languages:", dict(sorted(Counter(r["language"] for r in rows).items())))
        if args.review:
            for r in rows[: args.review]:
                print(f"   [{r['item_id']}] ({r['domain']}/{r['language']}) {r['problem'][:90]} => {r['answer'][:30]}")
    print("manifests:", json.dumps(manifests, ensure_ascii=False))

    if not args.write:
        print("review mode: nothing written")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_shas = {}
    for fname in ("OlymMATH-ZH-HARD.jsonl", "OlymMATH-EN-HARD.jsonl",
                  "aime2024_30.jsonl", "aime2025_30.jsonl", "hle_text_columns.jsonl"):
        p = STAGING / fname
        source_shas[fname] = sha256_file(p) if p.exists() else None
    file_shas = {}
    for set_id, rows in pools.items():
        path = OUT_DIR / f"{set_id}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        file_shas[set_id] = sha256_file(path)
        print(f"wrote {path} ({len(rows)} rows) sha256={file_shas[set_id][:16]}…")
    manifest = {
        "pool_id": "external_hard_pools_v1",
        "frozen_date": "2026-09-05",
        "seed": SEED,
        "domains": list(DOMAINS),
        "difficulty_anchor": "official_like_hard20_v1 (OlymMATH HARD + AIME level), repo's established official-difficulty proxy",
        "sampling_rule": "per round: stratified by 4 domains with per-(set,domain) floor 2, remainder proportional; OlymMATH sampled at problem-group level with at most one language per group; seeded and recorded in each run manifest",
        "sources": {
            "OlymMATH": "RUC-AIBox/OlymMATH via hf-mirror, data/OlymMATH-{ZH,EN}-HARD.jsonl (HARD tier)",
            "AIME": "local frozen copies tmp/p1_data/run/aime2024_30.jsonl + aime2025_30.jsonl (2025 items also mirrored on HF)",
            "HLE": "cais/hle (official, gated) text columns fetched via ModelScope mirror AI-ModelScope/hle data/test-00000-of-00001.parquet",
        },
        "source_sha256": source_shas,
        "excluded_items": {
            "reason": "disjoint from V4-HARD20-DUAL-001 official_like_hard20_v1",
            "olymmath_groups": sorted(used_olymp),
            "aime_ids": sorted(used_aime),
        },
        "files": file_shas,
        "set_manifests": manifests,
    }
    (OUT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote MANIFEST.json")


if __name__ == "__main__":
    sys.exit(main())
