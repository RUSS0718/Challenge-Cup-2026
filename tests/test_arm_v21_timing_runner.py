"""Acceptance tests for the serial eval112 timing runner."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts import run_arm_v21_eval112_timing as runner


class FakeClient:
    """Placeholder client proving one fresh client is created per item."""


class FakeAgent:
    """Return a complete answer without making network calls."""

    def __init__(self, client, config):
        self.client = client
        self.config = config

    def solve(self, problem, metadata):
        """Return bounded trace fields consumed by the runner."""
        return {
            "final_response": "42",
            "extracted_answer": "42",
            "trace": [
                {"stage": "evidence_ledger", "budget": {"calls": 1, "records": [{"reasoning_mode": "off"}], "candidates": [{"id": 1}]}},
                {"stage": "arm_v2_summary", "final_source": "candidate_a", "safe_fallback_used": False},
                {"stage": "finalize", "source": "candidate_a"},
            ],
        }


class ARMV21TimingRunnerTest(unittest.TestCase):
    """Check dataset guards, serial construction, and resumable artifacts."""

    def test_complete_answer_rejects_abstentions(self):
        for final in (None, "", "UNKNOWN", "unable to solve", "无法完成"):
            with self.subTest(final=final):
                self.assertFalse(runner.has_complete_answer({"final_response": final}))
        self.assertTrue(runner.has_complete_answer({"final_response": "Final answer: 42"}))

    def test_trace_fields_preserve_full_bounded_arm_diagnostics(self):
        result = {
            "final_response": "42",
            "trace": [{
                "stage": "arm_v2_summary",
                "primary_parse": {"status": "parsed", "candidate_count": 1},
                "primary_candidate": {"answer_complete": True, "trust_reason": "direct"},
                "second_parse": {"status": "not_run"},
                "second_candidate": None,
                "safe_candidate": {"value": "42"},
                "verification": {"status": "NOT_APPLICABLE"},
                "resolver": {"resolver_decision": None, "resolver_verdict": None},
                "final": {"source": "candidate_a"},
                "final_source": "candidate_a",
            }],
        }
        fields = runner._trace_fields(result)
        self.assertEqual("parsed", fields["primary_parse"]["status"])
        self.assertTrue(fields["primary_candidate"]["answer_complete"])
        self.assertEqual("42", fields["safe_candidate"]["value"])
        self.assertEqual("NOT_APPLICABLE", fields["verification"]["status"])
        self.assertIsNone(fields["resolver"]["resolver_decision"])
        self.assertEqual("candidate_a", fields["arm_v2_summary"]["final"]["source"])

    def test_second_sample_gain_loss_uses_paired_verdict_fields(self):
        report = runner.summarize_timing(
            [
                {
                    "status": "complete",
                    "complete_answer": True,
                    "verdict": "correct",
                    "baseline_verdict": "incorrect",
                    "candidate_verdict": "correct",
                    "second_sample_triggered": True,
                    "pair_relation": "CONFLICT",
                    "duration_seconds": 1,
                    "model_calls": 2,
                },
                {
                    "status": "complete",
                    "complete_answer": True,
                    "verdict": "incorrect",
                    "baseline_verdict": "correct",
                    "candidate_verdict": "incorrect",
                    "second_sample_triggered": True,
                    "pair_relation": "CONFLICT",
                    "duration_seconds": 1,
                    "model_calls": 2,
                },
            ],
            2,
        )
        self.assertEqual(1, report["correct_gain_from_second_sample"])
        self.assertEqual(1, report["correct_loss_from_second_sample"])

    def test_second_sample_gain_loss_reports_zero_when_unchanged(self):
        report = runner.summarize_timing(
            [{
                "status": "complete",
                "complete_answer": True,
                "verdict": "correct",
                "baseline_verdict": "correct",
                "candidate_verdict": "correct",
                "second_sample_triggered": True,
                "pair_relation": "EQUIVALENT",
                "duration_seconds": 1,
                "model_calls": 2,
            }],
            1,
        )
        self.assertEqual(0, report["correct_gain_from_second_sample"])
        self.assertEqual(0, report["correct_loss_from_second_sample"])

    def _dataset(self, directory: Path) -> Path:
        path = directory / "eval_112.json"
        path.write_text(
            json.dumps([{"idx": i, "problem": f"problem {i}", "answer": "42"} for i in range(112)]),
            encoding="utf-8",
        )
        return path

    def test_missing_dataset_fails_fast(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "eval112_required"):
                runner.load_eval112(Path(directory) / "missing.json")

    def test_runner_is_serial_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            clients = []

            def client_factory():
                client = FakeClient()
                clients.append(client)
                return client

            report = runner.run_timing(
                profile="arm-v2.1-off",
                run_id="ARM-V21-TEST",
                dataset_path=dataset,
                output_root=root / "artifacts",
                client_factory=client_factory,
                agent_factory=FakeAgent,
            )
            self.assertEqual(112, report["records"])
            self.assertEqual("ACCURACY_COMPLETE", report["disposition"])
            self.assertEqual(112, report["correct_count"])
            self.assertEqual(1.0, report["accuracy"])
            self.assertIn("second_sample_trigger_rate", report)
            self.assertIn("correct_gain_from_second_sample", report)
            self.assertEqual(112, len(clients))
            second = runner.run_timing(
                profile="arm-v2.1-off",
                run_id="ARM-V21-TEST",
                dataset_path=dataset,
                output_root=root / "artifacts",
                client_factory=client_factory,
                agent_factory=FakeAgent,
            )
            self.assertEqual(112, second["records"])
            self.assertEqual(112, len(clients))
            manifest = json.loads((root / "artifacts" / "ARM-V21-TEST" / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("off", manifest["solver_reasoning_mode"])
            self.assertEqual(1, manifest["workers"])

    def test_incomplete_answer_is_recorded_and_next_item_runs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root)
            clients = []
            solve_calls = []

            def client_factory():
                client = FakeClient()
                clients.append(client)
                return client

            def agent_factory(client, config):
                class RetryingFakeAgent(FakeAgent):
                    def solve(self, problem, metadata):
                        solve_calls.append(metadata["idx"])
                        if metadata["idx"] == 0:
                            return {"final_response": "UNKNOWN", "extracted_answer": "", "trace": []}
                        return super().solve(problem, metadata)

                return RetryingFakeAgent(client, config)

            report = runner.run_timing(
                profile="arm-v2.1-off",
                run_id="ARM-V21-RETRY-TEST",
                dataset_path=dataset,
                output_root=root / "artifacts",
                client_factory=client_factory,
                agent_factory=agent_factory,
            )
            run_dir = root / "artifacts" / "ARM-V21-RETRY-TEST"
            answers = [json.loads(line) for line in (run_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
            attempts = [json.loads(line) for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(112, len(answers))
            self.assertEqual(112, len(attempts))
            self.assertFalse(attempts[0]["complete_answer"])
            self.assertEqual("incomplete", attempts[0]["status"])
            self.assertEqual("incomplete_without_failure_reason", attempts[0]["final_failure_reason"])
            self.assertEqual("incomplete", answers[0]["status"])
            self.assertEqual(111, report["complete_answer_count"])
            self.assertEqual(112, len(clients))
            self.assertEqual(list(range(112)), solve_calls)
            self.assertFalse(json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))["retry_until_complete"])


if __name__ == "__main__":
    unittest.main()
