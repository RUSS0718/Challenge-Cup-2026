"""Tests for the reproducible multi-round evaluation matrix helpers."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from reasoning_agent.experiment_matrix import (
    RoundSpec,
    build_round_config,
    load_scored_rows,
    recovery_round_specs,
    select_rows,
    summarize_rows,
)
from scripts.run_robustness_matrix import _call_telemetry, _merge_round_reports


class ExperimentMatrixTest(unittest.TestCase):
    """Keep round selection, configuration, and failure summaries deterministic."""

    def test_load_and_select_support_idx_and_item_id_rows(self):
        rows = load_scored_rows(
            Path(__file__).parents[1] / "docs/experiments/V4-HARD20-DUAL-001/official_like_hard20_v1.jsonl"
        )
        selected = select_rows(rows, [rows[2]["item_id"], rows[0]["item_id"]])
        self.assertEqual([rows[2]["item_id"], rows[0]["item_id"]], [row["item_id"] for row in selected])
        self.assertTrue(all("problem" in row and "answer" in row for row in selected))

    def test_long_cfr_round_raises_primary_budget_without_changing_mode(self):
        spec = RoundSpec(
            round_id="R01",
            profile="cfr-long",
            dataset="eval",
            keys=(0,),
        )
        config = build_round_config(spec)
        self.assertTrue(config.enable_arm_harness)
        self.assertEqual("v2.1.4", config.arm_harness_version)
        self.assertEqual(8192, config.harness_attempt_a_max_tokens)
        self.assertEqual(4096, config.harness_attempt_b_max_tokens)
        self.assertEqual("positive_evidence", config.arm_trust_policy)

    def test_summary_counts_failure_reasons_and_finish_reasons(self):
        rows = [
            {
                "outcome": "correct",
                "verdict": "correct",
                "model_calls": 2,
                "finish_reasons": ["stop", "stop"],
                "trace": [],
            },
            {
                "outcome": "invalid",
                "verdict": "unknown",
                "model_calls": 2,
                "finish_reasons": ["length", "stop"],
                "trace": [
                    {
                        "stage": "arm_v2_summary",
                        "final_failure_reason": "second_sample_incomplete",
                    }
                ],
            },
        ]
        summary = summarize_rows(rows)
        self.assertEqual({"correct": 1, "invalid": 1}, summary["outcome_counts"])
        self.assertEqual({"length": 1, "stop": 3}, summary["finish_reason_counts"])
        self.assertEqual({"second_sample_incomplete": 1}, summary["failure_reason_counts"])

    def test_legacy_agent_telemetry_is_counted_without_an_evidence_ledger(self):
        class Client:
            finish_reasons = ["stop", "length"]
            request_diagnostics = [{"status": "success"}, {"status": "success"}]

        reasons, calls, model_error = _call_telemetry(Client(), [])
        self.assertEqual(["stop", "length"], reasons)
        self.assertEqual(2, calls)
        self.assertFalse(model_error)

    def test_subset_rerun_reuses_only_completed_default_round_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "R01").mkdir()
            (root / "R01" / "report.json").write_text(
                json.dumps(
                    {
                        "round_id": "R01",
                        "status": "completed",
                        "diagnostic_only": True,
                        "correct": 2,
                    }
                ),
                encoding="utf-8",
            )
            selected = [RoundSpec("R05", "typed-capsule", "eval", (0,))]
            fresh = [{"round_id": "R05", "status": "completed", "diagnostic_only": True, "correct": 1}]
            reports, reused = _merge_round_reports(root, selected, fresh)
            self.assertEqual(["R01", "R05"], [report["round_id"] for report in reports])
            self.assertEqual(["R01"], reused)

    def test_recovery_plan_is_ten_paired_rounds_and_keeps_default_official_profile(self):
        specs = recovery_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"B{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.5-bounded-tail", candidate.profile)
            self.assertEqual("arm-v2.1.4-cfr", baseline.profile)

    def test_bounded_tail_round_builds_v215_without_changing_budget_selector(self):
        config = build_round_config(recovery_round_specs()[0])
        self.assertEqual("v2.1.5", config.arm_harness_version)
        self.assertTrue(config.enable_arm_harness)
        self.assertEqual("positive_evidence", config.arm_trust_policy)
        self.assertEqual(build_round_config(recovery_round_specs()[1]).harness_attempt_a_max_tokens, config.harness_attempt_a_max_tokens)

    def test_subset_rerun_reuses_only_completed_recovery_round_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "B01").mkdir()
            (root / "B01" / "report.json").write_text(
                json.dumps(
                    {
                        "round_id": "B01",
                        "status": "completed",
                        "diagnostic_only": True,
                        "correct": 2,
                    }
                ),
                encoding="utf-8",
            )
            selected = [recovery_round_specs()[1]]
            fresh = [{"round_id": "B02", "status": "completed", "diagnostic_only": True, "correct": 1}]
            reports, reused = _merge_round_reports(root, selected, fresh)
            self.assertEqual(["B01", "B02"], [report["round_id"] for report in reports])
            self.assertEqual(["B01"], reused)


if __name__ == "__main__":
    unittest.main()
