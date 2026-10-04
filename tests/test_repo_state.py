"""Tests for release hash verification helpers."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from reasoning_agent.repo_state import (
    _dirty_paths,
    _recent_manifests,
    format_repo_state_summary,
    normalized_sha256,
    verify_runtime_hashes,
)


class RepoStateTest(unittest.TestCase):
    """Verify normalized source hashes and mismatch reporting."""

    def test_hash_normalizes_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"
            path.write_bytes(b"one\r\ntwo\r\n")
            expected = normalized_sha256(path)
            path.write_bytes(b"one\ntwo\n")
            self.assertEqual(expected, normalized_sha256(path))

    def test_hash_report_detects_mismatch_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.py"
            path.write_text("pass\n", encoding="utf-8")
            report = verify_runtime_hashes(
                root,
                {"source.py": "0" * 64, "missing.py": "1" * 64},
            )
            self.assertEqual("fail", report["status"])
            self.assertEqual(["missing.py"], report["missing"])
            self.assertEqual("source.py", report["mismatches"][0]["path"])

    def test_recent_legacy_manifest_reports_unknown_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "artifacts" / "legacy"
            run_dir.mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text(
                '{"run_id":"legacy","config":"old","status":"completed"}',
                encoding="utf-8",
            )
            recent = _recent_manifests(root)
            self.assertEqual("unknown", recent[0]["evaluation_scope"])
            self.assertEqual("old", recent[0]["config"])

    def test_dirty_paths_preserve_unicode_names(self):
        """Report non-ASCII paths in the same form users see in the worktree."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            path = root / "docs" / "实现文档.md"
            path.parent.mkdir()
            path.write_text("历史\n", encoding="utf-8")
            self.assertIn("docs/实现文档.md", _dirty_paths(root))

    def test_summary_exposes_release_guard_and_recent_artifact_path(self):
        """Keep the default status view compact while preserving navigation targets."""
        summary = format_repo_state_summary(
            {
                "repository": {
                    "branch": "feature/test",
                    "head_commit": "abc123",
                    "dirty_tree": True,
                    "dirty_paths": ["docs/old.md"],
                },
                "release": {
                    "submission_mode": "arm-v2.1.4-cfr",
                    "status": "DEPLOYED_UNVALIDATED_CANARY",
                    "selector_matches_runtime": True,
                    "runtime_hashes": {"status": "pass"},
                    "target_ref": "gitcode/main",
                    "rollback_anchor": "43a02da",
                    "official_evaluation": None,
                },
                "recent_runs": [
                    {
                        "path": "artifacts/run-1/run_manifest.json",
                        "run_id": "run-1",
                        "evaluation_scope": "local_replay",
                        "status": "completed",
                        "config": "arm-v2.1.4-cfr",
                    }
                ],
            }
        )
        self.assertIn("selector=arm-v2.1.4-cfr", summary)
        self.assertIn("artifacts/run-1/run_manifest.json", summary)
        self.assertNotIn('"recent_runs"', summary)
