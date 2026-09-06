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
    DEEPEN_PROMPT,
    DEEPEN_PROMPT_MFD,
    DEEPEN_PROMPT_V2,
    FINISH_PROMPT,
    FINISH_PROMPT_V2,
    FINISH_PROMPT_COMPACT_V2,
    L0_TOKEN_SEQUENCE,
    STAGE_TOKEN_SEQUENCE,
    STAGE_TOKEN_SEQUENCE_DE_SWAP,
    STAGE_TOKEN_SEQUENCE_E_UP,
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
    def test_p0_01_submission_profile_is_authorized_canary_agentconfig_defaults_off(self):
        # FESF v1 specification rolls the official profile back to FSDF v1;
        # canaries stay opt-in while AgentConfig defaults remain off.
        self.assertFalse(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)
        for flag in (
            "enable_fsdf_diagnostics_v2",
            "enable_fsdf_multiline_handoff_v2",
            "enable_fsdf_final_confirmation_v2",
            "enable_fsdf_finish_prompt_v2",
            "enable_fsdf_handoff_first_d",
            "enable_fsdf_d_result_to_e",
        ):
            self.assertFalse(getattr(SUBMISSION_CONFIG, flag), flag)
        for flag in (
            "enable_fork_select_deepen_finish",
            "enable_fsdf_diagnostics_v2",
            "enable_fsdf_multiline_handoff_v2",
            "enable_fsdf_final_confirmation_v2",
            "enable_fsdf_finish_prompt_v2",
            "enable_fsdf_handoff_first_d",
            "enable_fsdf_d_result_to_e",
        ):
            self.assertFalse(getattr(AgentConfig(), flag), flag)
        self.assertFalse(SUBMISSION_CONFIG.enable_contextual_answer_reconstruction)

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


class F2HandoffFirstDTest(unittest.TestCase):
    """fsdf_handoff_first_d_v1：仅 D 阶段提示词变化；解析、调用数与预算不变。"""

    def handoff_first_deep(self, candidate="42"):
        # 新协议的 D 输出：管理字段在前、DERIVED 完整条目持续交付在后。
        return (
            "SELECTED_BRANCH: B\n"
            "SELECTION_REASON: 覆盖约束且闭环最短\n"
            f"CANDIDATE_D: {candidate}\n"
            "OPEN: 第1步求根，第2步检查 t>0 且 t≠1，第3步代回排除增根\n"
            "CHECKS: 尚未完成代回检查\n"
            "RISK: 代换要求 t>0；乘去分母时假设 t≠1\n"
            "DERIVED: 第1步: 已将原问题化为方程 f(t)=0\n"
            "第2步: 整理得 (t-5)(t+1)=0\n"
            "第3步: 候选根 t=5 与 t=-1\n"
            "FINAL_D: 5"
        )

    def test_hfd_01_flag_defaults_off_on_agentconfig(self):
        self.assertFalse(AgentConfig().enable_fsdf_handoff_first_d)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_handoff_first_d)
        self.assertFalse(RelayOptions().handoff_first_d)

    def test_hfd_02_off_uses_v1_deepen_prompt(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_prompt_v2=True,
            ),
        )
        self.assertEqual(DEEPEN_PROMPT, client.calls[3][0][0]["content"])

    def test_hfd_03_on_changes_only_deepen_prompt_and_keeps_budget(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.handoff_first_deep(), finish("5", "5")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_prompt_v2=True,
                handoff_first_d=True,
            ),
        )
        self.assertEqual(DEEPEN_PROMPT_V2, client.calls[3][0][0]["content"])
        self.assertEqual(ANALYZE_PROMPT, client.calls[0][0][0]["content"])
        self.assertEqual(FINISH_PROMPT_V2, client.calls[4][0][0]["content"])
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("5", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_hfd_04_existing_parsing_handles_new_protocol_output(self):
        # 程序侧设施不变：新协议输出走既有解析，E 收到完整条目与剩余步骤。
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.handoff_first_deep(), finish("5", "5")],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("第1步: 已将原问题化为方程 f(t)=0", e_prompt)
        self.assertIn("第3步: 候选根 t=5 与 t=-1", e_prompt)
        self.assertIn("OPEN: 第1步求根", e_prompt)
        self.assertIn("RISK: 代换要求 t>0", e_prompt)
        self.assertNotIn("HANDOFF_INCOMPLETE", e_prompt)
        self.assertEqual("5", result.final_response)

    def test_hfd_05_truncated_tail_keeps_earlier_items_visible(self):
        # DERIVED 之后的 FINAL_D 被截掉时，前面完整条目仍进入 E，且终答 fail-closed。
        truncated = self.handoff_first_deep().split("FINAL_D:")[0]
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), truncated, RuntimeError("e")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
            ),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("第2步: 整理得 (t-5)(t+1)=0", e_prompt)
        self.assertIn("OPEN: 第1步求根", e_prompt)
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["fallback_source"])
        # 五个值字段齐全：截断只影响答案确认（无 FINAL_D → UNKNOWN），不影响交接。
        event = finalize_event(result.trace)
        self.assertEqual([], event["handoff_missing_fields"])


