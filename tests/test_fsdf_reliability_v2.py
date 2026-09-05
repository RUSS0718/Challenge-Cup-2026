"""FSDF v2 reliability increments (Issue #15) — zero-model acceptance tests.

Boundaries follow the spec's testing decisions: ReasoningAgent.solve() with a
ScriptedClient (public request messages + returned dict) and the existing
FakeClock.  Every increment must stay independently selectable and reproduce
FSDF v1 behaviour when off.
"""
import json
import unittest

from reasoning_agent.fork_select_deepen_finish import (
    ANALYZE_PROMPT,
    FINISH_PROMPT,
    FINISH_PROMPT_V2,
    L0_TOKEN_SEQUENCE,
    STAGE_TOKEN_SEQUENCE,
    ForkSelectDeepenFinishRelay,
    RelayOptions,
)
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class ScriptedClient:
    def __init__(self, responses, on_chat=None):
        self.responses = list(responses)
        self.calls = []
        self.on_chat = on_chat

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        if self.on_chat:
            self.on_chat(self)
        if not self.responses:
            raise AssertionError("scripted client exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def analysis():
    return (
        "GOAL: 求唯一答案\n"
        "ANSWER_TYPE: 整数\n"
        "CONSTRAINTS: 定义域和边界\n"
        "STRUCTURE: 代数关系\n"
        "BOTTLENECK: 证明关键等式"
    )


def idea(branch, method=None, secret=""):
    method = method or ("标准正向构造" if branch == "B" else "反推不变量")
    return (
        f"BRANCH: {branch}\nMETHOD: {method}\nKEY_LEMMA: 关键引理成立\n"
        "PLAN: 1.列条件 2.推导 3.检查边界\nEXPECTED_FORM: 整数\n"
        f"RISK: {secret or '局部边界'}"
    )


def deep(branch="B", candidate="7", extra=""):
    return (
        f"SELECTED_BRANCH: {branch}\nSELECTION_REASON: 覆盖约束且闭环最短\n"
        f"CANDIDATE_D: {candidate}\nDERIVED: x={candidate}\nOPEN: 无\n"
        "CHECKS: 定义域已检查\nRISK: 无\n"
        f"{extra}"
    )


def finish(candidate="7", final="7", extra=""):
    return f"CANDIDATE_E: {candidate}\n复核完成。\nFINAL: {final}\n{extra}"


def solve_v2(responses, options, problem="求一个非平凡整数 n。", clock=None):
    client = ScriptedClient(responses)
    relay = ForkSelectDeepenFinishRelay(client, clock=clock or FakeClock(), options=options)
    result = relay.solve(problem, "calculation")
    return client, result


ALL_ON = RelayOptions(
    diagnostics_v2=True,
    multiline_handoff_v2=True,
    final_confirmation_v2=True,
    finish_prompt_v2=True,
)
P0_ONLY = RelayOptions(diagnostics_v2=True)
P1_ONLY = RelayOptions(multiline_handoff_v2=True)
P2A_ONLY = RelayOptions(final_confirmation_v2=True)
P2B_ONLY = RelayOptions(finish_prompt_v2=True)


def finalize_event(trace):
    return next(entry for entry in trace if entry["stage"] == "finalize")


def handoff_section(e_prompt):
    return e_prompt.split("D handoff：\n", 1)[1]


class F2P0DiagnosticsTest(unittest.TestCase):
    def test_p0_01_submission_profile_keeps_v1_flags_off(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_diagnostics_v2)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_multiline_handoff_v2)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_final_confirmation_v2)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_finish_prompt_v2)
        for flag in (
            "enable_fsdf_diagnostics_v2",
            "enable_fsdf_multiline_handoff_v2",
            "enable_fsdf_final_confirmation_v2",
            "enable_fsdf_finish_prompt_v2",
        ):
            self.assertFalse(getattr(AgentConfig(), flag), flag)
        self.assertTrue(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)

    def test_p0_02_diagnostics_do_not_change_requests_or_answers(self):
        # 同一 ScriptedClient 序列（含 D 协议失败 + E 失败）在 P0 开关前后
        # 产生完全相同的模型请求与 final_response。
        scripted = [
            analysis(),
            idea("B"),
            idea("C"),
            "SELECTED_BRANCH: 大概是B吧\nCANDIDATE_D: 42\nFINAL_D: 42",
            RuntimeError("e"),
        ]
        client_off, result_off = solve_v2(list(scripted), RelayOptions())
        client_on, result_on = solve_v2(list(scripted), P0_ONLY)
        self.assertEqual(client_off.calls, client_on.calls)
        self.assertEqual(result_off.final_response, result_on.final_response)

    def test_p0_03_finalize_event_carries_bounded_diagnostics(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate=""), finish()],
            P0_ONLY,
        )
        self.assertEqual(5, len(client.calls))
        event = finalize_event(result.trace)
        self.assertEqual("unavailable", event["token_usage"])
        self.assertEqual("unavailable", event["finish_reason"])
        self.assertIn("CANDIDATE_D", event["handoff_missing_fields"])
        self.assertIsInstance(event["handoff_clipped"], bool)
        self.assertIsInstance(event["candidate_present"], bool)
        # 诊断只含字段名与布尔，不含任何模型原文或题面。
        diag_blob = json.dumps(
            {k: event[k] for k in (
                "handoff_missing_fields",
                "handoff_conflict_fields",
                "handoff_clipped",
                "finish_context_clipped",
                "candidate_present",
            )},
            ensure_ascii=False,
        )
        self.assertNotIn("定义域", diag_blob)
        self.assertNotIn("求一个非平凡整数", diag_blob)
        json.dumps(result.trace, ensure_ascii=False)

    def test_p0_04_diagnostics_report_conflicting_and_missing_fields(self):
        repeated = deep() + "CANDIDATE_D: 43\n"
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), repeated, finish()],
            P0_ONLY,
        )
        event = finalize_event(result.trace)
        self.assertIn("CANDIDATE_D", event["handoff_conflict_fields"])
        self.assertEqual([], event["handoff_missing_fields"])
        # 重复冲突不影响 v1 答案链（P0 不改变行为）。
        self.assertEqual("7", result.final_response)

    def test_p0_05_off_event_has_no_v2_keys(self):
        _, result = solve_v2([analysis(), idea("B"), idea("C"), deep(), finish()], RelayOptions())
        event = finalize_event(result.trace)
        for key in (
            "handoff_missing_fields",
            "handoff_conflict_fields",
            "handoff_clipped",
            "finish_context_clipped",
            "token_usage",
            "finish_reason",
        ):
            self.assertNotIn(key, event)


