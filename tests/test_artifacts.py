"""Tests for the shared run-scoped experiment artifact boundary."""

import json
from pathlib import Path
import tempfile
import unittest

from reasoning_agent.artifacts import ArtifactManager, RunContext


class ArtifactManagerTest(unittest.TestCase):
    """Keep experiment metadata and runtime files in one named run directory."""

    def test_manifest_uses_the_run_context_and_run_directory(self):
        """Persist the required reproducibility fields next to the run outputs."""
        with tempfile.TemporaryDirectory() as directory:
            context = RunContext(
                run_id="20260928-135512-arm-adaptive",
                config="arm-adaptive",
                dataset="eval-112",
                model="intern-s2",
                started_at="2026-09-28T13:55:12+00:00",
            )
            manager = ArtifactManager.from_context(Path(directory), context)

            manifest_path = manager.save_manifest(context, status="completed")

            self.assertEqual(
                Path(directory) / context.run_id / "run_manifest.json",
                manifest_path,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(context.run_id, manifest["run_id"])
            self.assertEqual("arm-adaptive", manifest["config"])
            self.assertEqual("eval-112", manifest["dataset"])
            self.assertEqual("intern-s2", manifest["model"])
            self.assertEqual("completed", manifest["status"])

    def test_named_writers_share_one_run_directory(self):
        """Write common experiment outputs through one persistence boundary."""
        with tempfile.TemporaryDirectory() as directory:
            manager = ArtifactManager(Path(directory) / "run")

            manager.save_answers([{"idx": 1, "status": "ok"}])
            manager.append_answer({"idx": 2, "status": "ok"})
            manager.save_metrics({"accuracy": 0.5})
            manager.save_report({"status": "completed"})
            manager.save_text("result.md", "# Summary\n")

            self.assertEqual(
                {
                    "answers.jsonl",
                    "metrics.json",
                    "report.json",
                    "result.md",
                },
                {path.name for path in Path(directory, "run").iterdir()},
            )
            answers = [
                json.loads(line)
                for line in (Path(directory) / "run" / "answers.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual([1, 2], [row["idx"] for row in answers])

    def test_writer_rejects_paths_outside_the_run_directory(self):
        """Keep callers from escaping the run directory with an artifact name."""
        with tempfile.TemporaryDirectory() as directory:
            manager = ArtifactManager(directory)

            with self.assertRaises(ValueError):
                manager.save_json("../report.json", {})


if __name__ == "__main__":
    unittest.main()
