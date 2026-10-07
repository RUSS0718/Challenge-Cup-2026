"""Bind external hard-set runs to the repository's shared artifact boundary.

This adapter owns run identity, default output placement, and the filenames
used by the hard-set runner. Serialization and atomic writes stay in
``reasoning_agent.artifacts``.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Mapping

from reasoning_agent.artifacts import ArtifactManager, RunContext

ROOT = Path(__file__).resolve().parents[1]


def current_git_commit(root: Path = ROOT) -> str | None:
    """Return the checked-out commit hash, or ``None`` outside a Git checkout."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


class ExternalHardSetsArtifactStore:
    """Provide named run-scoped writers for hard-set experiment outputs."""

    def __init__(self, context: RunContext, run_dir: Path) -> None:
        """Bind a run context and directory to the shared artifact manager."""
        self.context = context
        self.manager = ArtifactManager(run_dir)

    @classmethod
    def create(
        cls,
        *,
        root: Path,
        output_dir: Path | None,
        run_id: str | None,
        config: str,
        dataset: str,
        model: str,
        git_commit: str | None,
    ) -> "ExternalHardSetsArtifactStore":
        """Create a timestamped default run or honor an explicit run target."""
        if run_id is None and output_dir is None:
            context = RunContext.create(
                config,
                dataset=dataset,
                model=model,
                git_commit=git_commit,
            )
        else:
            resolved_id = run_id if run_id is not None else Path(output_dir).name
            context = RunContext(
                run_id=resolved_id,
                config=config,
                dataset=dataset,
                model=model,
                git_commit=git_commit,
            )
        run_dir = Path(output_dir) if output_dir is not None else Path(root) / "artifacts" / context.run_id
        return cls(context, run_dir)

    @property
    def run_dir(self) -> Path:
        """Return the directory containing this run's raw artifacts."""
        return self.manager.run_dir

    @property
    def answers_path(self) -> Path:
        """Return this run's resumable JSONL answer stream path."""
        return self.run_dir / "answers.jsonl"

    def save_manifest(self, fields: Mapping[str, Any] | None = None, **updates: Any) -> Path:
        """Persist provenance and runner-specific fields atomically."""
        payload = dict(fields or {})
        payload.update(updates)
        return self.manager.save_manifest(self.context, **payload)

    def save_preflight(self, report: Mapping[str, Any]) -> Path:
        """Persist the small-request endpoint preflight result."""
        return self.manager.save_json("preflight.json", report)

    def append_answer(self, record: Mapping[str, Any]) -> Path:
        """Append one completed task record to the run's JSONL stream."""
        return self.manager.append_answer(record)

    def save_report(self, report: Mapping[str, Any]) -> Path:
        """Persist the aggregate machine-readable report atomically."""
        return self.manager.save_report(report)
