"""Replay host-side candidate extraction without calling a model or using gold."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reasoning_agent.artifacts import ArtifactManager, RunContext
from reasoning_agent.answer_contract import TaskContract
from reasoning_agent.candidate_canonicalizer import parse_response
from reasoning_agent.invalid_recovery import decide_recovery, transition


def replay(answers: Path, output: Path, expected_records: int | None = None) -> dict:
    """Write one compact before/after decision row per saved answer."""
    if output.exists():
        raise ValueError("replay_output_already_exists")
    rows = [json.loads(line) for line in answers.read_text(encoding="utf-8").splitlines() if line.strip()]
    if expected_records is not None and len(rows) != expected_records:
        raise ValueError(f"expected_{expected_records}_records_got_{len(rows)}")
    output_rows = []
    for row in rows:
        parsed = parse_response(str(row.get("final_response", "")), TaskContract())
        candidate = parsed.candidates[0] if parsed.complete else None
        decision = decide_recovery(row, candidate)
        output_rows.append({
            "question_id": str(row.get("item_id", row.get("idx", ""))),
            "old_verdict": str(row.get("verdict", row.get("outcome", "unknown"))),
            "candidate_source": candidate.source if candidate else "none",
            "candidate_value": candidate.canonical_value if candidate else "",
            "decision": decision.as_dict(),
            "new_verdict": "unknown",
            "transition": transition(str(row.get("verdict", row.get("outcome", "unknown"))), "unknown"),
        })
    manager = ArtifactManager(output)
    context = RunContext.create("grh-v13-invalid-replay", dataset=answers.name)
    manager.save_manifest(context, status="running", remote_model_calls=0, source_record_count=len(rows))
    manager.save_answers(output_rows, filename="replay.jsonl")
    summary = {"records": len(output_rows), "actions": dict(Counter(row["decision"]["action"] for row in output_rows)), "remote_model_calls": 0, "gold_used": False, "disposition": "P1_HOST_REPLAY_ONLY"}
    manager.save_json("summary.json", summary)
    manager.save_manifest(context, status="completed", summary=summary)
    return summary


def main() -> None:
    """Run a deterministic replay from explicit answer artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-records", type=int)
    args = parser.parse_args()
    print(json.dumps(replay(args.answers, args.output, args.expected_records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