class F2P1HandoffTest(unittest.TestCase):
    def multiline_deep(self, candidate="42"):
        return (
            "SELECTED_BRANCH: B\n"
            "SELECTION_REASON: 覆盖约束且闭环最短\n"
            f"CANDIDATE_D: {candidate}\n"
            "DERIVED: 由条件得 x^2 = 4x + 5\n"
            "整理得 x^2 - 4x - 5 = 0\n"
            "第2步: 因式分解得 (x-5)(x+1) = 0\n"
            "OPEN: 判断哪个根满足原约束\n"
            "CHECKS: 定义域已检查\n"
            "RISK: 无"
        )

    def test_p1_01_multiline_derived_key_steps_reach_e(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.multiline_deep(), finish()],
            P1_ONLY,
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("由条件得 x^2 = 4x + 5", e_prompt)
        self.assertIn("整理得 x^2 - 4x - 5 = 0", e_prompt)
        self.assertIn("因式分解得 (x-5)(x+1) = 0", e_prompt)
        self.assertIn("OPEN: 判断哪个根满足原约束", e_prompt)
        self.assertNotIn("HANDOFF_INCOMPLETE", e_prompt)
        self.assertEqual("7", result.final_response)

    def test_p1_02_empty_candidate_does_not_absorb_next_field(self):
        d_response = "SELECTED_BRANCH: B\nCANDIDATE_D:\nDERIVED: x=2\nOPEN: 无\nCHECKS: ok\nRISK: 无"
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        e_prompt = client.calls[4][0][1]["content"]
        section = handoff_section(e_prompt)
        self.assertIn("DERIVED: x=2", section)
        self.assertNotIn("CANDIDATE_D: DERIVED", section)
        self.assertIn("HANDOFF_INCOMPLETE: true", section)
        self.assertEqual("7", result.final_response)

    def test_p1_03_repeated_identical_values_dedupe(self):
        d_response = deep(candidate="42") + "CANDIDATE_D: 42\n"
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertEqual(1, section.count("CANDIDATE_D: 42"))
        self.assertNotIn("HANDOFF_CONFLICT", section)

    def test_p1_04_repeated_conflicting_values_fail_closed(self):
        d_response = deep(candidate="42") + "CANDIDATE_D: 43\n"
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertIn("CANDIDATE_D_CONFLICT: true", section)
        self.assertNotIn("CANDIDATE_D: 42", section)
        self.assertNotIn("CANDIDATE_D: 43", section)
        self.assertIn("HANDOFF_CONFLICT: CANDIDATE_D", section)

    def test_p1_05_placeholder_then_value_is_an_update_not_conflict(self):
        d_response = deep(candidate="UNKNOWN") + "CANDIDATE_D: 42\n"
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertIn("CANDIDATE_D: 42", section)
        self.assertNotIn("HANDOFF_CONFLICT", section)
        self.assertNotIn("CANDIDATE_D: UNKNOWN", section)

    def test_p1_06_free_text_and_branch_echo_stay_excluded(self):
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nDERIVED: x=42\n"
            "自由推导：由对称性可知 x 为偶数，代入边界得唯一解 42，关键等式 2x=84 已确认。\n"
            "OPEN: 无\nCHECKS: ok\nRISK: 无\n" + idea("C", secret="C_ECHO_SECRET")
        )
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertNotIn("自由推导", e_prompt)
        self.assertNotIn("C_ECHO_SECRET", e_prompt)
        self.assertIn("OPEN: 无", e_prompt)
        self.assertEqual("7", result.final_response)

    def test_p1_07_budget_clips_whole_items_and_marks_loss_visible(self):
        derived_lines = [
            f"第{i}步: 中间结果推导过程记录 x_{i} = {i} * 3 + 7 + {i} * 11 与边界条件核对记录"
            for i in range(1, 61)
        ]
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: 42\n"
            "DERIVED: " + "\n".join(derived_lines) + "\n"
            "OPEN: 剩余未解步骤\nCHECKS: 检查结果\nRISK: 风险记录"
        )
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        # 只保留完整推导项：任何出现的行都必须完整，且没有字符级省略标记。
        self.assertNotIn("…[省略]…", section)
        for line in derived_lines:
            if line in section:
                self.assertEqual(1, section.count(line), line)
        self.assertIn("HANDOFF_PARTIAL: DERIVED", section)
        self.assertIn("HANDOFF_DROPPED: OPEN,CHECKS,CANDIDATE_D,RISK", section)
        self.assertIn("HANDOFF_INCOMPLETE: true", section)
        # 高优先级推导先于低优先级字段保留。
        self.assertIn("第1步: 中间结果推导过程记录 x_1 = 1 * 3 + 7 + 1 * 11 与边界条件核对记录", section)

    def test_p1_08_handoff_stays_within_existing_context_cap(self):
        big_derived = "DERIVED: " + "\n".join(f"行{i} = {i} + {i} * 2" for i in range(80))
        d_response = f"SELECTED_BRANCH: B\nCANDIDATE_D: 42\n{big_derived}\nOPEN: 无\nCHECKS: ok\nRISK: 无"
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            P1_ONLY,
        )
        e_prompt = client.calls[4][0][1]["content"]
        context = e_prompt.split("求一个非平凡整数 n。\n\n", 1)[1]
        self.assertLessEqual(len(context), 6500)
        self.assertEqual("7", result.final_response)

    def test_p1_09_conflict_and_missing_diagnosed_under_p1(self):
        d_response = deep(candidate="42") + "CANDIDATE_D: 43\n"
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, diagnostics_v2=True),
        )
        event = finalize_event(result.trace)
        self.assertIn("CANDIDATE_D", event["handoff_conflict_fields"])
        self.assertEqual([], event["handoff_missing_fields"])
        d_missing = "SELECTED_BRANCH: B\nSELECTION_REASON: r\nRISK: 无"
        _, result2 = solve_v2(
            [analysis(), idea("B"), idea("C"), d_missing, finish()],
            RelayOptions(multiline_handoff_v2=True, diagnostics_v2=True),
        )
        event2 = finalize_event(result2.trace)
        self.assertEqual(
            ["CANDIDATE_D", "DERIVED", "OPEN", "CHECKS"],
            event2["handoff_missing_fields"],
        )

    def test_p1_10_call_and_token_budget_unchanged(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.multiline_deep(), finish("8", "8")],
            ALL_ON,
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("8", result.final_response)


