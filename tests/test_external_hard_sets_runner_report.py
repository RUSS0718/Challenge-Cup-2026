"""Runner report boundary (Issue #15 P0): per-record field retention, separate
failure statistics and the full native/contract verdict comparison — all on
fixed synthetic rows and stage events, never touching a real model.
"""
import unittest
from dataclasses import asdict
from unittest.mock import patch

import scripts.run_external_hard_sets_smoke as runner
from scripts.run_external_hard_sets_smoke import (
    FSDF_CANDIDATE_FLAGS,
    FSDF_V2_FLAGS,
    analyze,
    arm_v2_metrics,
    arm_config,
    assign_arms,
    assign_arms_paired,
    client_diagnostics,
    compact_trace,
)


def fsdf_event(**overrides):
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


class CompactTraceTest(unittest.TestCase):
    def test_keeps_stage_failure_source_and_budget_fields(self):
        trace = [
            fsdf_event(
                stage="deepen",
                status="protocol_failed",
                error_category="invalid_response",
                selected_branch="B",
                fallback_source="unknown",
                private_model_text="SHOULD_NOT_SURVIVE",
            ),
            fsdf_event(
                stage="finalize",
                status="unknown",
                fallback_source="finish_unknown",
                handoff_missing_fields=["CANDIDATE_D"],
                handoff_clipped=True,
                handoff_unknown_fields=["DERIVED"],
                handoff_unclosed_fields=["RISK"],
                handoff_field_states={"CANDIDATE_D": "absent", "DERIVED": "unknown"},
                handoff_all_fields_present=False,
                handoff_has_derived_content=False,
                handoff_has_candidate_result=False,
                d_candidate_visible_to_e=False,
                token_usage="unavailable",
            ),
        ]
        compact = compact_trace(trace)
        self.assertEqual("protocol_failed", compact[0]["status"])
        self.assertEqual("invalid_response", compact[0]["error_category"])
        self.assertEqual("B", compact[0]["selected_branch"])
        self.assertEqual(8192, compact[0]["max_tokens"])
        self.assertEqual("finish_unknown", compact[1]["fallback_source"])
        self.assertEqual(["CANDIDATE_D"], compact[1]["handoff_missing_fields"])
        self.assertTrue(compact[1]["handoff_clipped"])
        self.assertEqual({"CANDIDATE_D": "absent", "DERIVED": "unknown"}, compact[1]["handoff_field_states"])
        self.assertEqual(["RISK"], compact[1]["handoff_unclosed_fields"])
        self.assertFalse(compact[1]["handoff_all_fields_present"])
        self.assertNotIn("private_model_text", compact[0])

    def test_baseline_traces_without_stage_fields_compact_unchanged(self):
        trace = [{"step": "finalize", "status": "selected", "model_calls": 2, "extra": 1}]
        compact = compact_trace(trace)
        self.assertEqual({"step": "finalize", "status": "selected", "model_calls": 2}, compact[0])

    def test_v2_summary_keeps_bounded_candidate_metadata_only(self):
        trace = [{
            "stage": "arm_v2_summary",
            "method": "arm_harness_v2",
            "profile": "selective",
            "candidate_a": {
                "value": "117",
                "valid": True,
                "trust": "medium",
                "trust_reason": "high_reasoning_risk_single_sample",
            },
            "second_sample_triggered": True,
            "private_prompt": "must not survive",
        }]
        compact = compact_trace(trace)[0]
        self.assertEqual("117", compact["candidate_a"]["value"])
        self.assertEqual("medium", compact["candidate_a"]["trust"])
        self.assertTrue(compact["second_sample_triggered"])
        self.assertNotIn("private_prompt", compact)


