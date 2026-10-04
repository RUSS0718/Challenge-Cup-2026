"""Reusable definitions for bounded multi-round agent evaluations.

This module owns dataset normalization, round specifications, profile construction,
and failure aggregation.  Network calls remain in the CLI runner so unit tests
can exercise the experiment contract without contacting the model endpoint.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from reasoning_agent.profiles import build_profile_config


@dataclass(frozen=True)
class RoundSpec:
    """Describe one reproducible experiment round and its selected records."""

    round_id: str
    profile: str
    dataset: str
    keys: tuple[Any, ...]


DATASET_PATHS: dict[str, Path] = {
    "eval": Path("reasoning_agent/error_notebook/eval_112.json"),
    "public": Path("sample_data/public_regression_112.jsonl"),
    "complex": Path("sample_data/complex_capability_freeze_48.jsonl"),
    "medium": Path("sample_data/medium_capability_freeze_60.jsonl"),
    "hard20": Path("docs/experiments/V4-HARD20-DUAL-001/official_like_hard20_v1.jsonl"),
    "fresh_confirmation": Path("sample_data/arm_v217_fresh_confirmation_25.jsonl"),
    "external_olymmath": Path("sample_data/external_hard_sets/set_a_olymmath_hard.jsonl"),
    "external_aime": Path("sample_data/external_hard_sets/set_b_aime.jsonl"),
    "external_hle": Path("sample_data/external_hard_sets/set_c_hle_math.jsonl"),
}


def default_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten fixed rounds spanning hard, public, and external-like questions."""

    return (
        RoundSpec("R01", "arm-v2.1.4-cfr", "eval", (0, 1, 2, 3, 4)),
        RoundSpec("R02", "cfr-long", "eval", (5, 6, 7, 8, 9)),
        RoundSpec("R03", "cfr-evidence", "eval", (0, 1, 2, 3, 4)),
        RoundSpec("R04", "arm-v2.1.4-off", "eval", (5, 6, 7, 8, 9)),
        RoundSpec("R05", "typed-capsule", "eval", (0, 1, 2, 3, 4)),
        RoundSpec("R06", "fsdf", "public", (5000, 5001, 5002, 5003, 5004)),
        RoundSpec("R07", "cfr-long", "public", (5005, 5006, 5007, 5008, 5009)),
        RoundSpec(
            "R08",
            "cfr-long-evidence",
            "hard20",
            (
                "OlymMATH-HARD-12-ZH", "OlymMATH-HARD-78-ZH", "OlymMATH-HARD-69-EN",
                "OlymMATH-HARD-49-ZH", "OlymMATH-HARD-14-EN",
            ),
        ),
        RoundSpec(
            "R09",
            "arm-v2.1.4-adaptive",
            "hard20",
            (
                "OlymMATH-HARD-56-EN", "OlymMATH-HARD-9-ZH", "OlymMATH-HARD-77-ZH",
                "OlymMATH-HARD-3-EN", "OlymMATH-HARD-70-ZH",
            ),
        ),
        RoundSpec(
            "R10",
            "cfr-long",
            "hard20",
            ("OlymMATH-HARD-62-EN", "OlymMATH-HARD-16-EN", "2024-I-9", "2024-I-5", "2024-II-11"),
        ),
    )


