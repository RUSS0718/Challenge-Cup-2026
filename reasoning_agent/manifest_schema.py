"""Canonical run provenance and fail-closed comparison of evaluation results.

Legacy aliases are readable, but missing scope remains unknown. Strict checks
operate on recorded fields and never invent evidence for historical runs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

MANIFEST_SCHEMA_VERSION = 2
EVALUATION_SCOPES = frozenset({"official", "proxy", "local_replay", "smoke", "diagnostic"})
REQUIRED_FIELDS = (
    "run_id", "config_selector", "dataset_id", "git_commit", "dataset_sha256",
    "started_at", "status", "evaluation_scope", "official_evaluation",
    "working_tree_dirty",
)


def normalise_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Read legacy aliases without labelling an unknown run as a local replay."""
    data = dict(manifest)
    aliases = {
        "config_selector": ("config", "profile", "submission_mode"),
        "dataset_id": ("dataset", "dataset_path", "input_file"),
        "git_commit": ("git_head",),
        "dataset_sha256": ("dataset_hash", "source_dataset_sha256"),
        "started_at": ("started_at_utc",),
        "working_tree_dirty": ("dirty_tree",),
    }
    for canonical, names in aliases.items():
        if data.get(canonical) is None:
            for name in names:
                if data.get(name) is not None:
                    data[canonical] = data[name]
                    break
    data.setdefault("manifest_schema_version", 1)
    data.setdefault("evaluation_scope", "unknown")
    data.setdefault("official_evaluation", None)
    return data


def validate_manifest(manifest: Mapping[str, Any], *, strict: bool = False) -> list[str]:
    """Reject incomplete or contradictory provenance before using run scores.

    Non-strict mode reads legacy aliases; strict mode requires explicitly
    recorded schema-v2 fields, valid hashes, scope and a clean worktree.
    """
    if not isinstance(manifest, Mapping):
        return ["invalid:manifest_must_be_object"]
    data = dict(manifest) if strict else normalise_manifest(manifest)
    errors: list[str] = []
    if strict and data.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("invalid:manifest_schema_version_requires_2")
    fields = REQUIRED_FIELDS if strict else ("run_id",)
    for field in fields:
        if field not in data or data[field] is None or data[field] == "":
            errors.append(f"missing:{field}")
    scope = data.get("evaluation_scope")
    if scope not in EVALUATION_SCOPES and (strict or scope != "unknown"):
        errors.append(f"invalid:evaluation_scope={scope!r}")
    official = data.get("official_evaluation")
    if official is not None and not isinstance(official, bool):
        errors.append("invalid:official_evaluation_must_be_bool")
    if official is True and scope != "official":
        errors.append("invalid:official_evaluation_requires_official_scope")
    elif scope in EVALUATION_SCOPES and official is not None and official != (scope == "official"):
        errors.append("invalid:official_evaluation_scope_mismatch")
    if strict:
        for key, pattern in (("git_commit", r"[0-9a-f]{40}|[0-9a-f]{64}"),
                             ("dataset_sha256", r"[0-9a-f]{64}")):
            if data.get(key) and not re.fullmatch(pattern, str(data[key])):
                errors.append(f"invalid:{key}_hash")
        if data.get("working_tree_dirty") is not False:
            errors.append("invalid:strict_manifest_requires_clean_worktree")
    return errors


def validate_comparison(manifests: Sequence[Mapping[str, Any]]) -> list[str]:
    """Require identical known scope and dataset before comparing result totals."""
    errors = [f"manifest[{i}]:{error}" for i, data in enumerate(manifests)
              for error in validate_manifest(data, strict=True)]
    if errors or not manifests:
        return errors or ["missing:comparison_manifests"]
    for field in ("evaluation_scope", "dataset_id", "dataset_sha256"):
        if len({data[field] for data in manifests}) != 1:
            errors.append(f"mismatch:{field}")
    return errors
