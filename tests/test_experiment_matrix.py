"""Tests for the reproducible multi-round evaluation matrix helpers."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reasoning_agent.experiment_matrix import (
    DATASET_PATHS,
    RoundSpec,
    build_round_config,
    format_matrix_summary,
    load_scored_rows,
    missing_candidate_round_specs,
    recovery_round_specs,
    select_rows,
    summarize_rows,
    structured_confirmation_round_specs,
    compact_finalizer_round_specs,
    external_pressure_round_specs,
    external_pressure_replication_round_specs,
    incumbent_guard_round_specs,
)
from scripts.run_robustness_matrix import (
    _call_telemetry,
    _merge_round_reports,
    _paired_record_count,
    _summarize_reports_by_profile,
    run_matrix,
)


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

    def test_matrix_summary_points_to_artifacts_without_dumping_round_details(self):
        """Default runner output should be short and still locate durable evidence."""
        summary = format_matrix_summary(
            {
                "run_id": "MATRIX-1",
                "status": "completed",
                "evaluation_scope": "local_replay",
                "round_count": 2,
                "total_records": 10,
                "correct": 4,
                "incorrect": 3,
                "invalid": 3,
                "model_errors": 0,
                "total_model_calls": 18,
            },
            Path("artifacts") / "MATRIX-1",
        )
        self.assertIn("matrix: id=MATRIX-1", summary)
        self.assertIn(
            f"aggregate: {Path('artifacts', 'MATRIX-1', 'aggregate.json')}",
            summary,
        )
        self.assertNotIn('"rounds"', summary)

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

    def test_missing_candidate_plan_is_ten_disjoint_paired_rounds(self):
        specs = missing_candidate_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"C{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.6-missing-candidate", candidate.profile)
            self.assertEqual("arm-v2.1.4-cfr", baseline.profile)

    def test_missing_candidate_profile_builds_v216_without_changing_budget(self):
        config = build_round_config(missing_candidate_round_specs()[0])
        baseline = build_round_config(missing_candidate_round_specs()[1])
        self.assertEqual("v2.1.6", config.arm_harness_version)
        self.assertEqual("positive_evidence", config.arm_trust_policy)
        self.assertEqual(config.harness_attempt_a_max_tokens, baseline.harness_attempt_a_max_tokens)

    def test_structured_confirmation_plan_is_ten_paired_rounds_on_fresh_data(self):
        specs = structured_confirmation_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"V{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual("fresh_confirmation", candidate.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.7-structured-confirmation", candidate.profile)
            self.assertEqual("arm-v2.1.4-cfr", baseline.profile)

    def test_structured_confirmation_plan_has_common_pressure_budget(self):
        candidate = build_round_config(structured_confirmation_round_specs()[0])
        baseline = build_round_config(structured_confirmation_round_specs()[1])
        self.assertEqual("v2.1.7", candidate.arm_harness_version)
        self.assertEqual(1024, candidate.harness_attempt_a_max_tokens)
        self.assertEqual(1024, candidate.harness_attempt_b_max_tokens)
        self.assertEqual(candidate.harness_attempt_a_max_tokens, baseline.harness_attempt_a_max_tokens)

    def test_compact_finalizer_plan_is_ten_paired_rounds_on_disjoint_data(self):
        specs = compact_finalizer_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"W{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.8-compact-finalizer", candidate.profile)
            self.assertEqual("cfr-long", baseline.profile)

    def test_compact_finalizer_uses_long_primary_and_short_second_budget(self):
        candidate = build_round_config(compact_finalizer_round_specs()[0])
        self.assertEqual("v2.1.8", candidate.arm_harness_version)
        self.assertEqual(8_192, candidate.harness_attempt_a_max_tokens)
        self.assertEqual(2_048, candidate.harness_attempt_b_max_tokens)
        self.assertEqual(16_384, candidate.harness_total_token_budget)

    def test_external_pressure_plan_is_ten_paired_rounds_across_frozen_pools(self):
        specs = external_pressure_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"X{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        self.assertEqual(
            {"external_olymmath", "external_aime", "external_hle"},
            {spec.dataset for spec in specs},
        )
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.8-external-pressure", candidate.profile)
            self.assertEqual("cfr-external-pressure", baseline.profile)

    def test_external_pressure_profiles_share_primary_budget(self):
        candidate = build_round_config(external_pressure_round_specs()[0])
        baseline = build_round_config(external_pressure_round_specs()[1])
        self.assertEqual("v2.1.8", candidate.arm_harness_version)
        self.assertEqual("v2.1.4", baseline.arm_harness_version)
        self.assertEqual(1_024, candidate.harness_attempt_a_max_tokens)
        self.assertEqual(candidate.harness_attempt_a_max_tokens, baseline.harness_attempt_a_max_tokens)
        self.assertEqual(4_096, candidate.harness_attempt_b_max_tokens)
        self.assertEqual(4_096, baseline.harness_attempt_b_max_tokens)

    def test_external_pressure_changes_only_harness_version(self):
        """A complete primary must keep the baseline Challenger budget and policy."""
        candidate = asdict(build_round_config(external_pressure_round_specs()[0]))
        baseline = asdict(build_round_config(external_pressure_round_specs()[1]))
        candidate.pop("arm_harness_version")
        baseline.pop("arm_harness_version")
        self.assertEqual(baseline, candidate)

    def test_external_pressure_replication_is_disjoint_and_scored(self):
        """The independent Y window must resolve every item and avoid X items."""
        x_specs = external_pressure_round_specs()
        y_specs = external_pressure_replication_round_specs()
        self.assertEqual([f"Y{index:02d}" for index in range(1, 11)], [spec.round_id for spec in y_specs])
        x_items = {(spec.dataset, key) for spec in x_specs for key in spec.keys}
        y_items = {(spec.dataset, key) for spec in y_specs for key in spec.keys}
        self.assertTrue(y_items)
        self.assertTrue(x_items.isdisjoint(y_items))
        for candidate, baseline in zip(y_specs[::2], y_specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.8-external-pressure", candidate.profile)
            self.assertEqual("cfr-external-pressure", baseline.profile)
            candidate_config = asdict(build_round_config(candidate))
            baseline_config = asdict(build_round_config(baseline))
            candidate_config.pop("arm_harness_version")
            baseline_config.pop("arm_harness_version")
            self.assertEqual(baseline_config, candidate_config)
        for spec in y_specs:
            rows = load_scored_rows(DATASET_PATHS[spec.dataset])
            self.assertEqual(list(spec.keys), [row["item_id"] for row in select_rows(rows, spec.keys)])

    def test_incumbent_guard_plan_is_ten_paired_rounds_disjoint_from_prior_windows(self):
        specs = incumbent_guard_round_specs()
        self.assertEqual(10, len(specs))
        self.assertEqual([f"Z{index:02d}" for index in range(1, 11)], [spec.round_id for spec in specs])
        prior = (*external_pressure_round_specs(), *external_pressure_replication_round_specs())
        prior_items = {(spec.dataset, key) for spec in prior for key in spec.keys}
        guard_items = {(spec.dataset, key) for spec in specs for key in spec.keys}
        self.assertTrue(guard_items.isdisjoint(prior_items))
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.1.9-incumbent-guard", candidate.profile)
            self.assertEqual("cfr-external-pressure", baseline.profile)

    def test_incumbent_guard_profile_keeps_equal_pressure_budget(self):
        candidate = build_round_config(incumbent_guard_round_specs()[0])
        baseline = build_round_config(incumbent_guard_round_specs()[1])
        self.assertEqual("v2.1.9", candidate.arm_harness_version)
        self.assertEqual("v2.1.4", baseline.arm_harness_version)
        self.assertEqual(1_024, candidate.harness_attempt_a_max_tokens)
        self.assertEqual(4_096, candidate.harness_attempt_b_max_tokens)
        candidate_values = asdict(candidate)
        baseline_values = asdict(baseline)
        candidate_values.pop("arm_harness_version")
        baseline_values.pop("arm_harness_version")
        self.assertEqual(baseline_values, candidate_values)

    def test_missing_scoring_dependency_blocks_network_calls(self):
        """A missing SymPy installation must fail before any round is launched."""
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.run_robustness_matrix.importlib.import_module", side_effect=ImportError):
                with patch("scripts.run_robustness_matrix._run_round") as run_round:
                    with self.assertRaisesRegex(ValueError, "scoring_dependency_unavailable"):
                        run_matrix(Path(directory), rounds=list(external_pressure_round_specs()))
                    run_round.assert_not_called()

    def test_summary_counts_finalizer_activation_and_truncation_events(self):
        rows = [
            {
                "outcome": "invalid",
                "verdict": "unknown",
                "model_calls": 2,
                "finish_reasons": ["length", "stop"],
                "trace": [{"stage": "compact_finalizer", "reason": "primary_truncated"}],
            },
            {
                "outcome": "correct",
                "verdict": "correct",
                "model_calls": 1,
                "finish_reasons": ["stop"],
                "trace": [],
            },
        ]
        summary = summarize_rows(rows)
        self.assertEqual(1, summary["compact_finalizer_activations"])
        self.assertEqual({"primary_truncated": 1}, summary["compact_finalizer_trigger_reason_counts"])
        self.assertEqual(1, summary["truncation_count"])

    def test_summary_counts_incumbent_guard_events(self):
        summary = summarize_rows(
            [
                {
                    "outcome": "correct",
                    "verdict": "correct",
                    "model_calls": 2,
                    "finish_reasons": ["length", "stop"],
                    "trace": [{"stage": "incumbent_preserving_finalizer_gate", "reason": "complete_incumbent"}],
                }
            ]
        )
        self.assertEqual(1, summary["incumbent_guard_activations"])
        self.assertEqual({"complete_incumbent": 1}, summary["incumbent_guard_reason_counts"])

    def test_runner_separates_arm_totals_from_paired_totals(self):
        reports = [
            {
                "profile": "candidate",
                "records": 2,
                "selected_items": ["a", "b"],
                "correct": 1,
                "incorrect": 1,
                "invalid": 0,
                "model_errors": 0,
                "total_model_calls": 4,
                "truncation_count": 1,
                "compact_finalizer_activations": 0,
                "incumbent_guard_activations": 2,
            },
            {
                "profile": "baseline",
                "records": 2,
                "selected_items": ["a", "b"],
                "correct": 0,
                "incorrect": 2,
                "invalid": 0,
                "model_errors": 0,
                "total_model_calls": 4,
                "truncation_count": 0,
                "compact_finalizer_activations": 0,
                "incumbent_guard_activations": 0,
            },
        ]
        by_profile = _summarize_reports_by_profile(reports)
        self.assertEqual(2, _paired_record_count(reports))
        self.assertEqual(1, by_profile["candidate"]["correct"])
        self.assertEqual(2, by_profile["candidate"]["incumbent_guard_activations"])
        self.assertEqual(0, by_profile["baseline"]["correct"])


if __name__ == "__main__":
    unittest.main()
