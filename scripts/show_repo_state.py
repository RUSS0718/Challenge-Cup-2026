"""Print or write the current release, Git, and run-artifact state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.repo_state import build_repo_state, write_json  # noqa: E402


def main() -> int:
    """Build a repository state snapshot and optionally persist it."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write docs/current_release.json")
    parser.add_argument("--check", action="store_true", help="fail if selector or release hashes disagree")
    args = parser.parse_args()
    manifest = ROOT / "docs/releases/arm-v2.1.4-cfr-20261004/manifest.json"
    output = ROOT / "docs/current_release.json"
    state = build_repo_state(ROOT, release_manifest=manifest, state_path=output)
    if args.write:
        write_json(output, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    release = state["release"]
    if args.check and (
        not release["selector_matches_runtime"]
        or release["runtime_hashes"]["status"] != "pass"
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
