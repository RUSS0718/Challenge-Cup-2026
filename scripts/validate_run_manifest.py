"""Validate one or more run manifests against the repository schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.manifest_schema import validate_manifest  # noqa: E402


def main() -> int:
    """Validate manifest files and return a shell-friendly exit status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: error:{exc}")
            failed = True
            continue
        errors = validate_manifest(payload, strict=args.strict)
        if errors:
            failed = True
            print(f"{path}: " + ", ".join(errors))
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
