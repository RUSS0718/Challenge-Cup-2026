"""Validate an offline reviewed-error notebook JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="reviewed-error notebook JSONL")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from reasoning_agent.error_notebook import validate_notebook_file

    report = validate_notebook_file(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, separators=(",", ":")))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
