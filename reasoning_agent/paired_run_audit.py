"""Validate paired evidence before an experiment can report a passing gate.

This audit checks recorded provenance and selection without inventing missing
configuration or treating a dirty checkout as a reproducible release tree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from reasoning_agent.manifest_schema import validate_comparison


def audit_paired_round(
    manifests: Sequence[Mapping[str, Any]],
    arms: Sequence[Sequence[Mapping[str, Any]]],
    *,
    expected_ids: Sequence[str],
    profiles: Sequence[str],
    dataset_id: str,
    dataset_sha256: str,
) -> list[str]:
    """Require complete, clean, identically sourced arms with the frozen selection."""
    errors = validate_comparison(manifests)
    if len(manifests) != 2 or len(arms) != 2:
        return errors + ["missing:two_paired_arms"]
    expected = list(expected_ids)
    if not expected or len(set(expected)) != len(expected):
        errors.append("invalid:expected_selection")
    for index, (manifest, rows) in enumerate(zip(manifests, arms)):
        prefix = f"arm[{index}]"
        for field, value in (
            ("status", "completed"),
            ("config_selector", profiles[index]),
            ("dataset_id", dataset_id),
            ("dataset_sha256", dataset_sha256),
            ("selected_items", expected),
            ("records", len(expected)),
            ("gold_passed_to_agent", False),
        ):
            if field not in manifest or manifest[field] != value:
                errors.append(f"{prefix}:mismatch:{field}")
        if [str(row.get("item_id", "")) for row in rows] != expected:
            errors.append(f"{prefix}:mismatch:answer_selection")
    if errors:
        return errors
    for index, (candidate, baseline) in enumerate(zip(arms[0], arms[1])):
        for field in ("problem_sha256", "expected_answer_sha256"):
            if not candidate.get(field) or candidate[field] != baseline.get(field):
                errors.append(f"record[{index}]:mismatch:{field}")
    return errors
