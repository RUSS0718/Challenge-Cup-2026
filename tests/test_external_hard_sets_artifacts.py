"""Exercise run-scoped persistence for the external hard-set runner."""

import json
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.run_external_hard_sets_smoke as runner
from scripts.external_hard_sets_artifacts import ExternalHardSetsArtifactStore


class ExternalHardSetsArtifactStoreTest(unittest.TestCase):
    """Keep external hard-set outputs inside one identifiable run directory."""

    def test_default_run_uses_unique_artifacts_directory_and_shared_writers(self):
        """Persist every runner artifact through the shared run boundary."""
        with tempfile.TemporaryDirectory() as directory:
            store = ExternalHardSetsArtifactStore.create(
                root=Path(directory),
                output_dir=None,
                run_id=None,
                config="external-hard-sets-smoke",
                dataset="set_a,set_b",
                model="intern-s2",
                git_commit="abc123",
            )

            self.assertRegex(store.context.run_id, r"^\d{8}-\d{6}\d{6}-external-hard-sets-smoke$")
            self.assertEqual(
                Path(directory) / "artifacts" / store.context.run_id,
                store.run_dir,
            )
            store.save_manifest(status="completed")
            store.append_answer({"item_id": "one", "status": "ok"})
            store.save_preflight({"pass": True})
            store.save_report({"n": 1})

            manifest = json.loads((store.run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(store.context.run_id, manifest["run_id"])
            self.assertEqual("external-hard-sets-smoke", manifest["config"])
            self.assertEqual("set_a,set_b", manifest["dataset"])
            self.assertEqual("intern-s2", manifest["model"])
            self.assertEqual("abc123", manifest["git_commit"])
            self.assertEqual("completed", manifest["status"])
            self.assertTrue((store.run_dir / "answers.jsonl").is_file())
            self.assertTrue((store.run_dir / "preflight.json").is_file())
            self.assertTrue((store.run_dir / "report.json").is_file())

    def test_custom_directory_and_run_id_are_preserved(self):
        """Allow an explicit directory and identity for resumed windows."""
        with tempfile.TemporaryDirectory() as directory:
            custom_dir = Path(directory) / "manual-window"
            store = ExternalHardSetsArtifactStore.create(
                root=Path(directory),
                output_dir=custom_dir,
                run_id="fixed-window-01",
                config="external-hard-sets-smoke",
                dataset="set_a",
                model="intern-s2",
                git_commit="abc123",
            )

            self.assertEqual(custom_dir, store.run_dir)
            self.assertEqual("fixed-window-01", store.context.run_id)

    def test_runner_default_run_persists_below_artifacts(self):
        """Use a unique ignored run directory for a default runner invocation."""
        item = {
            "item_id": "one",
            "problem": "Find the integer.",
            "answer": "42",
            "domain": "algebra",
            "language": "EN",
        }
        record = {
            "set_id": "set_b_aime",
            "item_id": "one",
            "arm": "v1",
            "status": "ok",
            "final_response": "Final answer: 42",
            "native": {"verdict": "correct"},
            "contract": {"verdict": "correct"},
            "contract_extractable": True,
            "json_serializable": True,
            "model_calls": 1,
            "duration_seconds": 1.0,
            "trace": [],
            "domain": "algebra",
            "language": "EN",
        }

        def load_rows(path):
            """Read produced answers while serving one synthetic pool item."""
            if Path(path).name == "answers.jsonl":
                return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
            return [item]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pools = root / "pools"
            pools.mkdir()
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "POOLS_DIR", pools),
                patch.object(runner, "current_git_commit", return_value="abc123"),
                patch.object(runner, "sha256_file", return_value="poolhash"),
                patch.object(runner, "load_jsonl", side_effect=load_rows),
                patch.object(runner, "sample_set", return_value=[item]),
                patch.object(runner, "solve_one", return_value=record),
                patch.dict(os.environ, {"INTERN_MODEL": "test-model"}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                runner.run(
                    None,
                    timeout=1,
                    workers=1,
                    seed=1,
                    hard_stop_minutes=1,
                    sample_size=1,
                    sets=["set_b_aime"],
                    arms=["v1"],
                )

            run_dirs = list((root / "artifacts").iterdir())
            self.assertEqual(1, len(run_dirs))
            manifest = json.loads((run_dirs[0] / "run_manifest.json").read_text(encoding="utf-8"))
            report = json.loads((run_dirs[0] / "report.json").read_text(encoding="utf-8"))
            self.assertRegex(manifest["run_id"], r"^\d{8}-\d{6}\d{6}-external-hard-sets-smoke$")
            self.assertEqual("test-model", manifest["model"])
            self.assertEqual("abc123", manifest["git_commit"])
            self.assertEqual("completed", manifest["status"])
            self.assertEqual(1, report["overall"]["n"])

    def test_preflight_uses_the_same_artifact_boundary(self):
        """Persist preflight telemetry and provenance through the run store."""
        class PreflightClient:
            """Stand in for a healthy endpoint without making network calls."""

            def __init__(self, timeout, retry):
                """Initialize the telemetry fields consumed by the runner."""
                self.finish_reasons = []
                self.completion_tokens = []

            def chat(self, messages, temperature, max_tokens):
                """Return a successful preflight marker and usage metadata."""
                self.finish_reasons.append("stop")
                self.completion_tokens.append(4)
                return "PREFLIGHT_OK"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "current_git_commit", return_value="abc123"),
                patch.object(runner, "InternChatClient", PreflightClient),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                report = runner.run_preflight(None, timeout=1)

            run_dir = root / "artifacts" / report["run_id"]
            saved_preflight = json.loads((run_dir / "preflight.json").read_text(encoding="utf-8"))
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(saved_preflight["pass"])
            self.assertEqual("external-hard-sets-preflight", manifest["config"])
            self.assertEqual("completed", manifest["status"])


if __name__ == "__main__":
    unittest.main()
