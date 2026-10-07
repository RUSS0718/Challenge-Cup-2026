"""Tests for the model-free ARM v2 raw health runner seam."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_arm_on_raw_health import run, summarize


class FakeHealthClient:
    """Return bounded client telemetry without making a network request."""

    created: list["FakeHealthClient"] = []

    def __init__(self, *, timeout, retry, thinking_mode):
        """Record constructor controls used by the raw health experiment."""
        self.timeout = timeout
        self.retry = retry
        self.thinking_mode = thinking_mode
        self.finish_reasons = []
        self.completion_tokens = []
        self.__class__.created.append(self)

    def chat(self, messages, temperature, max_tokens):
        """Return a short response and expose the same diagnostics as the real client."""
        self.finish_reasons.append("stop")
        self.completion_tokens.append(max_tokens // 2)
        return "Final answer: 323"


class ARMOnRawHealthTest(unittest.TestCase):
    """Keep the E1 runner direct, sequential, and accuracy-agnostic."""

    def tearDown(self):
        FakeHealthClient.created.clear()

    def test_run_records_the_token_by_difficulty_matrix(self):
        probes = (
            {"probe_id": "e", "difficulty": "easy", "problem": "1+1?"},
            {"probe_id": "m", "difficulty": "medium", "problem": "2+2?"},
            {"probe_id": "h", "difficulty": "hard", "problem": "3+3?"},
        )
        with tempfile.TemporaryDirectory() as directory:
            report = run(
                Path(directory),
                timeout_seconds=130,
                token_budgets=(512, 2_048, 4_096),
                probes=probes,
                client_factory=FakeHealthClient,
            )
            rows = [
                json.loads(line)
                for line in (Path(directory) / "answers.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(9, len(rows))
        self.assertEqual(9, report["records"])
        self.assertEqual(9, report["response_formed_count"])
        self.assertEqual({512, 2_048, 4_096}, {row["max_tokens"] for row in rows})
        self.assertEqual({"easy", "medium", "hard"}, {row["difficulty"] for row in rows})
        self.assertTrue(all(client.thinking_mode is True for client in FakeHealthClient.created))
        self.assertTrue(all(row["status"] == "ok" for row in rows))
        self.assertFalse(any("problem" in row for row in rows))

    def test_summary_does_not_infer_accuracy(self):
        report = summarize(
            [
                {
                    "max_tokens": 512,
                    "difficulty": "easy",
                    "status": "ok",
                    "response_formed": True,
                    "error_category": None,
                    "latency_seconds": 1.0,
                    "completion_tokens": 10,
                }
            ],
            expected_records=1,
        )

        self.assertEqual("NONE", report["capability_conclusion"])
        self.assertNotIn("correct", report)
        self.assertEqual("healthy", report["health_status"])


if __name__ == "__main__":
    unittest.main()
