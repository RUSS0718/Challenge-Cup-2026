"""Materialize fixed ARM item manifests from repository-local problem pools."""

from __future__ import annotations

import json
from pathlib import Path
import random
from typing import Any, Mapping


def expand_selection_manifest(
    selection: Mapping[str, Any],
    *,
    pool_root: Path,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Resolve set-to-item-id selections into scoreable problem rows.

    The manifest stores only item IDs.  Problem text and gold answers remain in
    the repository-local JSONL pools and are never passed to the model runner
    as metadata.

    Raises:
        RuntimeError: If the manifest, pool, or selected item is malformed or
            missing.
    """
    materialized: list[dict[str, Any]] = []
    for set_id, item_ids in selection.items():
        if not isinstance(set_id, str) or not isinstance(item_ids, list):
            raise RuntimeError("dataset_selection_manifest_invalid")
        if any(not isinstance(item_id, str) or not item_id.strip() for item_id in item_ids):
            raise RuntimeError(f"dataset_selection_ids_invalid:{set_id}")
        pool_path = pool_root / f"{set_id}.jsonl"
        if not pool_path.is_file():
            raise RuntimeError(f"dataset_selection_pool_required:{pool_path}")
        pool_rows: dict[str, dict[str, Any]] = {}
        for line in pool_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"dataset_selection_pool_invalid_json:{pool_path}") from exc
            if not isinstance(row, Mapping) or not isinstance(row.get("item_id"), str):
                raise RuntimeError(f"dataset_selection_pool_row_invalid:{pool_path}")
            pool_rows[row["item_id"]] = dict(row)
        missing = [item_id for item_id in item_ids if item_id not in pool_rows]
        if missing:
            raise RuntimeError(f"dataset_selection_item_missing:{set_id}:{missing[0]}")
        materialized.extend(
            {
                **pool_rows[item_id],
                "idx": f"{set_id}:{item_id}",
            }
            for item_id in item_ids
        )
    if seed is not None:
        random.Random(int(seed)).shuffle(materialized)
    return materialized


__all__ = ["expand_selection_manifest"]
