"""Validate a length-calibration pressure set without model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_length_pressure_set import MAX_PRESSURE_SIZE, MIN_PRESSURE_SIZE, THRESHOLD


REQUIRED_FIELDS = {
    "idx",
    "problem",
    "task_type",
    "source",
    "source_ref",
    "length_evidence",
}
FORBIDDEN_FIELDS = {"answer", "verification", "gold_answer", "reference_answer"}


def validate(path: Path, *, min_size: int = MIN_PRESSURE_SIZE, max_size: int = MAX_PRESSURE_SIZE) -> list[str]:
    errors: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            items = [json.loads(line) for line in handle if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"read_error:{exc}"]

    if not min_size <= len(items) <= max_size:
        errors.append(f"dataset_size:{len(items)}")

    seen_idx: set[int] = set()
    seen_problem: set[str] = set()
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"not_object:{position}")
            continue
        idx = item.get("idx", position)
        missing = REQUIRED_FIELDS - set(item)
        if missing:
            errors.append(f"missing_fields:{idx}:{','.join(sorted(missing))}")
        for field in sorted(FORBIDDEN_FIELDS & set(item)):
            errors.append(f"{field}_field_present:{idx}")
        if not isinstance(idx, int) or idx in seen_idx:
            errors.append(f"bad_or_duplicate_idx:{idx}")
        seen_idx.add(idx)
        problem = str(item.get("problem", "")).strip()
        if not problem or problem in seen_problem:
            errors.append(f"bad_or_duplicate_problem:{idx}")
        seen_problem.add(problem)

        evidence = item.get("length_evidence")
        if not isinstance(evidence, dict):
            errors.append(f"bad_length_evidence:{idx}")
            continue
        telemetry_source = evidence.get("telemetry_source")
        if not isinstance(telemetry_source, str) or not telemetry_source.strip():
            errors.append(f"missing_telemetry_source:{idx}")
        if Path(telemetry_source).is_absolute():
            errors.append(f"absolute_telemetry_source:{idx}")
        try:
            completion = float(evidence["completion_tokens"])
            ceiling = float(evidence["ceiling_tokens"])
            fraction = float(evidence["completion_fraction"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"incomplete_length_evidence:{idx}")
            continue
        if ceiling <= 0 or completion < 0 or not 0 <= fraction <= 1:
            errors.append(f"invalid_length_evidence:{idx}")
            continue
        if fraction < THRESHOLD or completion / ceiling < THRESHOLD:
            errors.append(f"completion_below_threshold:{idx}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    errors = validate(args.dataset)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"valid: {args.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