class F2P2aFinalConfirmationTest(unittest.TestCase):
    def test_p2a_01_explicit_unknown_never_revives_candidates(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="42"), finish(final="UNKNOWN")],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("finish_unknown", result.trace[-1]["fallback_source"])

    def test_p2a_02_conflicting_finals_fail_closed(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), "CANDIDATE_E: 7\nFINAL: 7\nFINAL: 8"],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("final_conflict", result.trace[-1]["fallback_source"])

    def test_p2a_03_placeholder_final_falls_back_to_confirmed_d_only(self):
        client, result = solve_v2(
            [
                analysis(),
                idea("B"),
                idea("C"),
                "SELECTED_BRANCH: B\nCANDIDATE_D: 5\nFINAL_D: 42",
                "CANDIDATE_E: 9\nFINAL: <result>",
            ],
            P2A_ONLY,
        )
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])

    def test_p2a_04_boxed_and_math_lines_are_not_answers(self):
        d_response = "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\n\\boxed{6}\nno final\n42"
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, "仍无结论"],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["fallback_source"])

    def test_p2a_05_unconfirmed_candidates_are_not_answers(self):
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5"), "CANDIDATE_E: 9"],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)

    def test_p2a_06_protocol_failed_d_raw_cannot_bypass_checks(self):
        _, result = solve_v2(
            [
                analysis(),
                idea("B"),
                idea("C"),
                "SELECTED_BRANCH: 大概是B吧\nCANDIDATE_D: 42\nFINAL_D: 42",
                RuntimeError("e"),
            ],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["fallback_source"])

    def test_p2a_07_d_explicit_unknown_and_d_conflicts(self):
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="42") + "FINAL_D: UNKNOWN", RuntimeError("e")],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        _, result2 = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="42") + "FINAL_D: 42\nFINAL_D: 43", RuntimeError("e")],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result2.final_response)
        self.assertEqual("deep_final_conflict", result2.trace[-1]["fallback_source"])

    def test_p2a_08_non_scalar_answers_keep_their_own_boundaries(self):
        for final in ("{1, 2}", "x > 5", "\\frac{1}{2}", "命题成立", "(1, 2)"):
            with self.subTest(final=final):
                _, result = solve_v2(
                    [analysis(), idea("B"), idea("C"), deep(), finish(final=final, extra="")],
                    P2A_ONLY,
                )
                self.assertEqual(final, result.final_response)

    def test_p2a_09_echoes_placeholders_and_method_descriptions_rejected(self):
        for final in ("答案", "CANDIDATE_E", "TBD", "使用反证法证明", "最终答案"):
            with self.subTest(final=final):
                _, result = solve_v2(
                    [analysis(), idea("B"), idea("C"), deep(candidate="7"), f"FINAL: {final}"],
                    P2A_ONLY,
                )
                self.assertEqual("UNKNOWN", result.final_response)

    def test_p2a_10_empty_final_marker_does_not_absorb_next_field(self):
        # 单行终答标记为空时不得吸收后续协议字段。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), "FINAL:\nCANDIDATE_E: 9"],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["fallback_source"])

    def test_p2a_11_mixed_unknown_and_value_fails_closed(self):
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), "FINAL: UNKNOWN\nFINAL: 7"],
            P2A_ONLY,
        )
        self.assertEqual("UNKNOWN", result.final_response)

    def test_p2a_12_valid_path_still_wins(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish("8", "8")],
            ALL_ON,
        )
        self.assertEqual(5, len(client.calls))
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("8", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])