def recovery_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten paired rounds for the v2.1.5 bounded-tail hypothesis.

    Each candidate round is immediately followed by the same-profile v2.1.4
    baseline on the same five records.  The plan spans hard20, eval-112, and
    public regression data without using item-specific routing.
    """
    return (
        RoundSpec("B01", "arm-v2.1.5-bounded-tail", "hard20", (
            "OlymMATH-HARD-12-ZH", "OlymMATH-HARD-78-ZH", "OlymMATH-HARD-69-EN",
            "OlymMATH-HARD-49-ZH", "OlymMATH-HARD-14-EN",
        )),
        RoundSpec("B02", "arm-v2.1.4-cfr", "hard20", (
            "OlymMATH-HARD-12-ZH", "OlymMATH-HARD-78-ZH", "OlymMATH-HARD-69-EN",
            "OlymMATH-HARD-49-ZH", "OlymMATH-HARD-14-EN",
        )),
        RoundSpec("B03", "arm-v2.1.5-bounded-tail", "hard20", (
            "OlymMATH-HARD-56-EN", "OlymMATH-HARD-9-ZH", "OlymMATH-HARD-77-ZH",
            "OlymMATH-HARD-3-EN", "OlymMATH-HARD-70-ZH",
        )),
        RoundSpec("B04", "arm-v2.1.4-cfr", "hard20", (
            "OlymMATH-HARD-56-EN", "OlymMATH-HARD-9-ZH", "OlymMATH-HARD-77-ZH",
            "OlymMATH-HARD-3-EN", "OlymMATH-HARD-70-ZH",
        )),
        RoundSpec("B05", "arm-v2.1.5-bounded-tail", "hard20", (
            "OlymMATH-HARD-62-EN", "OlymMATH-HARD-16-EN", "2024-I-9",
            "2024-I-5", "2024-II-11",
        )),
        RoundSpec("B06", "arm-v2.1.4-cfr", "hard20", (
            "OlymMATH-HARD-62-EN", "OlymMATH-HARD-16-EN", "2024-I-9",
            "2024-I-5", "2024-II-11",
        )),
        RoundSpec("B07", "arm-v2.1.5-bounded-tail", "eval", (10, 11, 12, 13, 14)),
        RoundSpec("B08", "arm-v2.1.4-cfr", "eval", (10, 11, 12, 13, 14)),
        RoundSpec("B09", "arm-v2.1.5-bounded-tail", "public", (5010, 5011, 5012, 5013, 5014)),
        RoundSpec("B10", "arm-v2.1.4-cfr", "public", (5010, 5011, 5012, 5013, 5014)),
    )


def missing_candidate_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten paired rounds for v2.1.6 missing-candidate recovery.

    The candidate is paired with the unchanged v2.1.4 CFR profile on the same
    records.  The selected records are disjoint from the v2.1.5 recovery
    window and cover complex, medium, and official-like hard prompts.
    """
    return (
        RoundSpec("C01", "arm-v2.1.6-missing-candidate", "complex", (6000, 6001, 6002, 6003, 6004)),
        RoundSpec("C02", "arm-v2.1.4-cfr", "complex", (6000, 6001, 6002, 6003, 6004)),
        RoundSpec("C03", "arm-v2.1.6-missing-candidate", "complex", (6005, 6006, 6007, 6008, 6009)),
        RoundSpec("C04", "arm-v2.1.4-cfr", "complex", (6005, 6006, 6007, 6008, 6009)),
        RoundSpec("C05", "arm-v2.1.6-missing-candidate", "medium", (6100, 6101, 6102, 6103, 6104)),
        RoundSpec("C06", "arm-v2.1.4-cfr", "medium", (6100, 6101, 6102, 6103, 6104)),
        RoundSpec("C07", "arm-v2.1.6-missing-candidate", "medium", (6200, 6201, 6202, 6203, 6204)),
        RoundSpec("C08", "arm-v2.1.4-cfr", "medium", (6200, 6201, 6202, 6203, 6204)),
        RoundSpec("C09", "arm-v2.1.6-missing-candidate", "hard20", (
            "2024-I-13", "2024-II-8", "2024-II-12", "2024-I-10", "2024-II-4",
        )),
        RoundSpec("C10", "arm-v2.1.4-cfr", "hard20", (
            "2024-I-13", "2024-II-8", "2024-II-12", "2024-I-10", "2024-II-4",
        )),
    )


def structured_confirmation_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten paired rounds for the v2.1.7 incumbent-only hypothesis.

    The five groups use a fresh 25-item set and a common 1,024-token pressure
    budget.  Only the candidate profile changes the second-call policy; the
    baseline keeps the v2.1.4 CFR implementation and the same item order.
    """
    groups = (
        ("fresh_confirm_01", "fresh_confirm_02", "fresh_confirm_03", "fresh_confirm_04", "fresh_confirm_05"),
        ("fresh_confirm_06", "fresh_confirm_07", "fresh_confirm_08", "fresh_confirm_09", "fresh_confirm_10"),
        ("fresh_confirm_11", "fresh_confirm_12", "fresh_confirm_13", "fresh_confirm_14", "fresh_confirm_15"),
        ("fresh_confirm_16", "fresh_confirm_17", "fresh_confirm_18", "fresh_confirm_19", "fresh_confirm_20"),
        ("fresh_confirm_21", "fresh_confirm_22", "fresh_confirm_23", "fresh_confirm_24", "fresh_confirm_25"),
    )
    specs: list[RoundSpec] = []
    for index, keys in enumerate(groups, start=1):
        specs.extend(
            (
                RoundSpec(f"V{index * 2 - 1:02d}", "arm-v2.1.7-structured-confirmation", "fresh_confirmation", keys),
                RoundSpec(f"V{index * 2:02d}", "arm-v2.1.4-cfr", "fresh_confirmation", keys),
            )
        )
    return tuple(specs)


def compact_finalizer_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten paired rounds for the v2.1.8 truncation hypothesis.

    The window uses five disjoint five-item groups from the internal eval set,
    complex and medium freezes, and public regression.  The candidate keeps
    the long primary budget but replaces the second call after an incomplete
    primary with a 2,048-token answer-only finalizer; the baseline uses the
    existing long CFR profile on the same rows.
    """
    groups = (
        ("eval", (15, 16, 17, 18, 19)),
        ("eval", (20, 21, 22, 23, 24)),
        ("complex", (6010, 6011, 6012, 6013, 6014)),
        ("medium", (6105, 6106, 6107, 6108, 6109)),
        ("public", (5020, 5021, 5022, 5023, 5024)),
    )
    specs: list[RoundSpec] = []
    for index, (dataset, keys) in enumerate(groups, start=1):
        specs.extend(
            (
                RoundSpec(f"W{index * 2 - 1:02d}", "arm-v2.1.8-compact-finalizer", dataset, keys),
                RoundSpec(f"W{index * 2:02d}", "cfr-long", dataset, keys),
            )
        )
    return tuple(specs)


