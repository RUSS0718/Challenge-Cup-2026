import dataclasses
import hashlib
import json
from pathlib import Path
import threading
import unittest

from reasoning_agent.fork_select_deepen_finish import (
    HARD_DEADLINE_SECONDS,
    L0_TOKEN_SEQUENCE,
    STAGE_TOKEN_SEQUENCE,
    ForkSelectDeepenFinishRelay,
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


def solve_full(responses, *, clock=None, config=None, problem="求一个非平凡整数 n。"):
    client = ScriptedClient(responses)
    relay = ForkSelectDeepenFinishRelay(client, clock=clock or FakeClock())
    result = relay.solve(problem, "calculation")
    return client, result


class ForkSelectDeepenFinishAcceptanceTest(unittest.TestCase):
    def test_t01_acceptance_config_off_authorized_submission_profile_on(self):
        before = dataclasses.asdict(SUBMISSION_CONFIG)
        # Acceptance base config is off; the current submission profile is on
        # only because default promotion was explicitly authorized separately.
        self.assertFalse(AgentConfig().enable_fork_select_deepen_finish)
        self.assertTrue(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)
        self.assertFalse(SUBMISSION_CONFIG.enable_contextual_answer_reconstruction)
        result = ReasoningAgent(ScriptedClient([]), AgentConfig()).config
        self.assertFalse(result.enable_fork_select_deepen_finish)
        self.assertEqual(before, dataclasses.asdict(SUBMISSION_CONFIG))

    def test_t02_paths_are_mutually_exclusive(self):
        # T02 覆盖 contextual/KCV/PS-C/V5 四条现存互斥路径。Spec 写明的 BTCS 组合
        # 在当前基线不可构造（缺 reasoning_agent.btcs 与 AgentConfig.protocol_mode），
        # 记 N/A，不计入通过/失败数。
        for flag in (
            "enable_contextual_answer_reconstruction",
            "enable_typed_answer_capsule",
            "enable_condition_checked_selection",
            "enable_plan_solve_compact",
        ):
            cfg = AgentConfig(enable_fork_select_deepen_finish=True, **{flag: True})
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                ReasoningAgent(ScriptedClient([]), cfg).solve("求 n", {})

    def test_t03_l0_uses_exactly_one_4096_call(self):
        client = ScriptedClient(["FINAL: 2"])
        result = ForkSelectDeepenFinishRelay(client).solve("1+1", "calculation")
        self.assertEqual([4096], [call[2] for call in client.calls])
        self.assertEqual(L0_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("2", result.final_response)

    def test_t04_long_scalar_uses_main_path(self):
        client, result = solve_full(
            [analysis(), idea("B"), idea("C"), deep(), finish()],
            problem="设 n 为满足约束的整数，经过长推导后求 n 的值。",
        )
        self.assertEqual(STAGE_TOKEN_SEQUENCE, tuple(call[2] for call in client.calls))
        self.assertEqual("7", result.final_response)

    def test_t05_complete_path_has_five_calls_and_18432_tokens(self):
        client, _ = solve_full([analysis(), idea("B"), idea("C"), deep(), finish()])
        observed = [call[2] for call in client.calls]
        self.assertEqual([2048, 2048, 2048, 8192, 4096], observed)
        self.assertEqual(18432, sum(observed))

    def test_t06_b_and_c_receive_same_a_without_each_other(self):
        b_text = idea("B", secret="B_ONLY_SECRET")
        c_text = idea("C", secret="C_ONLY_SECRET")
        client, _ = solve_full([analysis(), b_text, c_text, deep(), finish()])
        b_prompt = client.calls[1][0][1]["content"]
        c_prompt = client.calls[2][0][1]["content"]
        self.assertIn("GOAL: 求唯一答案", b_prompt)
        self.assertIn("GOAL: 求唯一答案", c_prompt)
        self.assertNotIn("C_ONLY_SECRET", b_prompt)
        self.assertNotIn("B_ONLY_SECRET", c_prompt)

    def test_t07_b_and_c_prompts_are_different(self):
        client, _ = solve_full([analysis(), idea("B"), idea("C"), deep(), finish()])
        hashes = [
            hashlib.sha256(json.dumps(client.calls[index][0], sort_keys=True).encode()).hexdigest()
            for index in (1, 2)
        ]
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertIn("标准构造", client.calls[1][0][0]["content"])
        self.assertIn("替代方法", client.calls[2][0][0]["content"])

    def test_t08_b_and_c_are_never_final_candidates(self):
        responses = [analysis(), "FINAL: 100", "FINAL: 101", deep(candidate="7"), finish()]
        _, result = solve_full(responses)
        self.assertEqual("7", result.final_response)
        self.assertNotEqual("100", result.final_response)
        self.assertNotEqual("101", result.final_response)

    def test_t09_idea_packets_are_cropped_to_1600(self):
        long_b = "B" * 5000
        long_c = "C" * 5000
        client, _ = solve_full([analysis(), long_b, long_c, deep(), finish()])
        d_prompt = client.calls[3][0][1]["content"]
        b_section = d_prompt.split("B 思路包：\n", 1)[1].split("\n\nC 思路包：", 1)[0]
        c_section = d_prompt.split("C 思路包：\n", 1)[1].split("\n", 1)[0]
        self.assertLessEqual(len(b_section), 1600)
        self.assertLessEqual(len(c_section), 1600)

    def test_t10_d_selects_only_one_branch(self):
        client, result = solve_full(
            [analysis(), idea("B", secret="B_REJECTED_SECRET"), idea("C", secret="C_SELECTED_SECRET"), deep("C"), finish()]
        )
        self.assertEqual("C", result.trace[-1]["selected_branch"])
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("C_SELECTED_SECRET", e_prompt)
        self.assertNotIn("B_REJECTED_SECRET", e_prompt)

    def test_t11_d_is_one_8192_call(self):
        client, _ = solve_full([analysis(), idea("B"), idea("C"), deep(), finish()])
        self.assertEqual(1, sum(call[2] == 8192 for call in client.calls))
        self.assertEqual(8192, client.calls[3][2])

    def test_t12_finish_excludes_rejected_branch_full_text(self):
        rejected_c = idea("C", secret="C_REJECTED_FULL_TEXT").replace("METHOD:", "METHOD :")
        incomplete_d = "SELECTED_BRANCH: B\nCANDIDATE_D: 7\nDERIVED: x=7\n" + rejected_c
        client, _ = solve_full(
            [analysis(), idea("B", secret="B_SELECTED"), rejected_c, incomplete_d, finish()]
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("B_SELECTED", e_prompt)
        self.assertNotIn("C_REJECTED_FULL_TEXT", e_prompt)

    def test_t13_finish_uses_4096_and_requires_candidate_then_final(self):
        client, result = solve_full([analysis(), idea("B"), idea("C"), deep(), finish("8", "8")])
        self.assertEqual(4096, client.calls[4][2])
        self.assertIn("CANDIDATE_E", client.calls[4][0][0]["content"])
        self.assertIn("FINAL", client.calls[4][0][0]["content"])
        self.assertEqual("finish_final", result.trace[-1]["fallback_source"])

    def test_t14_missing_packet_fields_does_not_stop_path(self):
        client, result = solve_full(["GOAL: only one field", "B idea", "C idea", deep(), finish()])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("7", result.final_response)
        self.assertIn("GOAL: only one field", client.calls[1][0][1]["content"])

    def test_t15_a_failure_degrades_to_b_c_d_e(self):
        client, result = solve_full([RuntimeError("hidden details"), idea("B"), idea("C"), deep(), finish()])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("7", result.final_response)
        self.assertIn("A 状态不可用", client.calls[1][0][1]["content"])
        self.assertNotIn("hidden details", json.dumps(result.trace, ensure_ascii=False))

    def test_t16_b_failure_selects_c_without_retry(self):
        client, result = solve_full([analysis(), RuntimeError("b"), idea("C"), deep("C"), finish()])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("C", result.trace[-1]["selected_branch"])
        self.assertEqual(2048, client.calls[2][2])

    def test_t17_c_failure_selects_b_without_retry(self):
        client, result = solve_full([analysis(), idea("B"), RuntimeError("c"), deep("B"), finish()])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("B", result.trace[-1]["selected_branch"])
        self.assertEqual(8192, client.calls[3][2])

    def test_t18_both_ideas_fail_uses_fixed_direct_fallback(self):
        client, result = solve_full([analysis(), RuntimeError("b"), RuntimeError("c"), deep(), finish()])
        self.assertEqual(5, len(client.calls))
        self.assertIn("固定 direct fallback", client.calls[3][0][1]["content"])
        self.assertEqual("7", result.final_response)

    def test_t19_d_failure_with_both_ideas_uses_deterministic_b(self):
        # Spec §10（复审修订）：D 失败且 B/C 均可用时，确定性选择 B（标准正向路径）；
        # 仅一支可用时 E 使用唯一可用思路。
        client, result = solve_full(
            [analysis(), idea("B", secret="B_ONLY"), idea("C", secret="C_REJECTED"), RuntimeError("d"), finish()]
        )
        self.assertEqual(5, len(client.calls))
        self.assertEqual("7", result.final_response)
        self.assertEqual("B", result.trace[-1]["selected_branch"])
        self.assertIn("B_ONLY", client.calls[4][0][1]["content"])
        self.assertNotIn("C_REJECTED", client.calls[4][0][1]["content"])
        client2, result2 = solve_full(
            [analysis(), RuntimeError("b"), idea("C", secret="C_ONLY"), RuntimeError("d"), finish()]
        )
        self.assertEqual(5, len(client2.calls))
        self.assertEqual("7", result2.final_response)
        self.assertEqual("C", result2.trace[-1]["selected_branch"])
        self.assertIn("C_ONLY", client2.calls[4][0][1]["content"])

    def test_t20_e_failure_degrades_strictly_to_d(self):
        client, result = solve_full([analysis(), idea("B"), idea("C"), deep(candidate="42"), RuntimeError("e")])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_candidate", result.trace[-1]["fallback_source"])

    def test_t21_answer_priority_fixtures(self):
        fixtures = (
            (finish("1", "2"), deep(), "2", "finish_final"),
            ("CANDIDATE_E: 3\nFINAL: <result>", deep(), "3", "finish_candidate"),
            ("no answer", "SELECTED_BRANCH: B\nFINAL_D: 4\nCANDIDATE_D: UNKNOWN", "4", "deep_final"),
            ("no answer", "SELECTED_BRANCH: B\nCANDIDATE_D: 5", "5", "deep_candidate"),
            ("no answer", "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\n\\boxed{6}", "6", "boxed"),
            ("no answer", "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\nno final\n42", "42", "math_line"),
        )
        for e_response, d_response, expected, source in fixtures:
            with self.subTest(expected=expected):
                _, result = solve_full([analysis(), idea("B"), idea("C"), d_response, e_response])
                self.assertEqual(expected, result.final_response)
                self.assertEqual(source, result.trace[-1]["fallback_source"])

    def test_t22_pseudo_final_in_b_or_c_cannot_win(self):
        _, result = solve_full([analysis(), "FINAL: 100", "FINAL: 101", deep(candidate="7"), finish()])
        self.assertEqual("7", result.final_response)

    def test_t23_placeholders_are_rejected(self):
        for placeholder in ("<answer>", "<result>", "UNKNOWN", "[答案]"):
            with self.subTest(placeholder=placeholder):
                _, result = solve_full(
                    [analysis(), idea("B"), idea("C"), deep(candidate="8"), f"FINAL: {placeholder}"]
                )
                self.assertEqual("8", result.final_response)

    def test_t24_body_numbers_are_not_salvaged(self):
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: UNKNOWN\nDERIVED: x=2\n"
            "OPEN: step=3\nCHECKS: boundary=4\nRISK: unresolved\n"
            "第1步得到 5\n第2步得到 6"
        )
        _, result = solve_full([analysis(), idea("B"), idea("C"), d_response, "仍未完成"])
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["fallback_source"])

    def test_t25_soft_deadline_stops_before_next_stage(self):
        clock = FakeClock()
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])

        def advance_after_c(current):
            if len(current.calls) == 3:
                clock.value = 900.0

        client.on_chat = advance_after_c
        result = ForkSelectDeepenFinishRelay(client, clock=clock).solve("求一个非平凡整数 n。", "calculation")
        self.assertEqual(3, len(client.calls))
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual(
            "soft_deadline",
            next(entry["error_category"] for entry in result.trace if entry["stage"] == "deepen"),
        )

    def test_t26_hard_deadline_stops_all_new_calls(self):
        clock = FakeClock()
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])

        def advance_after_d(current):
            if len(current.calls) == 4:
                clock.value = HARD_DEADLINE_SECONDS

        client.on_chat = advance_after_d
        result = ForkSelectDeepenFinishRelay(client, clock=clock).solve("求一个非平凡整数 n。", "calculation")
        self.assertEqual(4, len(client.calls))
        self.assertEqual("7", result.final_response)
        self.assertEqual(
            "hard_deadline",
            next(entry["error_category"] for entry in result.trace if entry["stage"] == "finish"),
        )

    def test_t27_three_concurrent_solves_are_isolated(self):
        outputs = [None, None, None]

        def run(index):
            branch = "B" if index != 1 else "C"
            responses = [
                analysis(),
                idea("B", secret=f"B-{index}"),
                idea("C", secret=f"C-{index}"),
                deep(branch, candidate=str(index)),
                finish(str(index), str(index)),
            ]
            client = ScriptedClient(responses)
            outputs[index] = (client, ForkSelectDeepenFinishRelay(client).solve(f"题目 {index}", "calculation"))

        threads = [threading.Thread(target=run, args=(index,)) for index in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for index, item in enumerate(outputs):
            client, result = item
            self.assertEqual(5, len(client.calls))
            self.assertEqual(str(index), result.final_response)
            self.assertEqual(str(index), result.trace[-1]["model_calls"] and result.extracted_answer)
            self.assertEqual("C" if index == 1 else "B", result.trace[-1]["selected_branch"])

    def test_t28_official_shape_extra_constructor_args_and_json(self):
        config = AgentConfig(enable_fork_select_deepen_finish=True, max_model_calls=99)
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])
        agent = ReasoningAgent(client=client, config=config, unused_constructor_option=True)
        result = agent.solve("求一个非平凡整数 n。", {"idx": 1})
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["final_response"], str)
        self.assertTrue(result["final_response"])
        json.dumps(result, ensure_ascii=False)

    def test_t29_trace_has_no_problem_prompt_response_or_secret(self):
        secret_problem = "PROBLEM_SECRET_123"
        secret_response = "RAW_RESPONSE_SECRET_456\n" + analysis()
        client, result = solve_full(
            [secret_response, idea("B"), idea("C"), deep(), finish()],
            problem=secret_problem,
        )
        trace_text = json.dumps(result.trace, ensure_ascii=False)
        self.assertNotIn(secret_problem, trace_text)
        self.assertNotIn("RAW_RESPONSE_SECRET_456", trace_text)
        self.assertNotIn("你负责 Analyze", trace_text)
        self.assertNotIn("SECRET", trace_text)
        self.assertEqual(5, len(client.calls))

    def test_t30_metadata_answer_and_gold_are_ignored(self):
        config = AgentConfig(enable_fork_select_deepen_finish=True)
        responses = [analysis(), idea("B"), idea("C"), deep(), finish()]
        first_client = ScriptedClient(responses)
        second_client = ScriptedClient(responses)
        first = ReasoningAgent(first_client, config).solve("求一个非平凡整数 n。", {})
        second = ReasoningAgent(second_client, config).solve(
            "求一个非平凡整数 n。", {"answer": "999", "gold": "999", "idx": 999}
        )
        self.assertEqual(first, second)
        self.assertNotIn("999", json.dumps(second, ensure_ascii=False))

    def test_t31_relay_has_no_internal_concurrency(self):
        source = Path(__file__).resolve().parents[1] / "reasoning_agent" / "fork_select_deepen_finish.py"
        text = source.read_text(encoding="utf-8").casefold()
        for forbidden in ("thread", "async", "multiprocessing", "subprocess", "create_task", "process("):
            self.assertNotIn(forbidden, text)

    def test_t32_external_budget_values_cannot_raise_fixed_caps(self):
        config = AgentConfig(
            enable_fork_select_deepen_finish=True,
            max_model_calls=99,
            l2_max_model_calls=99,
            max_tokens=99999,
            l0_max_tokens=99999,
        )
        client = ScriptedClient([analysis(), idea("B"), idea("C"), deep(), finish()])
        result = ReasoningAgent(client, config).solve("求一个非平凡整数 n。", {})
        observed = [call[2] for call in client.calls]
        self.assertEqual([2048, 2048, 2048, 8192, 4096], observed)
        self.assertLessEqual(len(client.calls), 5)
        self.assertEqual(18432, sum(observed))
        self.assertEqual("7", result["final_response"])

    def test_t33_invalid_d_selection_degrades_as_protocol_failure(self):
        # D 响应存在但 SELECTED_BRANCH 不可解析 → 按 D 协议失败处置：
        # 确定性分支回退、不重试；D 的合法 FINAL_D 仍保留在答案优先级链中。
        client, result = solve_full(
            [
                analysis(),
                idea("B"),
                idea("C"),
                "SELECTED_BRANCH: 大概是B吧\nSELECTION_REASON: r\nCANDIDATE_D: 42\n"
                "FINAL_D: 42\nDERIVED: x=42\nOPEN: 无\nCHECKS: ok\nRISK: 无",
                RuntimeError("e"),
            ]
        )
        self.assertEqual(5, len(client.calls))
        self.assertEqual("42", result.final_response)
        self.assertEqual("deep_final", result.trace[-1]["fallback_source"])
        self.assertEqual("B", result.trace[-1]["selected_branch"])
        deepen_events = [entry for entry in result.trace if entry["stage"] == "deepen"]
        self.assertEqual("protocol_failed", deepen_events[-1]["status"])
        self.assertEqual("invalid_response", deepen_events[-1]["error_category"])
        self.assertNotIn("大概是B吧", client.calls[4][0][1]["content"])
        client2, result2 = solve_full(
            [analysis(), idea("B"), idea("C"), "SELECTED_BRANCH: 也许C\nFINAL_D: 42", finish("7", "7")]
        )
        self.assertEqual(5, len(client2.calls))
        self.assertEqual("7", result2.final_response)
        self.assertEqual("finish_final", result2.trace[-1]["fallback_source"])

    def test_t34_incomplete_d_fields_pass_allowed_fields_without_raw_text(self):
        # §8：字段缺失不是硬 parser 门——传递已有 handoff 字段并标记 incomplete，
        # 不把任意 D raw 或未选分支文本交给 E。
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nDERIVED: x=42\n"
            "自由推导：由对称性可知 x 为偶数，代入边界得唯一解 42，关键等式 2x=84 已确认。"
        )
        client, _ = solve_full([analysis(), idea("B"), idea("C"), d_response, finish()])
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("CANDIDATE_D: 42", e_prompt)
        self.assertIn("DERIVED: x=42", e_prompt)
        self.assertIn("HANDOFF_INCOMPLETE: true", e_prompt)
        self.assertNotIn("对称性", e_prompt)
        self.assertNotIn("DERIVED: UNKNOWN", e_prompt)
        self.assertNotIn("OPEN: UNKNOWN", e_prompt)
        self.assertNotIn("CHECKS: UNKNOWN", e_prompt)
        self.assertNotIn("RISK: UNKNOWN", e_prompt)
        client2, result2 = solve_full(
            [
                analysis(),
                idea("B"),
                idea("C"),
                "SELECTED_BRANCH: B\n经过长推导确认唯一候选 42，剩余步骤只有写出结论。",
                "CANDIDATE_E: 42\nFINAL: 42",
            ]
        )
        self.assertIn("HANDOFF_INCOMPLETE: true", client2.calls[4][0][1]["content"])
        self.assertNotIn("剩余步骤只有写出结论", client2.calls[4][0][1]["content"])
        self.assertNotIn("DERIVED: UNKNOWN", client2.calls[4][0][1]["content"])
        self.assertEqual("42", result2.final_response)

    def test_t35_max_contexts_still_deliver_d_handoff_to_e(self):
        # A fallback 5000 + 选中思路 1600 时，E 的 6500 配额内 D handoff 仍有固定预留。
        big_a = "GOAL: 只有这一个字段\n" + "背景" * 2600
        big_idea = "BRANCH: B\nMETHOD: " + "法" * 1590
        client, result = solve_full(
            [
                big_a,
                big_idea,
                idea("C"),
                "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nDERIVED: x=42\nOPEN: 写出结论\nCHECKS: ok\nRISK: 无",
                finish(),
            ]
        )
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("DERIVED: x=42", e_prompt)
        self.assertIn("OPEN: 写出结论", e_prompt)
        self.assertIn("SELECTED_BRANCH: B", e_prompt)
        self.assertIn("GOAL", e_prompt)
        self.assertIn("BRANCH", e_prompt)
        self.assertEqual("7", result.final_response)
        context = e_prompt.split("求一个非平凡整数 n。\n\n", 1)[1]
        self.assertLessEqual(len(context), 6500)

    def test_t36_unavailable_b_selection_fails_closed_to_c(self):
        d_response = (
            "SELECTED_BRANCH: B\nCANDIDATE_D: 42\nDERIVED: B_ONLY_DEEP_REASONING\n"
            "OPEN: B_OPEN\nCHECKS: B_CHECKS\nRISK: B_RISK"
        )
        client, result = solve_full(
            [analysis(), RuntimeError("b"), idea("C", secret="C_AVAILABLE"), d_response, finish()]
        )
        self.assertEqual("7", result.final_response)
        self.assertEqual("C", result.trace[-1]["selected_branch"])
        deepen = [entry for entry in result.trace if entry["stage"] == "deepen"][-1]
        self.assertEqual("protocol_failed", deepen["status"])
        self.assertEqual("invalid_response", deepen["error_category"])
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("C_AVAILABLE", e_prompt)
        self.assertIn("HANDOFF_INCOMPLETE: true", e_prompt)
        self.assertNotIn("B_ONLY_DEEP_REASONING", e_prompt)
        self.assertNotIn("CANDIDATE_D: 42", e_prompt)

    def test_t37_unavailable_c_selection_fails_closed_to_b(self):
        d_response = (
            "SELECTED_BRANCH: C\nCANDIDATE_D: 24\nDERIVED: C_ONLY_DEEP_REASONING\n"
            "OPEN: C_OPEN\nCHECKS: C_CHECKS\nRISK: C_RISK"
        )
        client, result = solve_full(
            [analysis(), idea("B", secret="B_AVAILABLE"), RuntimeError("c"), d_response, finish()]
        )
        self.assertEqual("7", result.final_response)
        self.assertEqual("B", result.trace[-1]["selected_branch"])
        deepen = [entry for entry in result.trace if entry["stage"] == "deepen"][-1]
        self.assertEqual("protocol_failed", deepen["status"])
        self.assertEqual("invalid_response", deepen["error_category"])
        e_prompt = client.calls[4][0][1]["content"]
        self.assertIn("B_AVAILABLE", e_prompt)
        self.assertIn("HANDOFF_INCOMPLETE: true", e_prompt)
        self.assertNotIn("C_ONLY_DEEP_REASONING", e_prompt)
        self.assertNotIn("CANDIDATE_D: 24", e_prompt)


if __name__ == "__main__":
    unittest.main()