class SolveStatusAndTimeoutReportTest(unittest.TestCase):
    def test_timeout_then_success_keeps_final_status_and_records_recovery(self):
        class FakeClient:
            finish_reasons = ["length", "stop"]
            completion_tokens = [10, 12]
            latencies = [1.0, 0.5]
            request_diagnostics = [
                {
                    "logical_call_index": 0,
                    "request_sequence": 1,
                    "status": "error",
                    "error_category": "timeout",
                    "max_tokens": 100,
                    "completion_tokens": 0,
                    "finish_reason": "timeout",
                    "duration_seconds": 1.0,
                },
                {
                    "logical_call_index": 1,
                    "request_sequence": 2,
                    "status": "ok",
                    "error_category": None,
                    "max_tokens": 100,
                    "completion_tokens": 12,
                    "finish_reason": "stop",
                    "duration_seconds": 0.5,
                },
            ]

        class FakeAgent:
            def __init__(self, client, config):
                self.client = client

            def solve(self, problem, metadata):
                return {
                    "final_response": "Final answer: 42",
                    "extracted_answer": "42",
                    "trace": [],
                }

        task = {
            "set_id": "set_b_aime",
            "item": {
                "item_id": "timeout-recovered",
                "problem": "Find the integer.",
                "answer": "42",
                "domain": "algebra",
                "language": "EN",
            },
            "arm": "v1",
            "seed": 1,
            "task_idx": "set_b_aime-0",
        }
        with patch.object(runner, "InternChatClient", return_value=FakeClient()), \
                patch.object(runner, "ReasoningAgent", FakeAgent):
            record = runner.solve_one(task, timeout=1, api_key="")

        self.assertEqual("ok", record["status"])
        self.assertEqual(["timeout"], record["request_error_categories"])
        self.assertEqual("correct", record["native"]["verdict"])
        self.assertEqual("correct", record["contract"]["verdict"])
        self.assertTrue(record["nonempty_final"])
        self.assertTrue(record["contract_extractable"])

        overall = analyze([record])["overall"]
        self.assertEqual(1, overall["request_timeout_n"])
        self.assertEqual(1, overall["timeout_recovered_n"])
        self.assertEqual(1, overall["timeout_recovered_correct_n"])
        self.assertEqual(0, overall["final_unknown_after_timeout_n"])
        self.assertEqual(0, overall["model_error"])

    def test_timeout_and_final_abstention_are_distinct_from_recovery(self):
        recovered = make_row(row_id="recovered", final="42", status="error:timeout")
        recovered["request_error_categories"] = ["timeout"]
        recovered["client_request_diagnostics"] = [
            {"status": "error", "error_category": "timeout", "duration_seconds": 1.0},
            {"status": "ok", "error_category": None, "duration_seconds": 1.0},
        ]
        timed_out_unknown = make_row(
            row_id="timed-out-unknown",
            final="UNKNOWN",
            native="invalid",
            contract="invalid",
            status="error:timeout",
        )
        timed_out_unknown["client_request_diagnostics"] = [
            {"status": "error", "error_category": "timeout", "duration_seconds": 1.0},
        ]
        no_timeout_unknown = make_row(
            row_id="no-timeout-unknown",
            final="UNKNOWN",
            native="invalid",
            contract="invalid",
        )
        no_timeout_unknown["client_request_diagnostics"] = [
            {"status": "ok", "error_category": None, "duration_seconds": 1.0},
        ]

        overall = analyze([recovered, timed_out_unknown, no_timeout_unknown])["overall"]
        self.assertEqual(2, overall["request_timeout_n"])
        self.assertEqual(1, overall["timeout_recovered_n"])
        self.assertEqual(1, overall["final_unknown_after_timeout_n"])
        self.assertEqual(1, overall["no_timeout_abstain_n"])

    def test_truncated_candidate_survives_later_request_failure(self):
        class FakeClient:
            finish_reasons = ["length", "stop"]
            completion_tokens = [100, 0]
            request_diagnostics = [
                {
                    "logical_call_index": 0,
                    "request_sequence": 1,
                    "status": "ok",
                    "error_category": None,
                    "completion_tokens": 100,
                    "finish_reason": "length",
                    "duration_seconds": 1.0,
                },
                {
                    "logical_call_index": 1,
                    "request_sequence": 2,
                    "status": "error",
                    "error_category": "model_error",
                    "completion_tokens": 0,
                    "finish_reason": "error",
                    "duration_seconds": 1.0,
                },
            ]

        class FakeAgent:
            def __init__(self, client, config):
                self.client = client

            def solve(self, problem, metadata):
                return {
                    "final_response": "Final answer: 42",
                    "extracted_answer": "42",
                    "trace": [{
                        "step": "finalize",
                        "status": "selected",
                        "reason": "truncated_with_candidate",
                    }],
                }

        task = {
            "set_id": "set_b_aime",
            "item": {
                "item_id": "truncated-candidate",
                "problem": "Find the integer.",
                "answer": "42",
                "domain": "algebra",
                "language": "EN",
            },
            "arm": "v1",
            "seed": 1,
            "task_idx": "set_b_aime-1",
        }
        with patch.object(runner, "InternChatClient", return_value=FakeClient()), \
                patch.object(runner, "ReasoningAgent", FakeAgent):
            record = runner.solve_one(task, timeout=1, api_key="")

        self.assertEqual("ok", record["status"])
        self.assertEqual("42", record["extracted_answer"])
        self.assertEqual("42", record["pred"])
        self.assertEqual(["model_error"], record["request_error_categories"])
        self.assertEqual("truncated_with_candidate", record["trace"][0]["reason"])
        self.assertEqual(0, analyze([record])["overall"]["model_error"])


