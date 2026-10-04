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
    for row in rows:
        summary = _latest_summary(row.get("trace"))
        reason = summary.get("final_failure_reason")
        if reason:
            failure_reasons[str(reason)] += 1
        for key in ("primary_parse", "second_parse"):
            parse = summary.get(key)
            if isinstance(parse, Mapping) and parse.get("reason"):
                parser_reasons[str(parse["reason"])] += 1
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
        "truncation_rate": (
            sum(count for reason, count in finish_reasons.items() if reason in {"length", "max_tokens", "truncated"})
            / total_finish
            if total_finish
            else 0.0
        ),
        "failure_reason_counts": dict(failure_reasons),
        "parser_reason_counts": dict(parser_reasons),
        "decided_accuracy": outcomes.get("correct", 0) / decided if decided else None,
    }


__all__ = [
    "DATASET_PATHS",
    "RoundSpec",
    "build_round_config",
    "default_round_specs",
    "missing_candidate_round_specs",
    "recovery_round_specs",
    "load_scored_rows",
    "select_rows",
    "summarize_rows",
]