class F2HandoffDiagnosticsTest(unittest.TestCase):
    """Issue #16 第一步：字段五状态诊断 + 三项汇总计数。"""

    def states_event(self, d_response):
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, diagnostics_v2=True),
        )
        return finalize_event(result.trace)

    def test_hdiag_01_five_field_states_are_separated(self):
        d_response = (
            "SELECTED_BRANCH: B\n"
            "CANDIDATE_D: UNKNOWN\n"
            "DERIVED: 第1步: 已将原问题化为方程 f(t)=0\n"
            # OPEN 整段缺席
            "CHECKS: 代入 t=5\nCHECKS: 代入 t=3\n"
            "RISK: 代回可得 t=\\frac{5\n"
        )
        event = self.states_event(d_response)
        self.assertEqual(
            {
                "CANDIDATE_D": "unknown",
                "DERIVED": "content",
                "OPEN": "absent",
                "CHECKS": "conflict",
                "RISK": "unclosed",
            },
            event["handoff_field_states"],
        )
        self.assertEqual(["OPEN"], event["handoff_missing_fields"])
        self.assertEqual(["CANDIDATE_D"], event["handoff_unknown_fields"])
        self.assertEqual(["CHECKS"], event["handoff_conflict_fields"])
        self.assertEqual(["RISK"], event["handoff_unclosed_fields"])
        self.assertFalse(event["handoff_all_fields_present"])
        self.assertTrue(event["handoff_has_derived_content"])
        self.assertFalse(event["handoff_has_candidate_result"])

    def test_hdiag_02_complete_handoff_counts(self):
        event = self.states_event(deep())
        self.assertTrue(event["handoff_all_fields_present"])
        self.assertTrue(event["handoff_has_derived_content"])
        self.assertTrue(event["handoff_has_candidate_result"])
        self.assertEqual([], event["handoff_missing_fields"])

    def test_hdiag_03_candidate_result_via_final_d(self):
        # CANDIDATE_D 与 DERIVED 均为诚实 UNKNOWN：字段齐全但无可用推导，
        # 三项计数必须分开——这正是"管理字段全在不代表有数学进展"。
        d_response = (
            "SELECTED_BRANCH: B\n"
            "CANDIDATE_D: UNKNOWN\n"
            "DERIVED: UNKNOWN\n"
            "OPEN: 求根并代回检验\n"
            "CHECKS: 未完成代回检验\n"
            "RISK: 代换要求 t>0\n"
            "FINAL_D: 42"
        )
        event = self.states_event(d_response)
        self.assertTrue(event["handoff_has_candidate_result"])
        self.assertTrue(event["handoff_all_fields_present"])
        self.assertFalse(event["handoff_has_derived_content"])
        self.assertEqual(["CANDIDATE_D", "DERIVED"], event["handoff_unknown_fields"])
        self.assertEqual([], event["handoff_missing_fields"])

    def test_hdiag_04_mid_formula_truncation_never_reaches_e(self):
        # 审核复现用例：条目在公式中间截断，半截内容不得作为完整证据进入 E。
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\n"
            "DERIVED: 第1步: 已化简为 x=5\n第2步: 整理得 (t-5)(t+1)=0\n"
            "第3步: 代回可得 t=\\frac{5"
        )
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, diagnostics_v2=True),
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertNotIn("\\frac{5", section)
        self.assertIn("第1步: 已化简为 x=5", section)
        self.assertIn("第2步: 整理得 (t-5)(t+1)=0", section)
        self.assertIn("HANDOFF_UNCLOSED: DERIVED", section)
        self.assertIn("HANDOFF_INCOMPLETE: true", section)
        event = finalize_event(result.trace)
        self.assertEqual(["DERIVED"], event["handoff_unclosed_fields"])

    def test_hdiag_05_single_line_unclosed_value_is_dropped(self):
        d_response = "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nDERIVED: \\frac{5\nOPEN: 无\nCHECKS: ok\nRISK: 无"
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, diagnostics_v2=True),
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertNotIn("\\frac{5", section)
        self.assertIn("HANDOFF_UNCLOSED: DERIVED", section)
        event = finalize_event(result.trace)
        self.assertEqual(["DERIVED"], event["handoff_unclosed_fields"])

    def test_hdiag_06_parity_holds_with_state_diagnostics(self):
        # 新诊断键不得改变行为：同一序列（含 UNKNOWN/冲突/未闭合字段）开关前后
        # 请求与终答完全一致。
        scripted = [
            analysis(),
            idea("B"),
            idea("C"),
            "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\nCHECKS: a\nCHECKS: b\n"
            "RISK: t=\\frac{5\nDERIVED: 第1步: x=5",
            finish(),
        ]
        client_off, result_off = solve_v2(list(scripted), RelayOptions())
        client_on, result_on = solve_v2(list(scripted), P0_ONLY)
        self.assertEqual(client_off.calls, client_on.calls)
        self.assertEqual(result_off.final_response, result_on.final_response)