class ClientDiagnosticsTest(unittest.TestCase):
    def test_bounded_and_tolerant_of_missing_attributes(self):
        class FullClient:
            finish_reasons = ["length"] * 12
            completion_tokens = [1] * 12

        self.assertEqual(8, len(client_diagnostics(FullClient())["finish_reasons"]))
        self.assertEqual(8, len(client_diagnostics(FullClient())["completion_tokens"]))

        class BareClient:
            pass

        self.assertEqual([], client_diagnostics(BareClient())["finish_reasons"])
        self.assertEqual([], client_diagnostics(BareClient())["completion_tokens"])


class ArmSupportTest(unittest.TestCase):
    def test_arm_configs_differ_only_in_v2_flags(self):
        v1 = asdict(arm_config("v1"))
        v2 = asdict(arm_config("v2"))
        for flag in FSDF_V2_FLAGS:
            self.assertFalse(v1[flag])
            self.assertTrue(v2[flag])
            del v1[flag], v2[flag]
        self.assertEqual(v1, v2)
        with self.assertRaises(ValueError):
            arm_config("v3")

    def test_fesf_experiment_arms_pin_separate_paths_and_thinking_off(self):
        fsdf = arm_config("fsdf_v1_tkoff")
        fesf = arm_config("fesf_v1_tkoff_exact_eval")
        self.assertTrue(fsdf.enable_fork_select_deepen_finish)
        self.assertFalse(fsdf.enable_fesf_v1)
        self.assertFalse(fsdf.enable_fesf_exact_eval)
        self.assertFalse(fesf.enable_fork_select_deepen_finish)
        self.assertTrue(fesf.enable_fesf_v1)
        self.assertTrue(fesf.enable_fesf_exact_eval)
        self.assertFalse(fesf.enable_fesf_claim_dsl)
        dsl = arm_config("fesf_v1_tkoff_claim_dsl")
        self.assertTrue(dsl.enable_fesf_v1)
        self.assertTrue(dsl.enable_fesf_exact_eval)
        self.assertTrue(dsl.enable_fesf_claim_dsl)
        from scripts.run_external_hard_sets_smoke import arm_thinking_mode

        self.assertIs(arm_thinking_mode("fsdf_v1_tkoff"), False)
        self.assertIs(arm_thinking_mode("fesf_v1_tkoff_exact_eval"), False)
        self.assertIs(arm_thinking_mode("fesf_v1_tkoff_claim_dsl"), False)

    def test_submission_profile_equals_v1_anchor_arm(self):
        # The official profile follows the FSDF v1 rollback anchor; canaries
        # remain explicit arm-only candidates.
        from user_agent import SUBMISSION_CONFIG

        self.assertEqual(asdict(arm_config("v1")), asdict(SUBMISSION_CONFIG))
        self.assertTrue(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)
        self.assertFalse(SUBMISSION_CONFIG.enable_fesf_v1)
        self.assertFalse(SUBMISSION_CONFIG.enable_fesf_exact_eval)
        v1 = arm_config("v1")
        for flag in FSDF_CANDIDATE_FLAGS:
            self.assertFalse(getattr(v1, flag), flag)

    def test_arm_v2_profiles_pin_the_documented_modes(self):
        single = arm_config("arm-v2-single")
        selective = arm_config("arm-v2-selective")
        long_timeout = arm_config("arm-v2-long-timeout")
        salvage = arm_config("arm-v2-salvage")

        self.assertEqual("v2", single.arm_harness_version)
        self.assertEqual("single", single.arm_v2_mode)
        self.assertEqual("selective", selective.arm_v2_mode)
        self.assertEqual("long_timeout", long_timeout.arm_v2_mode)
        self.assertEqual(60, long_timeout.arm_primary_timeout_seconds)
        self.assertEqual("salvage", salvage.arm_v2_mode)
        self.assertEqual("compact_salvage", salvage.arm_timeout_recovery_mode)
        self.assertEqual(30, salvage.arm_primary_timeout_seconds)
        self.assertEqual("v1", arm_config("v1").arm_harness_version)

    def test_v2_reliability_metrics_are_reported_separately(self):
        def v2_row(row_id, verdict, **fields):
            row = make_row(row_id=row_id, native=verdict, contract=verdict)
            row.update({"arm": "arm-v2-selective", "arm_v2_summary": {"stage": "arm_v2_summary"}})
            row.update(fields)
            return row

        metrics = arm_v2_metrics([
            v2_row("trusted-correct", "correct", early_stop=True, candidate_a_trust="high"),
            v2_row("trusted-wrong", "incorrect", early_stop=True, candidate_a_trust="high"),
            v2_row("agreement", "correct", second_sample_triggered=True, agreement=True),
            v2_row(
                "conflict",
                "incorrect",
                second_sample_triggered=True,
                conflict=True,
                resolver_triggered=True,
            ),
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

    def test_v2hd_arm_differs_from_v2_only_in_handoff_first_d(self):
        v2 = asdict(arm_config("v2"))
        v2hd = asdict(arm_config("v2hd"))
        self.assertFalse(v2["enable_fsdf_handoff_first_d"])
        self.assertTrue(v2hd["enable_fsdf_handoff_first_d"])
        del v2["enable_fsdf_handoff_first_d"], v2hd["enable_fsdf_handoff_first_d"]
        self.assertEqual(v2, v2hd)

    def test_v2hd_dre_arm_differs_from_v2hd_only_in_d_result_to_e(self):
        v2hd = asdict(arm_config("v2hd"))
        dre = asdict(arm_config("v2hd_dre"))
        self.assertFalse(v2hd["enable_fsdf_d_result_to_e"])
        self.assertTrue(dre["enable_fsdf_d_result_to_e"])
        del v2hd["enable_fsdf_d_result_to_e"], dre["enable_fsdf_d_result_to_e"]
        self.assertEqual(v2hd, dre)

    def test_v2hd_hs_eu_arm_differs_from_lineage_base_only_in_e_budget(self):
        # v2hd_hs_eu 的谱系基座是 v2hd_hs_of（含 open_first_e），单变量 = e_budget_up。
        base = asdict(arm_config("v2hd_hs_of"))
        eu = asdict(arm_config("v2hd_hs_eu"))
        self.assertFalse(base["enable_fsdf_e_budget_up"])
        self.assertTrue(eu["enable_fsdf_e_budget_up"])
        del base["enable_fsdf_e_budget_up"], eu["enable_fsdf_e_budget_up"]
        self.assertEqual(base, eu)

    def test_v2hd_bs_hs_tkoff_arm_matches_frontier_config(self):
        # 思考开关是 client 级（ARM_THINKING_MODE），AgentConfig 必须与前沿一致。
        frontier = asdict(arm_config("v2hd_bs_hs"))
        tkoff = asdict(arm_config("v2hd_bs_hs_tkoff"))
        self.assertEqual(frontier, tkoff)
        from scripts.run_external_hard_sets_smoke import arm_thinking_mode

        self.assertIsNone(arm_thinking_mode("v2hd_bs_hs"))
        self.assertIs(arm_thinking_mode("v2hd_bs_hs_tkoff"), False)
        with self.assertRaises(ValueError):
            arm_config("v2hd_bs_hs_tkoff_typo")

    def test_paired_assignment_covers_every_arm_with_rotation(self):
        tasks = [{"i": i} for i in range(3)]
        paired = assign_arms_paired(tasks, ["v2", "v2hd"])
        self.assertEqual(6, len(paired))
        by_item = {}
        for entry in paired:
            by_item.setdefault(entry["i"], []).append((entry["arm"], entry["pair_order"]))
        # 每道题两臂各一次
        for item_id, entries in by_item.items():
            self.assertEqual({"v2", "v2hd"}, {arm for arm, _ in entries})
            self.assertEqual({0, 1}, {order for _, order in entries})
        # 先臂逐题轮换（按 pair_order==0 取先跑的臂）
        first_arm = {item_id: next(arm for arm, order in entries if order == 0)
                     for item_id, entries in by_item.items()}
        self.assertEqual({0: "v2", 1: "v2hd", 2: "v2"}, first_arm)
        self.assertEqual(assign_arms_paired([{"i": 0}], ["v2", "v2hd"]),
                         assign_arms_paired([{"i": 0}], ["v2", "v2hd"]))
        with self.assertRaises(ValueError):
            assign_arms_paired([], [])

    def test_assign_arms_is_deterministic_and_balanced(self):
        tasks = [{"i": i} for i in range(7)]
        assign_arms(tasks, ["v1", "v2"])
        self.assertEqual(["v1", "v2"] * 3 + ["v1"], [t["arm"] for t in tasks])
        tasks2 = [{"i": i} for i in range(7)]
        assign_arms(tasks2, ["v1", "v2"])
        self.assertEqual([t["arm"] for t in tasks], [t["arm"] for t in tasks2])
        with self.assertRaises(ValueError):
            assign_arms([], [])

    def test_by_arm_report_grouping(self):
        def row(rid, arm, verdict):
            base = make_row(row_id=rid, native=verdict, contract=verdict)
            base["arm"] = arm
            return base

        rows = [
            row("a1", "v1", "correct"),
            row("a2", "v1", "incorrect"),
            row("b1", "v2", "correct"),
            row("b2", "v2", "correct"),
        ]
        report = analyze(rows)
        self.assertEqual({"v1", "v2"}, set(report["by_arm"]))
        self.assertEqual(1, report["by_arm"]["v1"]["native_correct"])
        self.assertEqual(2, report["by_arm"]["v2"]["native_correct"])
        self.assertEqual(2, report["by_arm"]["v1"]["n"])
        self.assertEqual(2, report["by_arm"]["v2"]["n"])


if __name__ == "__main__":
    unittest.main()
