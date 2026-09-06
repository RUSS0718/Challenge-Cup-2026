"""Runner report boundary (Issue #15 P0): per-record field retention, separate
failure statistics and the full native/contract verdict comparison — all on
fixed synthetic rows and stage events, never touching a real model.
"""
import json
import unittest
from dataclasses import asdict

from scripts.run_external_hard_sets_smoke import (
    FSDF_CANDIDATE_FLAGS,
    FSDF_V2_FLAGS,
    analyze,
    arm_config,
    assign_arms,
    assign_arms_paired,
    client_diagnostics,
    compact_trace,
    stage_health,
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


class StageHealthTest(unittest.TestCase):
    def test_failure_modes_are_counted_separately(self):
        rows = [
            # 顶层 runner 失败
            make_row(row_id="r0", status="error:model_error"),
            # 阶段 client 异常（即使 solve 顶层成功也保留）
            make_row(
                row_id="r1",
                trace=[fsdf_event(status="failed", error_category="rate_limit")],
            ),
            # 非字符串/空响应
            make_row(
                row_id="r2",
                trace=[fsdf_event(status="failed", error_category="invalid_response")],
            ),
            # 协议失败
            make_row(
                row_id="r3",
                trace=[fsdf_event(status="protocol_failed", error_category="invalid_response")],
            ),
            # 截止时间跳过
            make_row(
                row_id="r4",
                trace=[fsdf_event(stage="finish", status="skipped", error_category="soft_deadline")],
            ),
            # 交接缺失 / 裁剪
            make_row(
                row_id="r5",
                trace=[
                    fsdf_event(
                        stage="finalize",
                        status="unknown",
                        handoff_missing_fields=["CANDIDATE_D"],
                        handoff_clipped=True,
                    )
                ],
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
        rows = [make_row(row_id="old", trace=[{"step": "finalize", "status": "selected"}])]
        health = stage_health(rows)
        for value in health.values():
            self.assertEqual(0, value)


class AnalyzeVerdictMatrixTest(unittest.TestCase):
    def test_full_native_contract_comparison(self):
        rows = [
            make_row(row_id="a", native="correct", contract="correct"),
            make_row(row_id="b", native="correct", contract="incorrect"),
            make_row(row_id="c", native="incorrect", contract="correct"),
            make_row(row_id="d", native="invalid", contract="incorrect", final="UNKNOWN"),
        ]
        report = analyze(rows)
        overall = report["overall"]
        self.assertEqual(2, overall["native_correct"])
        self.assertEqual(1, overall["native_incorrect"])
        self.assertEqual(1, overall["invalid"])
        self.assertEqual(2, overall["contract_correct"])
        self.assertEqual(2, overall["contract_incorrect"])
        self.assertEqual(0, overall["contract_invalid"])
        # 逐题完整对比：b(c/i)、c(i/c)、d(inv/i) 三题判定不一致。
        self.assertEqual(3, overall["verdict_mismatch"])
        self.assertTrue(overall["correct_count_consistent"])
        self.assertEqual(1, overall["unknown_final"])
        self.assertIn("judge_note", report)

    def test_equal_correct_counts_do_not_hide_mismatches(self):
        rows = [
            make_row(row_id="a", native="correct", contract="incorrect"),
            make_row(row_id="b", native="incorrect", contract="correct"),
        ]
        overall = analyze(rows)["overall"]
        self.assertEqual(overall["native_correct"], overall["contract_correct"])
        self.assertTrue(overall["correct_count_consistent"])
        self.assertEqual(2, overall["verdict_mismatch"])

    def test_report_is_json_serializable(self):
        rows = [make_row(row_id="a", trace=[fsdf_event()])]
        blob = json.dumps(analyze(rows), ensure_ascii=False)
        self.assertIsInstance(blob, str)


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

    def test_submission_profile_equals_v2hd_dre_arm(self):
        # 2026-09-06 用户授权 canary：官方提交配置必须与 v2hd_dre 诊断臂完全一致，
        # 且臂定义显式钉住全部候选开关（v1 锚点臂不受提交配置漂移影响）。
        from user_agent import SUBMISSION_CONFIG

        self.assertEqual(asdict(arm_config("v2hd_dre")), asdict(SUBMISSION_CONFIG))
        v1 = arm_config("v1")
        for flag in FSDF_CANDIDATE_FLAGS:
            self.assertFalse(getattr(v1, flag), flag)

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