class F2DResultToETest(unittest.TestCase):
    """Issue #16 第二步：fsdf_d_result_to_e_v1（待核查候选对 E 可见）。"""

    def synthetic_d(self):
        return (
            "SELECTED_BRANCH: B\n"
            "CANDIDATE_D: UNKNOWN\n"
            "DERIVED: 已化为一个待求解方程\n"
            "FINAL_D: 314159"
        )

    def test_dre_01_default_off_on_agentconfig_canary_on_submission(self):
        self.assertFalse(AgentConfig().enable_fsdf_d_result_to_e)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_d_result_to_e)
        self.assertFalse(RelayOptions().d_result_to_e)

    def test_dre_02_candidate_visible_to_e_and_fallback_intact(self):
        # 审核复现：E 输入此前看不到 FINAL_D；开启后作为待核查候选可见，
        # E 未产出终答时回退链不变。
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.synthetic_d(), RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, d_result_to_e=True),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("FINAL_D_FOR_CHECK: 314159", e_prompt)
        self.assertNotIn("CANDIDATE_D: UNKNOWN", e_prompt)
        self.assertEqual("314159", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])

    def test_dre_03_off_has_no_injection(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), self.synthetic_d(), finish()],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True),
        )
        self.assertNotIn("FINAL_D_FOR_CHECK", client.calls[4][0][1]["content"])

    def test_dre_04_conflicting_final_d_not_injected(self):
        d_response = self.synthetic_d() + "\nFINAL_D: 271828"
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, d_result_to_e=True),
        )
        self.assertNotIn("FINAL_D_FOR_CHECK", client.calls[4][0][1]["content"])
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("deep_final_conflict", result.trace[-1]["fallback_source"])

    def test_dre_05_unknown_and_protocol_failed_d_not_injected(self):
        d_unknown = "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nFINAL_D: UNKNOWN"
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_unknown, finish()],
            RelayOptions(multiline_handoff_v2=True, d_result_to_e=True),
        )
        self.assertNotIn("FINAL_D_FOR_CHECK", client.calls[4][0][1]["content"])
        d_failed = "SELECTED_BRANCH: 大概是B吧\nFINAL_D: 42"
        client2, result2 = solve_v2(
            [analysis(), idea("B"), idea("C"), d_failed, RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, d_result_to_e=True),
        )
        self.assertNotIn("FINAL_D_FOR_CHECK", client2.calls[4][0][1]["content"])
        self.assertEqual("UNKNOWN", result2.final_response)

    def test_dre_06_selection_rules_unchanged(self):
        # E 看到候选后明确弃答 → 最终仍是 UNKNOWN（可见性不改变选择链）。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.synthetic_d(), "FINAL: UNKNOWN"],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, d_result_to_e=True),
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("finish_unknown", result.trace[-1]["fallback_source"])

    def test_dre_07_budget_and_diag_flag(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.synthetic_d(), finish("7", "7")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                d_result_to_e=True,
            ),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        event = finalize_event(result.trace)
        self.assertTrue(event["d_candidate_visible_to_e"])
        self.assertFalse(event["e_final_equals_d_candidate"])
        json.dumps(result.as_dict(), ensure_ascii=False)

    def test_dre_08_anchoring_copy_is_observed_not_promoted(self):
        # E 照抄注入候选时终答仍走正常选择链；布尔诊断只记录行为不改变行为。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.synthetic_d(), "FINAL: 314159"],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                d_result_to_e=True,
            ),
        )
        self.assertEqual("314159", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])
        event = finalize_event(result.trace)
        self.assertTrue(event["d_candidate_visible_to_e"])
        self.assertTrue(event["e_final_equals_d_candidate"])