def external_pressure_round_specs() -> tuple[RoundSpec, ...]:
    """Return ten paired external hard-set rounds under a primary pressure budget.

    The candidate and baseline share a 1,024-token primary request so that any
    difference is attributable to the v2.1.8 answer-only finalizer.  The five
    paired groups are disjoint within each frozen external pool and cover
    OlymMATH, AIME, and HLE math records.
    """
    groups = (
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-0-ZH", "OlymMATH-HARD-6-ZH",
                "OlymMATH-HARD-1-ZH", "OlymMATH-HARD-10-ZH",
                "OlymMATH-HARD-2-EN",
            ),
        ),
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-8-EN", "OlymMATH-HARD-5-EN",
                "OlymMATH-HARD-11-EN", "OlymMATH-HARD-4-ZH",
                "OlymMATH-HARD-13-EN",
            ),
        ),
        (
            "external_aime",
            (
                "aime-2024-I-4", "aime-2024-I-12", "aime-2024-I-8",
                "aime-2024-II-6", "aime-2024-I-11",
            ),
        ),
        (
            "external_hle",
            (
                "hle-67486cd4501c568127ed52d4",
                "hle-67053981f8ad2742675478b4",
                "hle-66ff68bec7e8ec38a6188f9c",
                "hle-670df2e172288739ca35e0e1",
                "hle-671ada4eed3d54e87368bc78",
            ),
        ),
        (
            "external_hle",
            (
                "hle-673b5fdff0294e2cbdb5bebb",
                "hle-6742f485e9256150e88912f1",
                "hle-675853c6101f66905f003073",
                "hle-6754baec618d187bb3362936",
                "hle-6720ca4b696f86db458bcfe9",
            ),
        ),
    )
    specs: list[RoundSpec] = []
    for index, (dataset, keys) in enumerate(groups, start=1):
        specs.extend(
            (
                RoundSpec(
                    f"X{index * 2 - 1:02d}",
                    "arm-v2.1.8-external-pressure",
                    dataset,
                    keys,
                ),
                RoundSpec(f"X{index * 2:02d}", "cfr-external-pressure", dataset, keys),
            )
        )
    return tuple(specs)


def external_pressure_replication_round_specs() -> tuple[RoundSpec, ...]:
    """Return an independent ten-round replication on disjoint hard-set items.

    The profiles and budgets match :func:`external_pressure_round_specs`, but
    every selected item is outside that first window so a second result is not
    a rerun of the same records.
    """
    groups = (
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-7-ZH", "OlymMATH-HARD-23-EN",
                "OlymMATH-HARD-24-ZH", "OlymMATH-HARD-25-EN",
                "OlymMATH-HARD-19-ZH",
            ),
        ),
        (
            "external_olymmath",
            (
                "OlymMATH-HARD-15-EN", "OlymMATH-HARD-31-ZH",
                "OlymMATH-HARD-27-EN", "OlymMATH-HARD-26-ZH",
                "OlymMATH-HARD-22-EN",
            ),
        ),
        (
            "external_aime",
            (
                "aime-2024-I-3", "aime-2024-I-2", "aime-2024-I-15",
                "aime-2024-II-7", "aime-2024-II-3",
            ),
        ),
        (
            "external_hle",
            (
                "hle-6778bdd88f6679541aac6b6a",
                "hle-673fb49e9c9d0a5bc88bf8be",
                "hle-66ecb2eb54baa602e636a457",
                "hle-672067805681ce2b6f5a08a7",
                "hle-670205330fb89862bc1d87d2",
            ),
        ),
        (
            "external_hle",
            (
                "hle-673852c82e5179091a7648e8",
                "hle-66f9a1ed4f798b651f6d3c8e",
                "hle-66f2e9b4d18ac34db32642b7",
                "hle-66f708eec8903a7f2c03edbe",
                "hle-67259a76e7601df8b19a9e2a",
            ),
        ),
    )
    specs: list[RoundSpec] = []
    for index, (dataset, keys) in enumerate(groups, start=1):
        specs.extend(
            (
                RoundSpec(
                    f"Y{index * 2 - 1:02d}",
                    "arm-v2.1.8-external-pressure",
                    dataset,
                    keys,
                ),
                RoundSpec(f"Y{index * 2:02d}", "cfr-external-pressure", dataset, keys),
            )
        )
    return tuple(specs)


