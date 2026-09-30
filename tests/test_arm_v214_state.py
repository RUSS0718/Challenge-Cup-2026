"""Regression tests for ARM v2.1.4 candidate provenance and metrics."""

import unittest

from reasoning_agent.harness_contracts import Candidate
from reasoning_agent.harness_contracts import HostParser
from reasoning_agent.arm_v21_verification import (
    ChallengerFinding,
    FreshReview,
    parse_challenger_finding,
    replacement_decision,
)
from reasoning_agent.submission_diagnostics import summarize_submission_diagnostics


class ARMV214StateTest(unittest.TestCase):
    """Keep provenance fields bounded and promotion metrics denominator-safe."""

    def test_candidate_ledger_includes_provenance_fields(self):
        candidate = Candidate(
            candidate_id="primary_1",
            value="7",
            normalized_value="7",
            answer_type="integer",
            source="arm_primary",
            extraction_status="parsed",
            candidate_role="primary",
            candidate_version=1,
            incumbent=True,
        )
        row = candidate.ledger_dict()
        self.assertEqual("primary", row["candidate_role"])
        self.assertEqual(1, row["candidate_version"])
        self.assertTrue(row["incumbent"])
        self.assertEqual("none", row["challenge_status"])

    def test_metrics_use_total_denominator_and_report_damage_rescue(self):
        records = [
            {"arm_v2_summary": {"final_source": "primary"}, "primary_candidate_complete": True,
             "baseline_verdict": "correct", "verdict": "correct", "model_calls": 1},
            {"arm_v2_summary": {"final_source": "repair"}, "primary_candidate_complete": True,
             "baseline_verdict": "correct", "verdict": "incorrect", "model_calls": 2},
            {"arm_v2_summary": {"final_source": "challenger"}, "primary_candidate_complete": True,
             "baseline_verdict": "incorrect", "verdict": "correct", "model_calls": 2},
            {"arm_v2_summary": {"final_source": "abstain"}, "primary_candidate_complete": False,
             "baseline_verdict": "invalid", "verdict": "invalid", "model_calls": 1},
        ]
        report = summarize_submission_diagnostics(records, profile="arm-v2.1.4", expected_records=4)
        self.assertEqual(1, report["damage_count"])
        self.assertEqual(1, report["rescue_count"])
        self.assertEqual(2, report["primary_correct_count"])
        self.assertEqual(0.5, report["primary_accuracy"])
        self.assertEqual(0.5, report["accuracy"])

    def test_final_marker_preserves_answer_when_tail_is_truncated(self):
        parsed = HostParser().parse(
            "推理尚未收束\nFinal answer: 7",
            problem="计算 1+1",
            source="arm_primary",
            finish_reason="length",
        )
        self.assertEqual(1, len(parsed.candidates))
        self.assertTrue(parsed.truncated)
        self.assertTrue(parsed.candidates[0].answer_complete)
        self.assertEqual("parsed", parsed.candidates[0].extraction_status)

    def test_challenger_contract_requires_specific_evidence_for_replacement(self):
        finding = parse_challenger_finding(
            '{"verdict":"OBJECTION","issue_type":"arithmetic",'
            '"issue_location":"step 2","claim":"sum is wrong",'
            '"evidence":"2+2=4","repairable":true,"coverage":"final check"}'
        )
        self.assertTrue(finding.supports_replacement)
        self.assertEqual("step 2", finding.as_dict()["issue_location"])
        self.assertFalse(ChallengerFinding().supports_replacement)
        self.assertEqual("UNKNOWN", parse_challenger_finding("B looks better").verdict)

    def test_repair_requires_passing_fresh_review(self):
        finding = ChallengerFinding(
            verdict="OBJECTION", issue_type="substitution", issue_location="step 1",
            evidence="x=2 fails the original constraint", repairable=True,
        )
        self.assertEqual((False, "fresh_review_not_passed"), replacement_decision(finding, FreshReview("UNKNOWN")))
        self.assertEqual((False, "fresh_review_not_passed"), replacement_decision(finding, FreshReview("FAIL")))
        self.assertEqual((True, "fresh_review_supported_replacement"), replacement_decision(finding, FreshReview("PASS")))


if __name__ == "__main__":
    unittest.main()