class F2DeBudgetSwapTest(unittest.TestCase):
    """fsdf_de_budget_swap_v1：D/E 预算对调（4096/8192），总数与调用数不变。"""

    def test_dbs_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_de_budget_swap)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_de_budget_swap)
        self.assertFalse(RelayOptions().de_budget_swap)

    def test_dbs_02_off_keeps_v1_sequence(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("7", result.final_response)

    def test_dbs_03_swap_only_changes_stage_max_tokens(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish("7", "7")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                de_budget_swap=True,
            ),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual(18432, sum(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        # 提示词与温度不受影响。
        self.assertEqual(DEEPEN_PROMPT, client.calls[3][0][0]["content"])
        self.assertEqual(0.0, client.calls[4][1])
        self.assertEqual("7", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_dbs_04_swap_with_handoff_first_combo(self):
        # 与交接产物优先组合（迭代窗实际配置）：预算交换仍精确生效。
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_prompt_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
            ),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual("7", result.final_response)

    def test_dbs_05_protocol_failure_reports_swapped_tokens(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), "SELECTED_BRANCH: 大概是B吧", RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, de_budget_swap=True),
        )
        deepen = [e for e in result.trace if e["stage"] == "deepen"][-1]
        self.assertEqual("protocol_failed", deepen["status"])
        self.assertEqual(4096, deepen["max_tokens"])
        self.assertEqual("UNKNOWN", result.final_response)


class F2FinishCompactFinalTest(unittest.TestCase):
    """fsdf_finish_compact_final_v1（迭代 2）：仅 E 提示词换成紧凑+提前 FINAL 变体。"""

    def test_fcf_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_finish_compact_final)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_finish_compact_final)
        self.assertFalse(RelayOptions().finish_compact_final)

    def test_fcf_02_off_uses_frontier_prompt(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_prompt_v2=True,
                de_budget_swap=True,
            ),
        )
        self.assertEqual(FINISH_PROMPT_V2, client.calls[4][0][0]["content"])

    def test_fcf_03_on_uses_compact_prompt_only(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish("7", "7")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_prompt_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                finish_compact_final=True,
            ),
        )
        self.assertEqual(FINISH_PROMPT_COMPACT_V2, client.calls[4][0][0]["content"])
        self.assertEqual(DEEPEN_PROMPT_V2, client.calls[3][0][0]["content"])
        # 预算交换（迭代 1 前沿）保持不变：D 4096 / E 8192，总数与调用数不变。
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("7", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_fcf_04_early_final_still_fail_closed_on_conflict(self):
        # 紧凑提示鼓励尽早 FINAL；若模型输出两个冲突 FINAL，P2a 规则照常 fail-closed。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), "FINAL: 7\nFINAL: 8"],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                finish_compact_final=True,
            ),
        )
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("final_conflict", result.trace[-1]["fallback_source"])


class F2MandatoryFinalDTest(unittest.TestCase):
    """fsdf_mandatory_final_d_v1（迭代 3）：D 强制前置 FINAL_D，激活 deep_final 回退。"""

    def mfd_deep(self, final="42"):
        return (
            "SELECTED_BRANCH: B\n"
            "SELECTION_REASON: 覆盖约束且闭环最短\n"
            "CANDIDATE_D: UNKNOWN\n"
            f"FINAL_D: {final}\n"
            "OPEN: 求根并检查 t>0\n"
            "DERIVED: 第1步: 已化简为 (t-5)(t+1)=0\n"
            "第2步: 候选根 t=5 与 t=-1"
        )

    def test_mfd_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_mandatory_final_d)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_mandatory_final_d)
        self.assertFalse(RelayOptions().mandatory_final_d)

    def test_mfd_02_off_uses_frontier_prompt(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True, de_budget_swap=True),
        )
        self.assertEqual(DEEPEN_PROMPT_V2, client.calls[3][0][0]["content"])

    def test_mfd_03_on_uses_mfd_prompt_only(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.mfd_deep(), finish("42", "42")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                mandatory_final_d=True,
            ),
        )
        self.assertEqual(DEEPEN_PROMPT_MFD, client.calls[3][0][0]["content"])
        self.assertIn("立即输出你认为最可能正确的唯一最终答案", client.calls[3][0][0]["content"])
        self.assertNotIn("可以输出 FINAL_D", client.calls[3][0][0]["content"])
        # 预算与调用不变（迭代 1 前沿的交换保持）。
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("42", result.final_response)

    def test_mfd_04_early_final_d_survives_and_falls_back(self):
        # E 失败时，前置 FINAL_D 经 deep_final 被采纳（激活休眠回退）。
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.mfd_deep(), RuntimeError("e")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                mandatory_final_d=True,
            ),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("第1步: 已化简为 (t-5)(t+1)=0", e_prompt)
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])

    def test_mfd_05_d_abstention_stays_unknown(self):
        # 强制 FINAL_D 但 D 明确弃答 → 不激活回退，最终 UNKNOWN。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.mfd_deep(final="UNKNOWN"), RuntimeError("e")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                mandatory_final_d=True,
            ),
        )
        self.assertEqual("UNKNOWN", result.final_response)

    def test_mfd_06_e_confirmed_final_still_wins(self):
        # 结构单调性：E 自行形成终答时，前置 FINAL_D 不改变结果来源。
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), self.mfd_deep(final="99"), finish("7", "7")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                mandatory_final_d=True,
            ),
        )
        self.assertEqual("7", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])