def load_scored_rows(path: Path) -> list[dict[str, Any]]:
    """Load JSON or JSONL rows while retaining a stable string item identifier."""

    if path.suffix.casefold() == ".jsonl":
        payload: Any = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        payload = payload.get("records", payload.get("items", payload))
    if not isinstance(payload, list):
        raise ValueError(f"dataset_must_be_list:{path}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, Mapping):
            raise ValueError(f"dataset_row_must_be_object:{path}")
        raw_key = row.get("idx") if row.get("idx") is not None else row.get("item_id")
        problem = row.get("problem")
        answer = row.get("answer")
        if raw_key is None or not isinstance(problem, str) or not problem.strip():
            raise ValueError(f"dataset_row_identity_invalid:{path}")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"dataset_row_answer_invalid:{path}")
        item_id = str(raw_key)
        if item_id in seen:
            raise ValueError(f"dataset_duplicate_item:{item_id}")
        seen.add(item_id)
        normalized = dict(row)
        normalized["item_id"] = item_id
        normalized["problem"] = problem
        normalized["answer"] = answer
        rows.append(normalized)
    return rows


def select_rows(rows: Sequence[Mapping[str, Any]], keys: Sequence[Any]) -> list[dict[str, Any]]:
    """Select rows in the requested order, failing if a key is absent."""

    indexed = {str(row.get("item_id")): row for row in rows}
    selected: list[dict[str, Any]] = []
    for key in keys:
        item = indexed.get(str(key))
        if item is None:
            raise KeyError(f"dataset_item_missing:{key}")
        selected.append(dict(item))
    return selected


