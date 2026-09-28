"""Small pure helpers for ARM-Harness v2.1 telemetry and paired attribution."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


def parse_diagnostics(parsed: Any, candidates: Iterable[Any]) -> dict[str, Any]:
    """Return bounded parser status fields without retaining model text."""
    items = list(candidates)
    return {
        "status": str(getattr(parsed, "status", "missing")),
        "reason": str(
            getattr(parsed, "reason_summary", getattr(parsed, "reason", "unknown"))
        )[:240],
        "truncated": bool(getattr(parsed, "truncated", False)),
        "candidate_count": len(items),
    }


def candidate_diagnostics(candidate: Any) -> dict[str, Any] | None:
    """Return the candidate fields required to explain a final decision."""
    if candidate is None:
        return None
    return {
        "candidate_id": str(getattr(candidate, "candidate_id", "")),
        "value": str(
            getattr(candidate, "normalized_value", "") or getattr(candidate, "value", "")
        )[:256],
        "answer_type": str(getattr(candidate, "answer_type", "unknown")),
        "structural_validity": str(getattr(candidate, "structural_validity", "unassessed")),
        "answer_complete": bool(getattr(candidate, "answer_complete", True)),
        "answer_complete_reason": str(getattr(candidate, "answer_complete_reason", ""))[:240],
        "trust": str(getattr(candidate, "trust_confidence", "unknown")),
        "trust_reason": str(getattr(candidate, "trust_reason", ""))[:240],
    }


def pair_relation(candidate_a: Any, candidate_b: Any) -> str:
    """Classify two candidate outcomes before resolver selection."""
    valid_a = candidate_a is not None
    valid_b = candidate_b is not None
    if valid_a and valid_b:
        from reasoning_agent.harness_contracts import value_equivalence

        return "EQUIVALENT" if value_equivalence(candidate_a.value, candidate_b.value) == "EQUIVALENT" else "CONFLICT"
    if valid_a:
        return "A_ONLY"
    if valid_b:
        return "B_ONLY"
    return "NO_VALID_PAIR"


def second_sample_outcome(relation: str) -> str:
    """Map a pair relation to a runtime-safe, gold-independent outcome."""
    if relation == "EQUIVALENT":
        return "confirmed"
    if relation == "CONFLICT":
        return "introduced_conflict"
    return "no_value"


def transition_label(baseline: Any, candidate: Any) -> str:
    """Normalize paired verdicts to one of the nine required transitions."""
    def normalize(value: Any) -> str:
        text = str(value or "invalid").casefold()
        return text if text in {"correct", "incorrect", "invalid"} else "invalid"

    return f"{normalize(baseline)} → {normalize(candidate)}"


def paired_attribution(
    rows: Iterable[Mapping[str, Any]],
    baseline_name: str,
    candidate_name: str,
) -> dict[str, Any]:
    """Build item-level baseline/candidate transitions and source evidence."""
    by_arm: dict[str, dict[Any, Mapping[str, Any]]] = {
        baseline_name: {},
        candidate_name: {},
    }
    for row in rows:
        arm = row.get("variant")
        if arm in by_arm:
            by_arm[arm][row.get("idx")] = row
    if set(by_arm[baseline_name]) != set(by_arm[candidate_name]):
        raise ValueError("paired_items_must_match")
    matrix = Counter(
        transition_label(
            by_arm[baseline_name][idx].get("verdict"),
            by_arm[candidate_name][idx].get("verdict"),
        )
        for idx in by_arm[baseline_name]
    )
    labels = [f"{left} → {right}" for left in ("correct", "incorrect", "invalid") for right in ("correct", "incorrect", "invalid")]
    items = []
    for idx in by_arm[baseline_name]:
        baseline = by_arm[baseline_name][idx]
        candidate = by_arm[candidate_name][idx]
        items.append(
            {
                "idx": idx,
                "baseline_result": baseline.get("verdict", "invalid"),
                "candidate_result": candidate.get("verdict", "invalid"),
                "transition": transition_label(baseline.get("verdict"), candidate.get("verdict")),
                "candidate_final_source": candidate.get("final_source"),
            }
        )
    return {
        "transition_matrix": {label: matrix.get(label, 0) for label in labels},
        "item_attribution": items,
    }


__all__ = [
    "candidate_diagnostics",
    "paired_attribution",
    "pair_relation",
    "parse_diagnostics",
    "second_sample_outcome",
    "transition_label",
]