class F2FinishHandoffShareTest(unittest.TestCase):
    """fsdf_finish_handoff_share_v1（迭代 4）：E 输入构成重分配——删除"选中思路"块，
    handoff 装配上限 3000→4600（P1 多行装配下），总上下文 6500 不变。"""

    @staticmethod
    def big_derived(lines=40):
        return "DERIVED: " + "\n".join(
            f"第{i}步: 完整中间推导条目记录 x_{i} = {i} * 13 + 7 与边界条件核对说明" for i in range(1, lines + 1)
        )

    def test_fhs_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_finish_handoff_share)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_finish_handoff_share)
        self.assertFalse(RelayOptions().finish_handoff_share)

    def test_fhs_02_off_keeps_selected_idea_block(self):
        client, _ = solve_v2(
            [analysis(), idea("B", secret="IDEA_SECRET"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True, de_budget_swap=True),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("选中思路：", e_prompt)
        self.assertIn("IDEA_SECRET", e_prompt)

    def test_fhs_03_on_drops_idea_block_and_enlarges_handoff(self):
        d_response = f"SELECTED_BRANCH: B\nCANDIDATE_D: 42\n{self.big_derived(90)}\nOPEN: 无\nCHECKS: ok\nRISK: 无"
        client_off, _ = solve_v2(
            [analysis(), idea("B", secret="IDEA_SECRET"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True, de_budget_swap=True),
        )
        client_on, result = solve_v2(
            [analysis(), idea("B", secret="IDEA_SECRET"), idea("C"), d_response, finish()],
            RelayOptions(
                multiline_handoff_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                finish_handoff_share=True,
            ),
        )
        section_off = handoff_section(client_off.calls[4][0][1]["content"])
        section_on = handoff_section(client_on.calls[4][0][1]["content"])
        # 选中思路块消失；交接条目变多（更大的装配上限）。
        self.assertNotIn("选中思路：", client_on.calls[4][0][1]["content"])
        self.assertNotIn("IDEA_SECRET", client_on.calls[4][0][1]["content"])
        self.assertGreater(len(section_on), len(section_off))
        # 90 行条目（约 3800 字符）在 4600 上限下完整保留，3000 上限下被部分裁剪。
        self.assertIn("第90步", section_on)
        self.assertNotIn("HANDOFF_DROPPED", section_on)
        self.assertIn("HANDOFF_PARTIAL", section_off)
        self.assertNotIn("HANDOFF_PARTIAL", section_on)
        # 总上下文上限保持。
        e_prompt = client_on.calls[4][0][1]["content"]
        context = e_prompt.split("求一个非平凡整数 n。\n\n", 1)[1]
        self.assertLessEqual(len(context), 6500)
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client_on.calls))
        self.assertEqual("7", result.final_response)

    def test_fhs_04_no_branch_fallback_line_kept(self):
        client, _ = solve_v2(
            [analysis(), RuntimeError("b"), RuntimeError("c"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, finish_handoff_share=True),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("没有可用分支", e_prompt)
        self.assertNotIn("选中思路：", e_prompt)


class F2HandoffOpenFirstETest(unittest.TestCase):
    """fsdf_handoff_open_first_e_v1（迭代 5）：仅 E 侧渲染顺序——OPEN 提到 DERIVED 前。"""

    def test_ofe_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_handoff_open_first_e)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_handoff_open_first_e)
        self.assertFalse(RelayOptions().handoff_open_first_e)

    def test_ofe_02_off_keeps_derived_before_open(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True, de_budget_swap=True,
                         finish_handoff_share=True),
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertLess(section.index("DERIVED:"), section.index("OPEN:"))

    def test_ofe_03_on_renders_open_before_derived(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish("7", "7")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                finish_handoff_share=True,
                handoff_open_first_e=True,
            ),
        )
        section = handoff_section(client.calls[4][0][1]["content"])
        self.assertLess(section.index("OPEN:"), section.index("DERIVED:"))
        self.assertLess(section.index("CANDIDATE_D:"), section.index("OPEN:"))
        # 装配保留优先级不变：内容完整、预算不变。
        self.assertNotIn("HANDOFF_DROPPED", section)
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("7", result.final_response)

    def test_ofe_04_assembly_priority_unchanged_under_budget(self):
        # 渲染顺序改变不得影响装配裁剪（同样的条目被保留）。
        derived_lines = [
            f"第{i}步: 完整中间推导条目记录 x_{i} = {i} * 13 + 7 与边界条件核对说明"
            for i in range(1, 141)
        ]
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: 42\n"
            "DERIVED: " + "\n".join(derived_lines) + "\n"
            "OPEN: 剩余步骤\nCHECKS: 检查结果\nRISK: 风险"
        )
        sections = {}
        for flag in (False, True):
            client, _ = solve_v2(
                [analysis(), idea("B"), idea("C"), d_response, finish()],
                RelayOptions(
                    multiline_handoff_v2=True,
                    handoff_first_d=True,
                    de_budget_swap=True,
                    finish_handoff_share=True,
                    handoff_open_first_e=flag,
                ),
            )
            sections[flag] = handoff_section(client.calls[4][0][1]["content"])
        for flag, section in sections.items():
            self.assertIn("HANDOFF_PARTIAL: DERIVED", section)
            self.assertIn("第1步", section)
            self.assertNotIn("第140步", section)
            self.assertNotIn("…[省略]…", section)
        # 仅顺序不同：两臂保留的 DERIVED 行集合一致。
        def derived_lines_in(section):
            return [line for line in section.splitlines() if line.startswith(("DERIVED: ", "第"))]
        self.assertEqual(derived_lines_in(sections[False]), derived_lines_in(sections[True]))


