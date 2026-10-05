"""Tests for the v2.4 experiment definition and gate accounting."""

import unittest
from collections import Counter

from scripts.run_arm_v224_experiment import _gate_decisions, risk_gated_round_specs
from reasoning_agent.paired_run_audit import audit_paired_round


class ARMV224ExperimentTest(unittest.TestCase):
    """Protect paired selection and candidate-to-baseline safety semantics."""

    def test_round_plan_has_ten_disjoint_paired_rounds(self):
        specs = risk_gated_round_specs()
        self.assertEqual(10, len(specs))
        for candidate, baseline in zip(specs[::2], specs[1::2]):
            self.assertEqual(candidate.dataset, baseline.dataset)
            self.assertEqual(candidate.keys, baseline.keys)
            self.assertEqual("arm-v2.4-risk-gated", candidate.profile)
            self.assertEqual("cfr-v2.4-risk-pressure", baseline.profile)

    def test_candidate_incorrect_to_baseline_correct_fails_safety_gate(self):
        gates = _gate_decisions(
            {"correct": 0, "incorrect": 1, "invalid": 0},
            {"correct": 1, "incorrect": 0, "invalid": 0},
            candidate_errors=0,
            baseline_errors=0,
            candidate_calls=2,
            baseline_calls=2,
            paired_records=1,
            activation_total=1,
            candidate_truncations=0,
            baseline_truncations=0,
            transitions=Counter({"incorrect__to__correct": 1}),
        )
        self.assertEqual("FAIL", gates["safety_gate"])

    def test_any_baseline_correct_recovery_is_a_safety_regression(self):
        gates = _gate_decisions(
            {"correct": 0, "incorrect": 0, "invalid": 1},
            {"correct": 1, "incorrect": 0, "invalid": 0},
            candidate_errors=0,
            baseline_errors=0,
            candidate_calls=2,
            baseline_calls=2,
            paired_records=1,
            activation_total=1,
            candidate_truncations=0,
            baseline_truncations=0,
            transitions=Counter({"invalid__to__correct": 1}),
        )
        self.assertEqual("FAIL", gates["safety_gate"])

    def test_dirty_manifest_cannot_pass_provenance_audit(self):
        manifest = {
            "manifest_schema_version": 2,
            "run_id": "run",
            "config_selector": "candidate",
            "dataset_id": "set.jsonl",
            "git_commit": "a" * 40,
            "dataset_sha256": "b" * 64,
            "started_at": "2026-10-05T00:00:00Z",
            "status": "completed",
            "evaluation_scope": "local_replay",
            "official_evaluation": False,
            "working_tree_dirty": True,
            "selected_items": ["q1"],
            "records": 1,
            "gold_passed_to_agent": False,
        }
        errors = audit_paired_round(
            [manifest, {**manifest, "config_selector": "baseline"}],
            [[{"item_id": "q1"}], [{"item_id": "q1"}]],
            expected_ids=["q1"],
            profiles=("candidate", "baseline"),
            dataset_id="set.jsonl",
            dataset_sha256="b" * 64,
        )
        self.assertIn("manifest[0]:invalid:strict_manifest_requires_clean_worktree", errors)


if __name__ == "__main__":
    unittest.main()