class F2P2bFinishPromptTest(unittest.TestCase):
    def test_p2b_01_finish_prompt_variant_only_changes_e_stage(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            P2B_ONLY,
        )
        self.assertEqual(FINISH_PROMPT_V2, client.calls[4][0][0]["content"])
        self.assertNotIn("第一项输出 CANDIDATE_E", client.calls[4][0][0]["content"])
        self.assertIn("未解步骤", client.calls[4][0][0]["content"])
        # 其它阶段提示词不变。
        self.assertEqual(ANALYZE_PROMPT, client.calls[0][0][0]["content"])
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("7", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_p2b_02_off_uses_v1_prompt(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(),
        )
        self.assertEqual(FINISH_PROMPT, client.calls[4][0][0]["content"])


class F2RegressionGuardsTest(unittest.TestCase):
    def test_rg_01_l0_behaviour_identical_with_all_flags_on(self):
        client = ScriptedClient(["FINAL: 2"])
        result = ForkSelectDeepenFinishRelay(
            client, clock=FakeClock(), options=ALL_ON
        ).solve("1+1", "calculation")
        self.assertEqual(L0_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("2", result.final_response)

    def test_rg_02_off_path_matches_v1_fixtures(self):
        # 开关全关时与 v1 行为一致（含 v1 允许的候选回退链）。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="42"), RuntimeError("e")],
            RelayOptions(),
        )
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_candidate", result.trace[-1]["fallback_source"])

    def test_rg_03_result_is_json_serializable_with_all_flags(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nCANDIDATE_D: 43", finish()],
            ALL_ON,
        )
        blob = json.dumps(result.as_dict(), ensure_ascii=False)
        self.assertIsInstance(blob, str)
        self.assertNotIn("PROBLEM_SECRET", blob)

    def test_rg_04_time_boundary_check_still_applies(self):
        clock = FakeClock()
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])

        def advance_after_c(current):
            if len(current.calls) == 3:
                clock.value = 900.0

        client.on_chat = advance_after_c
        result = ForkSelectDeepenFinishRelay(
            client, clock=clock, options=ALL_ON
        ).solve("求一个非平凡整数 n。", "calculation")
        self.assertEqual(3, len(client.calls))
        self.assertEqual("UNKNOWN", result.final_response)

    def test_rg_05_agent_wiring_flags_reach_relay(self):
        config = AgentConfig(
            enable_fork_select_deepen_finish=True,
            enable_fsdf_diagnostics_v2=True,
            enable_fsdf_multiline_handoff_v2=True,
            enable_fsdf_final_confirmation_v2=True,
            enable_fsdf_finish_prompt_v2=True,
        )
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])
        result = ReasoningAgent(client, config).solve("求一个非平凡整数 n。", {"idx": 1})
        self.assertEqual(FINISH_PROMPT_V2, client.calls[4][0][0]["content"])
        self.assertTrue(finalize_event(result["trace"])["token_usage"] == "unavailable")
        self.assertEqual("7", result["final_response"])
        json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
