"""Regression tests for hard-set judgment and aggregate reporting modules."""

import json
import unittest

from scripts.external_hard_sets_aggregate import analyze, arm_v2_metrics, stage_health
from scripts.external_hard_sets_judging import contract_check, extract_contract_answer
from scripts.external_hard_sets_qualification import analyze_skill_qualification


def fsdf_event(**overrides):
    """Build a compact synthetic FSDF stage event for report tests."""
    event = {
        "method": "fork_select_deepen_finish_v1",
        "stage": "deepen",
        "status": "ok",
        "model_calls": 4,
        "max_tokens": 8192,
        "elapsed_bucket": "normal",
    }
    event.update(overrides)
    return event


def make_row(
    row_id="item-1",
    status="ok",
    final="42",
    native="correct",
    contract="correct",
    trace=None,
    domain="algebra",
    set_id="set_b_aime",
):
    """Build a minimal answer row accepted by the aggregate report."""
    return {
        "set_id": set_id,
        "item_id": row_id,
        "problem_group_id": "grp-1",
        "language": "ZH",
        "domain": domain,
        "source_family": "AIME",
        "seed": 1,
        "status": status,
        "final_response": final,
        "extracted_answer": final,
        "pred": final,
        "gold": "42",
        "native": {"verdict": native, "detail": "synthetic"},
        "contract": {"verdict": contract, "detail": "synthetic"},
        "verdict_match": native == contract,
        "nonempty_final": bool(final.strip()),
        "contract_extractable": final.strip().upper() != "UNKNOWN",
        "format_ok": final.strip().upper() != "UNKNOWN",
        "json_serializable": True,
        "model_calls": 5,
        "duration_seconds": 1.0,
        "trace": trace or [],
    }


class StageHealthTest(unittest.TestCase):
    """Keep stage failures separate from final answer verdicts."""

    def test_failure_modes_are_counted_separately(self):
        """Count client, protocol, skip, and handoff failures independently."""
        rows = [
            make_row(row_id="r0", status="error:model_error"),
            make_row(row_id="r1", trace=[fsdf_event(status="failed", error_category="rate_limit")]),
            make_row(row_id="r2", trace=[fsdf_event(status="failed", error_category="invalid_response")]),
            make_row(row_id="r3", trace=[fsdf_event(status="protocol_failed", error_category="invalid_response")]),
            make_row(row_id="r4", trace=[fsdf_event(stage="finish", status="skipped", error_category="soft_deadline")]),
            make_row(
                row_id="r5",
                trace=[fsdf_event(stage="finalize", status="unknown", handoff_missing_fields=["CANDIDATE_D"], handoff_clipped=True)],
            ),
        ]
        health = stage_health(rows)
        self.assertEqual(1, health["stage_client_errors"])
        self.assertEqual(1, health["stage_invalid_responses"])
        self.assertEqual(1, health["stage_protocol_failures"])
        self.assertEqual(1, health["stage_skipped"])
        self.assertEqual(1, health["handoff_missing"])
        self.assertEqual(1, health["handoff_clipped"])

    def test_old_records_without_stage_events_are_safe(self):
        """Treat legacy rows without stage events as zero stage failures."""
        health = stage_health([make_row(row_id="old", trace=[{"step": "finalize", "status": "selected"}])])
        for value in health.values():
            self.assertEqual(0, value)


class AnalyzeVerdictMatrixTest(unittest.TestCase):
    """Verify the report preserves native/contract disagreement details."""

    def test_full_native_contract_comparison(self):
        """Report all verdict cells and the complete mismatch count."""
        rows = [
            make_row(row_id="a", native="correct", contract="correct"),
            make_row(row_id="b", native="correct", contract="incorrect"),
            make_row(row_id="c", native="incorrect", contract="correct"),
            make_row(row_id="d", native="invalid", contract="incorrect", final="UNKNOWN"),
        ]
        overall = analyze(rows)["overall"]
        self.assertEqual(2, overall["native_correct"])
        self.assertEqual(1, overall["native_incorrect"])
        self.assertEqual(1, overall["invalid"])
        self.assertEqual(2, overall["contract_correct"])
        self.assertEqual(2, overall["contract_incorrect"])
        self.assertEqual(0, overall["contract_invalid"])
        self.assertEqual(3, overall["verdict_mismatch"])
        self.assertTrue(overall["correct_count_consistent"])
        self.assertEqual(1, overall["unknown_final"])
        self.assertIn("judge_note", analyze(rows))

    def test_equal_correct_counts_do_not_hide_mismatches(self):
        """Keep per-row mismatch counts even when correct totals agree."""
        overall = analyze([
            make_row(row_id="a", native="correct", contract="incorrect"),
            make_row(row_id="b", native="incorrect", contract="correct"),
        ])["overall"]
        self.assertEqual(overall["native_correct"], overall["contract_correct"])
        self.assertTrue(overall["correct_count_consistent"])
        self.assertEqual(2, overall["verdict_mismatch"])

    def test_report_is_json_serializable(self):
        """Keep the complete report suitable for machine-readable output."""
        self.assertIsInstance(json.dumps(analyze([make_row(trace=[fsdf_event()])])), str)

    def test_natural_language_final_is_not_contract_format_success(self):
        """Reject prose even when it contains a plausible numeric answer."""
        final = "the number of such $n$ is $45$."
        self.assertEqual("", extract_contract_answer(final, "OlymMATH"))
        self.assertEqual("invalid", contract_check(final, "47", "OlymMATH")["verdict"])
        row = make_row(row_id="prose-final", final=final, native="incorrect", contract="invalid")
        row["contract_extractable"] = False
        row["format_ok"] = False
        overall = analyze([row])["overall"]
        self.assertEqual(1, overall["nonempty_final"])
        self.assertEqual(0, overall["contract_extractable"])
        self.assertEqual(0, overall["format_ok"])

    def test_aime_contract_requires_marked_integer_answer(self):
        """Require a marked integer rather than an incidental integer in prose."""
        self.assertEqual("correct", contract_check("Final answer: 236", "236", "AIME")["verdict"])
        self.assertEqual("invalid", contract_check("The derivation mentions 236 but gives no marked answer.", "236", "AIME")["verdict"])
        self.assertEqual("invalid", contract_check("Final answer: 236.5", "236", "AIME")["verdict"])