class F2FinishHandoffShareV2Test(unittest.TestCase):
    """fsdf_finish_handoff_share_v2（迭代 7）：share 模式下 A 摘要也移出，
    E 上下文 = 分支 + 纯进度交接，装配上限 4600→6050（总 6500 不变）。"""

    def test_fsv2_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_finish_handoff_share_v2)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_finish_handoff_share_v2)
        self.assertFalse(RelayOptions().finish_handoff_share_v2)

    def test_fsv2_02_v1_share_keeps_a_block(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, finish_handoff_share=True),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("A 约束摘要：", e_prompt)
        self.assertNotIn("选中思路：", e_prompt)

    def test_fsv2_03_drops_a_block_and_enlarges_handoff(self):
        d_response = f"SELECTED_BRANCH: B\nCANDIDATE_D: 42\n{F2FinishHandoffShareTest.big_derived(120)}\nOPEN: 无\nCHECKS: ok\nRISK: 无"
        client_v1, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(multiline_handoff_v2=True, finish_handoff_share=True),
        )
        client_v2, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_response, finish()],
            RelayOptions(
                multiline_handoff_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                finish_handoff_share_v2=True,
            ),
        )
        e_v2 = client_v2.calls[4][0][1]["content"]
        section_v1 = handoff_section(client_v1.calls[4][0][1]["content"])
        section_v2 = handoff_section(e_v2)
        # A 摘要块消失；上下文 = 分支 + 纯交接。
        self.assertNotIn("A 约束摘要", e_v2)
        self.assertNotIn("选中思路", e_v2)
        self.assertIn("SELECTED_BRANCH: B", section_v2)
        # 6050 上限下更多条目存活（120 行约 5100 字符）。
        self.assertIn("第120步", section_v2)
        self.assertNotIn("第120步", section_v1)
        # 总上下文上限保持；预算与调用不变。
        context = e_v2.split("求一个非平凡整数 n。\n\n", 1)[1]
        self.assertLessEqual(len(context), 6500)
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client_v2.calls))
        self.assertEqual(5, len(client_v2.calls))
        self.assertEqual("7", result.final_response)


