"""Runner report boundary (Issue #15 P0): per-record field retention, separate
failure statistics and the full native/contract verdict comparison — all on
fixed synthetic rows and stage events, never touching a real model.
"""
import json
import unittest

from scripts.run_external_hard_sets_smoke import (
    analyze,
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


if __name__ == "__main__":
    unittest.main()
