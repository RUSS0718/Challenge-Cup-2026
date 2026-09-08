import unittest
import json
import tempfile
import time
from pathlib import Path

from llm_client import ChatClientError
from scripts.run_car001_health_probe import (
    CAR_ID,
    BASELINE_ID,
    ProbeFailFastClient,
    paired_jobs,
    run,
    summarize,
)


class Car001HealthProbeTest(unittest.TestCase):
    @staticmethod
    def _record(job):
        return {
            "item_id": job["item"].get("idx", job["item_seq"]),
            "arm": job["arm"],
            "pair_order": job["pair_order"],
            "item_seq": job["item_seq"],
            "status": "ok",
            "final_response_present": True,
            "model_calls": 1,
            "duration_seconds": 0.0,
            "finish_reasons": [],
            "completion_tokens": [],
        }

    def test_paired_jobs_rotate_first_arm(self):
        jobs = paired_jobs([{"idx": 1}, {"idx": 2}])
        self.assertEqual(
            [(1, BASELINE_ID, 0), (1, CAR_ID, 1), (2, CAR_ID, 0), (2, BASELINE_ID, 1)],
            [(job["item"]["idx"], job["arm"], job["pair_order"]) for job in jobs],
        )

    def test_stage_failure_voids_even_when_relay_returns_unknown(self):
        records = [
            {
                "arm": BASELINE_ID,
                "status": "stage_error:model_error",
                "model_calls": 5,
                "duration_seconds": 0.1,
                "final_response_present": True,
                "finish_reasons": [],
                "completion_tokens": [],
            }
            for _ in range(2)
        ] + [
            {
                "arm": CAR_ID,
                "status": "stage_error:client_error",
                "model_calls": 3,
                "duration_seconds": 0.1,
                "final_response_present": True,
                "finish_reasons": [],
                "completion_tokens": [],
            }
            for _ in range(2)
        ]
        report = summarize(records, expected=2)
        self.assertTrue(report["void"])
        self.assertIn("fsdf_v1_model_error_rate", report["void_reasons"])
        self.assertIn("car_001_model_error_rate", report["void_reasons"])

    def test_fail_fast_client_does_not_repeat_transport_error(self):
        class Inner:
            def __init__(self):
                self.calls = 0

            def chat(self, *args, **kwargs):
                self.calls += 1
                raise ChatClientError("timeout")

            def diagnostic_snapshot(self):
                return {}

        inner = Inner()
        client = ProbeFailFastClient(inner)
        with self.assertRaises(ChatClientError):
            client.chat([], 0.0, 8)
        with self.assertRaises(ChatClientError):
            client.chat([], 0.0, 8)
        self.assertEqual(1, inner.calls)

    def test_partial_hard_stop_checkpoints_completed_records(self):
        def slow(job, timeout, retry):
            time.sleep(0.25)
            return self._record(job)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "partial"
            report = run(
                output,
                Path("sample_data/medium_capability_freeze_60.jsonl"),
                limit=2,
                timeout=0,
                retry=1,
                workers=1,
                hard_stop_seconds=0.02,
                solve_fn=slow,
            )
            self.assertEqual("partial_hard_stop", report["status"])
            self.assertTrue(report["void"])
            self.assertIn("window_hard_stop", report["void_reasons"])
            self.assertTrue((output / "answers.jsonl").exists())
            self.assertTrue((output / "report.json").exists())
            self.assertTrue((output / "run_manifest.json").exists())
            self.assertLessEqual(report["records"], report["expected_records"])

    def test_complete_run_keeps_four_records_sorted(self):
        def fast(job, timeout, retry):
            return self._record(job)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "complete"
            report = run(
                output,
                Path("sample_data/medium_capability_freeze_60.jsonl"),
                limit=2,
                timeout=1,
                retry=1,
                workers=2,
                hard_stop_seconds=1,
                solve_fn=fast,
            )
            self.assertEqual("completed", report["status"])
            self.assertFalse(report["void"])
            rows = [json.loads(line) for line in (output / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(4, len(rows))
            self.assertEqual(
                [(0, 0), (0, 1), (1, 0), (1, 1)],
                [(row["item_seq"], row["pair_order"]) for row in rows],
            )


if __name__ == "__main__":
    unittest.main()
