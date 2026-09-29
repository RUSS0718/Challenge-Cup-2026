"""Acceptance tests for the four-arm promotion runner."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_submission_promotion import PROMOTION_ARMS, run_promotion


class FakeClient:
    """Provide a client object for the injected no-network promotion run."""


class FakeAgent:
    """Return one bounded correct answer for every configured arm."""

    def __init__(self, client, config):
        self.client = client
        self.config = config

    def solve(self, problem, metadata):
        """Return the compact trace shapes consumed by the promotion runner."""
        del problem, metadata
        if self.config.enable_arm_harness:
            trace = [
                {
                    "stage": "evidence_ledger",
                    "budget": {"calls": 1, "records": [{"reasoning_mode": "off"}]},
                },
                {
                    "stage": "arm_v2_summary",
                    "solver_reasoning_mode": "off",
                    "primary_candidate": {"answer_complete": True},
                    "final_source": "primary",
                    "second_sample_triggered": False,
                    "resolver_triggered": False,
                },
            ]
        else:
            trace = [{"stage": "finalize", "source": "legacy_backend", "model_calls": 1}]
        return {"final_response": "42", "extracted_answer": "42", "trace": trace}


class SubmissionPromotionTest(unittest.TestCase):
    """Ensure all four arms share the runner and produce bounded artifacts."""

    def test_four_arm_fake_run_writes_diagnostics_and_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "items.json"
            dataset.write_text(
                json.dumps([{"idx": index, "problem": "1+1", "answer": "42"} for index in range(30)]),
                encoding="utf-8",
            )
            report = run_promotion(
                run_prefix="PROMOTION-TEST",
                dataset_path=dataset,
                output_root=root / "artifacts",
                expected_records=30,
                selection_seed=None,
                client_factory=FakeClient,
                agent_factory=FakeAgent,
            )

            self.assertEqual(set(PROMOTION_ARMS), set(report["arms"]))
            self.assertEqual(4, len(report["round_reports"]))
            self.assertTrue(all(gate["status"] == "PASS" for gate in report["full30_gates"].values()))
            diagnostics = root / "artifacts" / "PROMOTION-TEST-r1-B" / "diagnostics.jsonl"
            self.assertEqual(30, len(diagnostics.read_text(encoding="utf-8").splitlines()))
            self.assertNotIn("final_response", diagnostics.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
