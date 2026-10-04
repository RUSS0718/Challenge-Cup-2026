"""Repository and release-state inspection for agent-friendly diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from reasoning_agent.manifest_schema import normalise_manifest


def _git(repo_root: Path, *args: str) -> str | None:
    """Return one Git command's trimmed output, or ``None`` when unavailable."""

    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\r\n")


def normalized_sha256(path: Path) -> str:
    """Hash a UTF-8 source file after normalising CRLF to LF."""

    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_runtime_hashes(repo_root: Path, expected: dict[str, str]) -> dict[str, Any]:
    """Compare release-manifest hashes with the current checkout."""

    mismatches: list[dict[str, str]] = []
    missing: list[str] = []
    checked = 0
    for relative, expected_hash in expected.items():
        path = repo_root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        checked += 1
        actual = normalized_sha256(path)
        if actual != expected_hash:
            mismatches.append(
                {"path": relative, "expected": expected_hash, "actual": actual}
            )
    return {
        "status": "pass" if not missing and not mismatches else "fail",
        "checked": checked,
        "missing": missing,
        "mismatches": mismatches,
    }


def _dirty_paths(repo_root: Path, *, exclude: Path | None = None) -> list[str]:
    """Return porcelain paths, optionally excluding the generated state file."""

    raw = _git(
        repo_root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ) or ""
    excluded = exclude.resolve() if exclude else None
    paths: list[str] = []
    for record in raw.split("\x00"):
        if not record:
            continue
        relative = record[3:] if len(record) >= 3 else record
        candidate = (repo_root / relative).resolve()
        if excluded and candidate == excluded:
            continue
        paths.append(relative)
    return paths


def _recent_manifests(repo_root: Path, limit: int = 5) -> list[dict[str, Any]]:
    """List recent run manifests without reading raw answer files."""

    candidates = sorted(
        (path for path in (repo_root / "artifacts").rglob("run_manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    recent: list[dict[str, Any]] = []
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = normalise_manifest(payload)
        recent.append(
            {
                "path": str(path.relative_to(repo_root)).replace("\\", "/"),
                "run_id": data.get("run_id"),
                "status": data.get("status"),
                "evaluation_scope": data.get("evaluation_scope"),
                "config": data.get("config_selector") or data.get("submission_mode"),
            }
        )
    return recent


def build_repo_state(
    repo_root: Path | str,
    *,
    release_manifest: Path | str,
    state_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build one machine-readable snapshot of the active release and worktree."""

    root = Path(repo_root).resolve()
    manifest_path = Path(release_manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_path = Path(state_path).resolve() if state_path else None
    head = _git(root, "rev-parse", "HEAD")
    gitcode_main = _git(root, "rev-parse", "refs/remotes/gitcode/main")
    branch = _git(root, "branch", "--show-current")
    target_ref = manifest.get("target_ref", "gitcode/main")
    submission_mode = manifest.get("submission_mode")
    try:
        import user_agent

        runtime_submission_mode = user_agent.SUBMISSION_MODE
    except (ImportError, AttributeError):
        runtime_submission_mode = None
    dirty = _dirty_paths(root, exclude=output_path)
    hash_report = verify_runtime_hashes(
        root, dict(manifest.get("runtime_file_sha256", {}))
    )
    return {
        "state_schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "root": str(root),
            "branch": branch,
            "head_commit": head,
            "gitcode_main_commit": gitcode_main,
            "dirty_tree": bool(dirty),
            "dirty_paths": dirty,
        },
        "release": {
            "target_ref": target_ref,
            "submission_mode": submission_mode,
            "runtime_submission_mode": runtime_submission_mode,
            "status": manifest.get("status"),
            "rollback_anchor": manifest.get("rollback_anchor"),
            "official_evaluation": manifest.get("official_evaluation"),
            "manifest_path": str(manifest_path.relative_to(root)).replace("\\", "/"),
            "selector_matches_runtime": submission_mode == runtime_submission_mode,
            "runtime_hashes": hash_report,
        },
        "recent_runs": _recent_manifests(root),
    }


def format_repo_state_summary(state: Mapping[str, Any]) -> str:
    """Format the release snapshot as a compact agent-facing status report.

    The summary keeps the checkout, release guard, and recent artifact paths
    visible without printing the full dirty-path list or nested JSON. Callers
    that need machine-readable details should serialize the original snapshot.
    """

    repository = state.get("repository") or {}
    release = state.get("release") or {}
    dirty_paths = repository.get("dirty_paths") or []
    recent_runs = state.get("recent_runs") or []

    dirty = "yes" if repository.get("dirty_tree") else "no"
    selector_match = "yes" if release.get("selector_matches_runtime") else "no"
    hash_status = str((release.get("runtime_hashes") or {}).get("status") or "unknown")
    official = release.get("official_evaluation")
    official_label = "pending" if official is None else str(official).lower()

    lines = [
        "repo: "
        f"branch={repository.get('branch') or 'detached'} "
        f"head={repository.get('head_commit') or 'unknown'} "
        f"gitcode_main={repository.get('gitcode_main_commit') or 'unknown'} "
        f"dirty={dirty} dirty_paths={len(dirty_paths)}",
        "release: "
        f"selector={release.get('submission_mode') or 'unknown'} "
        f"status={release.get('status') or 'unknown'} "
        f"selector_match={selector_match} runtime_hashes={hash_status}",
        "release: "
        f"target={release.get('target_ref') or 'unknown'} "
        f"rollback={release.get('rollback_anchor') or 'none'} "
        f"manifest={release.get('manifest_path') or 'unknown'} "
        f"official_evaluation={official_label}",
        "recent_runs:",
    ]
    if not recent_runs:
        lines.append("- none")
    else:
        for run in recent_runs:
            lines.append(
                "- "
                f"{run.get('path') or 'unknown'} "
                f"run_id={run.get('run_id') or 'unknown'} "
                f"scope={run.get('evaluation_scope') or 'unknown'} "
                f"status={run.get('status') or 'unknown'} "
                f"config={run.get('config') or 'unknown'}"
            )
    return "\n".join(lines)


def write_json(path: Path | str, payload: dict[str, Any]) -> None:
    """Write a UTF-8 indented JSON state file with a trailing newline."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