class F2EBudgetUpTest(unittest.TestCase):
    """fsdf_e_budget_up_v1（迭代 8）：仅 E 生成预算 8192→9728（总 +8%）。"""

    def test_ebu_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_e_budget_up)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_e_budget_up)
        self.assertFalse(RelayOptions().e_budget_up)

    def test_ebu_02_off_keeps_swap_sequence(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, de_budget_swap=True),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))

    def test_ebu_03_on_raises_only_e_budget(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish("7", "7")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                finish_handoff_share=True,
                e_budget_up=True,
            ),
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE_E_UP, tuple(call[2] for call in client.calls))
        self.assertEqual([4096], [call[2] for call in client.calls if call[2] not in (2048, 9728)])
        self.assertEqual(2048 * 3 + 4096 + 9728, sum(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        # 提示词不受影响。
        self.assertEqual(DEEPEN_PROMPT_V2, client.calls[3][0][0]["content"])
        self.assertEqual("7", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_ebu_04_without_swap_e_goes_4096_to_9728(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(e_budget_up=True),
        )
        self.assertEqual((2048, 2048, 2048, 8192, 9728), tuple(call[2] for call in client.calls))


class F2DeepCandidateFallbackTest(unittest.TestCase):
    """fsdf_deep_candidate_fallback_v1（迭代 9）：仅 E 失败时采纳 content 态 CANDIDATE_D。"""

    def test_dcf_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_deep_candidate_fallback)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_deep_candidate_fallback)
        self.assertFalse(RelayOptions().deep_candidate_fallback)

    def test_dcf_02_off_pool_stays_unknown(self):
        # 前沿行为：E 失败 + 无 FINAL_D + CANDIDATE_D content → UNKNOWN。
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5"), RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True),
        )
        self.assertEqual("UNKNOWN", result.final_response)

    def test_dcf_03_on_adopts_content_candidate_on_e_failure(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5"), RuntimeError("e")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                deep_candidate_fallback=True,
            ),
        )
        self.assertEqual("5", result.final_response)
        self.assertEqual("deep_candidate", result.trace[-1]["fallback_source"])

    def test_dcf_04_e_final_still_wins(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5"), finish("9", "9")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                deep_candidate_fallback=True,
            ),
        )
        self.assertEqual("9", result.final_response)
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_dcf_05_abstention_conflict_and_unknown_states_unchanged(self):
        # E 显式弃答 → UNKNOWN（即使候选可用）。
        _, r1 = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5"), "FINAL: UNKNOWN"],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, deep_candidate_fallback=True),
        )
        self.assertEqual("UNKNOWN", r1.final_response)
        # CANDIDATE_D 冲突 → 不可采纳。
        d_conflict = deep(candidate="5") + "CANDIDATE_D: 6"
        _, r2 = solve_v2(
            [analysis(), idea("B"), idea("C"), d_conflict, RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, deep_candidate_fallback=True),
        )
        self.assertEqual("UNKNOWN", r2.final_response)
        # CANDIDATE_D: UNKNOWN（unknown 态）→ 不可采纳。
        _, r3 = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="UNKNOWN"), RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, deep_candidate_fallback=True),
        )
        self.assertEqual("UNKNOWN", r3.final_response)

    def test_dcf_06_protocol_failed_d_excluded(self):
        d_failed = "SELECTED_BRANCH: 大概是B吧\nCANDIDATE_D: 42"
        _, result = solve_v2(
            [analysis(), idea("B"), idea("C"), d_failed, RuntimeError("e")],
            RelayOptions(multiline_handoff_v2=True, final_confirmation_v2=True, deep_candidate_fallback=True),
        )
        self.assertEqual("UNKNOWN", result.final_response)

    def test_dcf_07_deep_final_still_preferred(self):
        client, result = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(candidate="5") + "FINAL_D: 42", RuntimeError("e")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                deep_candidate_fallback=True,
            ),
        )
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])


class F2SkillRoutesTest(unittest.TestCase):
    """fsdf_skill_routes_v1（迭代 11）：宿主预筛路线层——目录+正文注入 D 的 user 提示。"""

    def test_sr_01_defaults_off_and_resource_loads(self):
        self.assertFalse(AgentConfig().enable_fsdf_skill_routes)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_skill_routes)
        self.assertFalse(RelayOptions().skill_routes)
        from reasoning_agent.fork_select_deepen_finish import SKILL_ROUTES

        self.assertGreaterEqual(len(SKILL_ROUTES), 3)

    def test_sr_02_off_keeps_frontier_d_prompt(self):
        client, _ = solve_v2(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True),
        )
        self.assertNotIn("可用解题路线", client.calls[3][0][1]["content"])

    def test_sr_03_on_injects_directory_and_body(self):
        client, result = solve_v2(
            ["求方程 2x+3=7 的解。", idea("B"), idea("C"), deep(), finish("2", "2")],
            RelayOptions(
                multiline_handoff_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                skill_routes=True,
            ),
        )
        d_user = client.calls[3][0][1]["content"]
        self.assertIn("可用解题路线（宿主按题型预筛，仅限目录内 ID）：", d_user)
        self.assertIn("宿主预选路线：", d_user)
        self.assertIn("预期产物：", d_user)
        # 预算与调用不变。
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual("2", result.final_response)

    def test_sr_04_d_override_validated_against_directory(self):
        d_override = deep() + "\nSELECTED_SKILL: symmetry_invariant"
        d_bad = deep() + "\nSELECTED_SKILL: not_a_route"
        for d_response, expected in ((d_override, "symmetry_invariant"), (d_bad, "")):
            with self.subTest(expected=expected):
                _, result = solve_v2(
                    ["证明：对任意实数 a>0，a+a^2 >= 2a^3 不一定成立，讨论之。", idea("B"), idea("C"),
                     d_response, finish()],
                    RelayOptions(
                        diagnostics_v2=True,
                        multiline_handoff_v2=True,
                        handoff_first_d=True,
                        skill_routes=True,
                    ),
                )
                event = finalize_event(result.trace)
                self.assertEqual(expected, event.get("selected_skill", ""))

    def test_sr_05_no_route_text_falls_back(self):
        # 无匹配关键词/题型时回退前沿行为（仍注入宿主预选，但目录存在）。
        client, result = solve_v2(
            ["求一个非平凡整数 n。", idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, skill_routes=True),
        )
        self.assertIn("可用解题路线", client.calls[3][0][1]["content"])
        self.assertEqual("7", result.final_response)


