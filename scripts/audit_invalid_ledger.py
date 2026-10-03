"""Generate a gold-free invalid ledger from one immutable answer artifact.

The command performs no model calls and writes only compact diagnostics through
``ArtifactManager``.  It never rewrites the source answers file.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.artifacts import ArtifactManager, RunContext
from reasoning_agent.invalid_ledger import ledger_row


def _read_jsonl(path: Path) -> list[dict]:
    """Read JSONL rows and fail on malformed evidence."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    """Return the exact input hash recorded in the manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str | None:
    """Read the current commit without failing an exported source snapshot."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def audit(answers: Path, output: Path, expected_records: int | None = None) -> dict:
    """Create ``invalid_ledger.jsonl`` and a compact summary."""
    if output.exists():
        raise ValueError("ledger_output_already_exists")
    rows = _read_jsonl(answers)
    if expected_records is not None and len(rows) != expected_records:
        raise ValueError(f"expected_{expected_records}_records_got_{len(rows)}")
    ledger = [ledger_row(row) for row in rows]
    manager = ArtifactManager(output)
    context = RunContext.create("grh-v13-invalid-ledger", dataset=answers.name, git_commit=_git_sha())
    manager.save_manifest(context, status="running", input_sha256={str(answers): _sha256(answers)}, remote_model_calls=0, source_record_count=len(rows))
    manager.save_answers(ledger, filename="invalid_ledger.jsonl")
    summary = {
        "records": len(ledger),
        "old_verdicts": dict(Counter(row["old_verdict"] for row in ledger)),
        "failure_classes": dict(Counter(row["failure_class"] for row in ledger)),
        "salvage_tiers": dict(Counter(row["proposed_action"] for row in ledger)),
        "salvage_eligible": sum(bool(row["salvage_eligible"]) for row in ledger),
        "remote_model_calls": 0,
        "gold_in_ledger": False,
        "disposition": "P0_OFFLINE_LEDGER_ONLY",
    }
    manager.save_json("summary.json", summary)
    manager.save_manifest(context, status="completed", summary=summary)
    return summary


def main() -> None:
    """Parse explicit input/output paths and run the offline audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-records", type=int)
    args = parser.parse_args()
    print(json.dumps(audit(args.answers, args.output, args.expected_records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
