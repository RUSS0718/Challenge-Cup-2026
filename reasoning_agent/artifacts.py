"""Shared persistence boundary for local experiment run artifacts.

This module owns run-scoped directories and common JSON, JSONL, Markdown, and
manifest writes.  Experiment runners may decide which data to collect, but
they should send the resulting files through one ``ArtifactManager`` instance
so runtime outputs do not spread across source and test directories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


def _utc_now() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    """Convert a configuration label into a short run-id-safe slug."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "run"


@dataclass(frozen=True)
class RunContext:
    """Identify one experiment run and its reproducibility metadata."""

    run_id: str
    config: str
    dataset: str | None = None
    model: str | None = None
    started_at: str = field(default_factory=_utc_now)
    status: str = "running"
    git_commit: str | None = None

    def __post_init__(self) -> None:
        """Reject empty identity fields before any artifact is created."""

        if not self.run_id.strip():
            raise ValueError("run_id_must_be_non_empty")
        if not self.config.strip():
            raise ValueError("config_must_be_non_empty")

    @classmethod
    def create(
        cls,
        config: str,
        *,
        dataset: str | None = None,
        model: str | None = None,
        git_commit: str | None = None,
    ) -> "RunContext":
        """Create a timestamped context when the caller has no run id."""

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
        return cls(
            run_id=f"{timestamp}-{_slugify(config)}",
            config=config,
            dataset=dataset,
            model=model,
            started_at=_utc_now(),
            git_commit=git_commit,
        )

    def as_manifest(self) -> dict[str, Any]:
        """Return the stable provenance fields written to ``run_manifest.json``."""

        manifest = {
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "config": self.config,
            "dataset": self.dataset,
            "model": self.model,
            "started_at": self.started_at,
            "status": self.status,
        }
        return manifest


class ArtifactManager:
    """Persist all files for one run below a single directory."""

    def __init__(self, run_dir: Path | str) -> None:
        """Bind the manager to a run directory without creating it yet."""

        self.run_dir = Path(run_dir)

    @classmethod
    def from_context(cls, root: Path | str, context: RunContext) -> "ArtifactManager":
        """Create a manager at ``root/<run_id>`` for the supplied context."""

        return cls(Path(root) / context.run_id)

    def _path(self, filename: str) -> Path:
        """Resolve one flat artifact filename and reject directory traversal."""

        path = Path(filename)
        if path.is_absolute() or path.parent != Path(".") or not path.name:
            raise ValueError("artifact_filename_must_be_flat")
        return self.run_dir / path.name

    def _atomic_write(self, filename: str, content: str) -> Path:
        """Write text through a sibling temporary file and return its final path."""

        path = self._path(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
        return path

    def save_json(self, filename: str, payload: Any) -> Path:
        """Atomically write JSON while rejecting non-JSON numeric values."""

        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"
        return self._atomic_write(filename, content)

    def save_text(self, filename: str, content: str) -> Path:
        """Atomically write a human-readable summary or other text artifact."""

        return self._atomic_write(filename, content)

    def append_jsonl(self, filename: str, record: Mapping[str, Any]) -> Path:
        """Append one JSON object to a run-local JSONL stream."""

        path = self._path(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    def save_answers(
        self,
        rows: Iterable[Mapping[str, Any]],
        filename: str = "answers.jsonl",
    ) -> Path:
        """Replace the run's answer stream with the supplied rows atomically."""

        content = "".join(
            json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
            for row in rows
        )
        return self._atomic_write(filename, content)

    def append_answer(self, row: Mapping[str, Any]) -> Path:
        """Append one row to the conventional ``answers.jsonl`` stream."""

        return self.append_jsonl("answers.jsonl", row)

    def save_metrics(self, metrics: Mapping[str, Any]) -> Path:
        """Write the conventional machine-readable metrics artifact."""

        return self.save_json("metrics.json", metrics)

    def save_report(self, report: Mapping[str, Any]) -> Path:
        """Write the conventional machine-readable report artifact."""

        return self.save_json("report.json", report)

    def save_manifest(
        self,
        context_or_manifest: RunContext | Mapping[str, Any],
        **fields: Any,
    ) -> Path:
        """Write a run manifest and merge runner-specific fields into it."""

        if isinstance(context_or_manifest, RunContext):
            manifest = context_or_manifest.as_manifest()
        else:
            manifest = dict(context_or_manifest)
        manifest.update(fields)
        return self.save_json("run_manifest.json", manifest)