class F2SkillHarnessTest(unittest.TestCase):
    """fsdf_skill_harness_v1（迭代 12）：D 系统提示=路线执行脚本，强制逐步输出。"""

    def test_tkh_01_defaults_off(self):
        self.assertFalse(AgentConfig().enable_fsdf_skill_harness)
        self.assertFalse(SUBMISSION_CONFIG.enable_fsdf_skill_harness)
        self.assertFalse(RelayOptions().skill_harness)

    def test_tkh_02_off_keeps_frontier_prompt(self):
        client, _ = solve_v2(
            ["求方程 2x+3=7 的解。", idea("B"), idea("C"), deep(), finish()],
            RelayOptions(multiline_handoff_v2=True, handoff_first_d=True),
        )
        self.assertEqual(DEEPEN_PROMPT_V2, client.calls[3][0][0]["content"])

    def test_tkh_03_on_replaces_system_prompt_with_route_script(self):
        client, result = solve_v2(
            ["求方程 2x+3=7 的解。", idea("B"), idea("C"), deep(), finish("2", "2")],
            RelayOptions(
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                skill_harness=True,
            ),
        )
        d_sys = client.calls[3][0][0]["content"]
        self.assertIn("是路线执行器，不是自由解题者", d_sys)
        self.assertIn("不得跳步", d_sys)
        self.assertIn("消元与代换", d_sys)  # 计算题预选路线
        self.assertNotIn("可以输出 FINAL_D", d_sys)
        # 预算与调用不变。
        self.assertEqual(STAGE_TOKEN_SEQUENCE_DE_SWAP, tuple(call[2] for call in client.calls))
        self.assertEqual(5, len(client.calls))
        self.assertEqual("2", result.final_response)

    def test_tkh_04_step_outputs_parse_and_telemetry_counts(self):
        d_harness = (
            "SELECTED_BRANCH: B\n"
            "CANDIDATE_D: 2\n"
            "OPEN: 无\n"
            "CHECKS: 代回 2x+3=7 成立\n"
            "RISK: 无\n"
            "DERIVED: 第1步: 未知量 x，关系 2x+3=7\n"
            "第2步: 消元得 x=2\n"
            "第3步: 代回检验通过\n"
            "第4步: 无需构造\n"
            "FINAL_D: 2"
        )
        client, result = solve_v2(
            ["求方程 2x+3=7 的解。", idea("B"), idea("C"), d_harness, RuntimeError("e")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                skill_harness=True,
            ),
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("第1步: 未知量 x，关系 2x+3=7", e_prompt)
        self.assertIn("路线核查要求", e_prompt)
        self.assertEqual("2", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])
        event = finalize_event(result.trace)
        self.assertEqual(4, event.get("harness_steps_completed"))
        self.assertEqual(4, event.get("harness_steps_expected"))
        self.assertEqual("elimination_substitution", event.get("harness_route_id"))

    def test_tkh_05_missing_steps_telemetry(self):
        d_partial = (
            "SELECTED_BRANCH: B\n"
            "CANDIDATE_D: UNKNOWN\n"
            "OPEN: 后续步骤未完成\n"
            "CHECKS: 未验证\n"
            "RISK: 无\n"
            "DERIVED: 第1步: 已列出关系 2x+3=7"
        )
        _, result = solve_v2(
            ["求方程 2x+3=7 的解。", idea("B"), idea("C"), d_partial, RuntimeError("e")],
            RelayOptions(
                diagnostics_v2=True,
                multiline_handoff_v2=True,
                final_confirmation_v2=True,
                handoff_first_d=True,
                de_budget_swap=True,
                skill_harness=True,
            ),
        )
        event = finalize_event(result.trace)
        self.assertEqual(1, event.get("harness_steps_completed"))
        self.assertEqual(4, event.get("harness_steps_expected"))
        self.assertEqual("UNKNOWN", result.final_response)


if __name__ == "__main__":
    unittest.main()
