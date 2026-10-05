"""Query the machine-readable experiment disposition registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/experiment_registry.json"


def main() -> int:
    """Print matching experiment records by id or disposition."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id")
    parser.add_argument("--status", help="comma-separated statuses")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = payload["experiments"]
    statuses = {item.strip() for item in args.status.split(",")} if args.status else None
    matches = [
        item for item in records
        if (not args.id or item["method_id"].casefold() == args.id.casefold())
        and (not statuses or item["status"] in statuses)
    ]
    if args.as_json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
    else:
        for item in matches:
            print(f"{item['method_id']}\t{item['status']}\t{item['summary']}")
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