class SkillQualificationReportTest(unittest.TestCase):
    """Keep qualification gates based on scorer telemetry only."""

    def test_qualification_metrics_use_scorer_labels_and_bounded_events(self):
        """Score applicability, tool execution, and evidence consumption."""
        def qrow(rid, applicable, selected, usable=True, consumed=True):
            """Build one synthetic qualification row."""
            route = {
                "stage": "route",
                "skill_name": "exact-evaluation" if selected else "NONE",
                "skill_choice_parsed": True,
                "applicability": "yes" if selected else "no",
            }
            trace = [route]
            events = []
            if selected and usable:
                events.append({
                    "stage": "tool_exact_eval",
                    "status": "EXACT",
                    "execution_status": "ok",
                    "claim_known": True,
                    "binding_ok": True,
                    "tool_request_valid": True,
                    "evidence_consumed": consumed,
                    "evidence_id": "T1",
                })
                trace.extend(events)
            row = make_row(row_id=rid, set_id="fesf_skill_qualification", trace=trace)
            row.update({
                "qualification_applicable": applicable,
                "skill_selected": selected,
                "skill_choice_parsed": True,
                "route_applicability": "yes" if selected else "no",
                "tool_request_count": len(events),
                "tool_events": events,
            })
            return row

        report = analyze_skill_qualification([
            qrow("a", True, True),
            qrow("b", True, False),
            qrow("c", False, False),
            qrow("d", False, True),
        ])
        self.assertEqual(2, report["applicable_n"])
        self.assertEqual(1, report["applicable_selected"])
        self.assertEqual(1, report["non_applicable_none"])
        self.assertEqual(2, report["tool_execution_success_n"])
        self.assertEqual(2, report["evidence_consumed_n"])
        self.assertFalse(report["qualification_pass"])


class ArmV2MetricTest(unittest.TestCase):
    """Verify v2 reliability counters stay separate from generic accuracy."""

    def test_v2_reliability_metrics_are_reported_separately(self):
        """Count trusted candidates, samples, conflicts, and resolver outcomes."""
        def v2_row(row_id, verdict, **fields):
            """Build one synthetic v2 row."""
            row = make_row(row_id=row_id, native=verdict, contract=verdict)
            row.update({"arm": "arm-v2-selective", "arm_v2_summary": {"stage": "arm_v2_summary"}})
            row.update(fields)
            return row

        metrics = arm_v2_metrics([
            v2_row("trusted-correct", "correct", early_stop=True, candidate_a_trust="high"),
            v2_row("trusted-wrong", "incorrect", early_stop=True, candidate_a_trust="high"),
            v2_row("agreement", "correct", second_sample_triggered=True, agreement=True),
            v2_row("conflict", "incorrect", second_sample_triggered=True, conflict=True, resolver_triggered=True),
        ])
        self.assertEqual(2, metrics["trusted_candidate_n"])
        self.assertEqual(1, metrics["trusted_candidate_correct_n"])
        self.assertEqual(0.5, metrics["trusted_candidate_precision"])
        self.assertEqual(1, metrics["wrong_early_stop_n"])
        self.assertEqual(0.5, metrics["wrong_early_stop_rate"])
        self.assertEqual(2, metrics["second_sample_n"])
        self.assertEqual(1, metrics["agreement_correct_n"])
        self.assertEqual(1, metrics["conflict_n"])
        self.assertEqual(1, metrics["resolver_n"])
        self.assertEqual(0, metrics["resolver_correct_n"])


if __name__ == "__main__":
    unittest.main()