def build_round_config(spec: RoundSpec) -> Any:
    """Build one isolated profile, including explicit token-budget candidates."""

    if spec.profile == "cfr-long":
        return replace(
            build_profile_config("arm-v2.1.4-cfr"),
            harness_attempt_a_max_tokens=8_192,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    if spec.profile == "cfr-evidence":
        return replace(
            build_profile_config("arm-v2.1.4-cfr"),
            arm_trust_policy="evidence",
        )
    if spec.profile == "cfr-long-evidence":
        return replace(
            build_profile_config("arm-v2.1.4-cfr"),
            arm_trust_policy="evidence",
            harness_attempt_a_max_tokens=8_192,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    if spec.profile == "typed-capsule":
        return replace(
            build_profile_config("arm-v2.1.4-cfr"),
            enable_constraint_fit_harness=False,
            enable_arm_harness=False,
            enable_fork_select_deepen_finish=False,
            enable_typed_answer_capsule=True,
            max_model_calls=2,
            max_tokens=4_096,
            capsule_retry_max_tokens=2_048,
        )
    if spec.profile == "arm-v2.1.6-missing-candidate":
        return build_profile_config(spec.profile)
    if spec.profile == "arm-v2.1.8-compact-finalizer":
        return replace(
            build_profile_config(spec.profile),
            harness_attempt_a_max_tokens=8_192,
            harness_attempt_b_max_tokens=2_048,
            harness_total_token_budget=16_384,
        )
    if spec.profile == "arm-v2.1.8-external-pressure":
        return replace(
            build_profile_config("arm-v2.1.8-compact-finalizer"),
            harness_attempt_a_max_tokens=1_024,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    if spec.profile == "cfr-external-pressure":
        return replace(
            build_profile_config("arm-v2.1.4-cfr"),
            harness_attempt_a_max_tokens=1_024,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    if spec.dataset == "fresh_confirmation":
        return replace(
            build_profile_config(spec.profile),
            harness_attempt_a_max_tokens=1_024,
            harness_attempt_b_max_tokens=1_024,
            harness_total_token_budget=8_192,
        )
    return build_profile_config(spec.profile)


def _latest_summary(trace: Any) -> Mapping[str, Any]:
    """Return the most recent ARM summary from a bounded trace."""

    if not isinstance(trace, list):
        return {}
    return next(
        (
            entry
            for entry in reversed(trace)
            if isinstance(entry, Mapping) and entry.get("stage") == "arm_v2_summary"
        ),
        {},
    )


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate score, truncation, parser, and final-failure evidence."""

    outcomes = Counter(str(row.get("outcome", "invalid")) for row in rows)
    verdicts = Counter(str(row.get("verdict", "unknown")) for row in rows)
    finish_reasons = Counter(
        str(reason)
        for row in rows
        for reason in row.get("finish_reasons", [])
    )
    failure_reasons: Counter[str] = Counter()
    parser_reasons: Counter[str] = Counter()
    finalizer_reasons: Counter[str] = Counter()
    compact_finalizer_activations = 0
    truncation_count = 0
    for row in rows:
        summary = _latest_summary(row.get("trace"))
        reason = summary.get("final_failure_reason")
        if reason:
            failure_reasons[str(reason)] += 1
        for key in ("primary_parse", "second_parse"):
            parse = summary.get(key)
            if isinstance(parse, Mapping) and parse.get("reason"):
                parser_reasons[str(parse["reason"])] += 1
        row_truncations = sum(
            1
            for reason in row.get("finish_reasons", [])
            if str(reason) in {"length", "max_tokens", "truncated"}
        )
        truncation_count += row_truncations
        for entry in row.get("trace", []) if isinstance(row.get("trace"), list) else []:
            if not isinstance(entry, Mapping) or entry.get("stage") != "compact_finalizer":
                continue
            compact_finalizer_activations += 1
            reason = entry.get("reason")
            if reason:
                finalizer_reasons[str(reason)] += 1
    decided = outcomes.get("correct", 0) + outcomes.get("incorrect", 0)
    total_calls = sum(int(row.get("model_calls", 0) or 0) for row in rows)
    total_finish = sum(finish_reasons.values())
    return {
        "records": len(rows),
        "outcome_counts": dict(outcomes),
        "verdict_counts": dict(verdicts),
        "correct": outcomes.get("correct", 0),
        "incorrect": outcomes.get("incorrect", 0),
        "invalid": outcomes.get("invalid", 0),
        "model_errors": sum(bool(row.get("model_error")) for row in rows),
        "total_model_calls": total_calls,
        "average_model_calls": total_calls / len(rows) if rows else 0.0,
        "finish_reason_counts": dict(finish_reasons),
        "truncation_count": truncation_count,
        "truncation_rate": (
            sum(count for reason, count in finish_reasons.items() if reason in {"length", "max_tokens", "truncated"})
            / total_finish
            if total_finish
            else 0.0
        ),
        "failure_reason_counts": dict(failure_reasons),
        "parser_reason_counts": dict(parser_reasons),
        "compact_finalizer_activations": compact_finalizer_activations,
        "compact_finalizer_trigger_reason_counts": dict(finalizer_reasons),
        "decided_accuracy": outcomes.get("correct", 0) / decided if decided else None,
    }


def format_matrix_summary(aggregate: Mapping[str, Any], artifact_dir: Path | str) -> str:
    """Format a matrix result as a short report with durable artifact paths."""

    root = Path(artifact_dir)
    return "\n".join(
        [
            "matrix: "
            f"id={aggregate.get('run_id') or 'unknown'} "
            f"status={aggregate.get('status') or 'unknown'} "
            f"scope={aggregate.get('evaluation_scope') or 'unknown'}",
            "results: "
            f"rounds={aggregate.get('round_count', 0)} "
            f"records={aggregate.get('total_records', 0)} "
            f"correct={aggregate.get('correct', 0)} "
            f"incorrect={aggregate.get('incorrect', 0)} "
            f"invalid={aggregate.get('invalid', 0)} "
            f"model_errors={aggregate.get('model_errors', 0)} "
            f"calls={aggregate.get('total_model_calls', 0)} "
            f"truncations={aggregate.get('truncation_count', 0)} "
            f"finalizer_activations={aggregate.get('compact_finalizer_activations', 0)}",
            f"artifacts: {root}",
            f"aggregate: {root / 'aggregate.json'}",
            f"summary: {root / 'result.md'}",
        ]
    )


__all__ = [
    "DATASET_PATHS",
    "RoundSpec",
    "build_round_config",
    "default_round_specs",
    "missing_candidate_round_specs",
    "structured_confirmation_round_specs",
    "recovery_round_specs",
    "external_pressure_round_specs",
    "external_pressure_replication_round_specs",
    "load_scored_rows",
    "select_rows",
    "summarize_rows",
    "format_matrix_summary",
]
