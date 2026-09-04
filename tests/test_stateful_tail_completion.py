"""Zero-model replay tests for ``stateful_tail_completion_v1`` (default off).

Frozen trigger (strict口径, preregistration STATEFUL-TAIL-V1): the fifth model
call continues the 4th unfinished response only when ALL of the following
hold — flag enabled, exactly four model calls used, zero candidates with an
extractable answer, and the 4th call returned a continuable (non-error,
non-empty) response.  Any other path must stay transcript-identical to the
hetero_k5 baseline.  No network: every test drives ReasoningAgent with a
scripted FakeClient.
"""
import concurrent.futures
import dataclasses
import json
import unittest

from user_agent import (
    ALTERNATIVE_REASONER_PROMPT,
    DIRECT_REASONER_PROMPT,
    STATEFUL_TAIL_CONTINUATION_PROMPT,
    ReasoningAgent,
    SUBMISSION_CONFIG,
)

PROBLEM = "设 a = 2，b = 3，求 a 与 b 的乘积。"
L0_PROBLEM = "1+1"
FALLBACK_FINAL = "未能生成有效数学答案。"


def truncated(seed: str = "", length: int = 600) -> str:
    """A long mid-reasoning response with no extractable answer marker."""
    unit = (
        "我们先分析问题的结构，然后逐步推演。设未知量并代入条件，化简得到新的关系，"
        "继续推进计算并核对边界情形，再回到主线推导，检查特殊取值与对称性，"
        "随后把中间结果合并成完整的推导链，暂时还没有得出可以收束的结论。"
    )
    body = (unit * (length // len(unit) + 1))[:length]
    return f"{seed}{body}"


def ok(answer: str) -> str:
    return f"代入计算得 {answer}。\n最终答案：{answer}"


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def baseline_config():
    return dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_contextual_answer_reconstruction=False,
        enable_fork_select_deepen_finish=False,
    )


def tail_config(**overrides):
    return dataclasses.replace(
        SUBMISSION_CONFIG,
        enable_contextual_answer_reconstruction=False,
        enable_fork_select_deepen_finish=False,
        enable_stateful_tail_completion=True,
        **overrides
    )


def solve_with(config, responses, problem=PROBLEM):
    client = FakeClient(responses)
    agent = ReasoningAgent(client=client, config=config)
    result = agent.solve(problem, {"idx": 0})
    return client, result


def prompts(client):
    return [call[0] for call in client.calls]


class StatefulTailDefaultOffTest(unittest.TestCase):
    def test_submission_config_keeps_flag_off(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_stateful_tail_completion)
        self.assertFalse(baseline_config().enable_stateful_tail_completion)


class UntriggeredParityTest(unittest.TestCase):
    def test_consensus_transcript_identical_to_baseline(self):
        responses = [ok("6"), ok("6"), ok("6"), ok("6"), ok("6")]
        off_client, off_result = solve_with(baseline_config(), responses)
        on_client, on_result = solve_with(tail_config(), responses)
        # Consensus stops at 3 calls; the fifth slot never happens.
        self.assertEqual(len(on_client.calls), 3)
        self.assertEqual(prompts(on_client), prompts(off_client))
        self.assertEqual(on_result, off_result)

    def test_fifth_slot_stays_fresh_when_a_candidate_exists(self):
        responses = [ok("1"), ok("2"), ok("3"), truncated("R4"), ok("4")]
        on_client, on_result = solve_with(tail_config(), responses)
        off_client, off_result = solve_with(baseline_config(), responses)
        self.assertEqual(len(on_client.calls), 5)
        # Candidates exist after four calls, so the strict trigger must not
        # fire and the whole solve must match the baseline transcript.
        self.assertEqual(prompts(on_client), prompts(off_client))
        self.assertEqual(on_result, off_result)

    def test_l0_problem_never_continues(self):
        client, result = solve_with(tail_config(), [ok("2"), ok("2")], problem=L0_PROBLEM)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("tail_continuation", json.dumps(result, ensure_ascii=False))


class TriggeredFifthSlotTest(unittest.TestCase):
    def test_all_four_unextractable_triggers_continuation(self):
        responses = [
            truncated("R1"),
            truncated("R2"),
            truncated("R3"),
            truncated("R4TAIL_"),
            ok("24"),
        ]
        on_client, on_result = solve_with(tail_config(), responses)
        off_client, off_result = solve_with(baseline_config(), responses)
        # Calls 1-4 are byte-identical between arms (prompt, temperature, tokens).
        self.assertEqual(prompts(on_client)[:4], prompts(off_client)[:4])
        self.assertEqual(len(on_client.calls), 5)
        system_msg, user_msg = on_client.calls[4][0]
        self.assertEqual(system_msg["content"], STATEFUL_TAIL_CONTINUATION_PROMPT)
        self.assertIn("此前一次解答的末尾片段", user_msg["content"])
        self.assertIn("不要从头重新作答", user_msg["content"])
        self.assertIn("R4TAIL_", user_msg["content"])
        self.assertNotIn("请给出完整解答", user_msg["content"])
        # Same call budget shape as the baseline fifth slot.
        self.assertEqual(on_client.calls[4][1], on_client.calls[0][1])
        self.assertEqual(on_client.calls[4][2], on_client.calls[0][2])
        # The baseline fifth slot is a fresh direct recompute (task_extra may be appended), not a continuation.
        self.assertIn(DIRECT_REASONER_PROMPT, off_client.calls[4][0][0]["content"])
        self.assertNotEqual(off_client.calls[4][0][0]["content"], STATEFUL_TAIL_CONTINUATION_PROMPT)
        self.assertIn("请给出完整解答", off_client.calls[4][0][1]["content"])
        # Result: the continuation answer is extracted through the normal path.
        self.assertEqual(on_result["extracted_answer"], "24")
        self.assertIn("24", on_result["final_response"])
        self.assertNotIn("tail_continuation", json.dumps(off_result, ensure_ascii=False))

    def test_trace_records_tail_continuation_reasoner(self):
        responses = [truncated("R1"), truncated("R2"), truncated("R3"), truncated("R4"), ok("9")]
        client, result = solve_with(tail_config(), responses)
        entries = [
            entry
            for entry in result["trace"]
            if entry.get("step") == "generate_candidate" and entry.get("reasoner") == "tail_continuation"
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "ok")
        # The raw tail payload must not leak into the trace.
        self.assertNotIn("R1", json.dumps(result, ensure_ascii=False))

    def test_tail_is_truncated_to_last_max_chars(self):
        long_response = truncated("HEADMARK_NEVER_", length=9500) + "TAILMARK_LAST_9751"
        self.assertGreater(len(long_response), 8000)
        responses = [truncated("R1"), truncated("R2"), truncated("R3"), long_response, ok("7")]
        client, _ = solve_with(tail_config(), responses)
        user_msg = client.calls[4][0][1]["content"]
        self.assertIn("TAILMARK_LAST_9751", user_msg)
        self.assertNotIn("HEADMARK_NEVER_", user_msg)

    def test_tail_respects_configured_max_chars(self):
        long_response = truncated("OPENHEAD_", length=400) + "CLOSETAIL_424242"
        responses = [truncated("R1"), truncated("R2"), truncated("R3"), long_response, ok("7")]
        client, _ = solve_with(tail_config(stateful_tail_max_chars=50), responses)
        user_msg = client.calls[4][0][1]["content"]
        self.assertIn("CLOSETAIL_424242", user_msg)
        self.assertNotIn("OPENHEAD_", user_msg)

    def test_continuation_unextractable_fails_closed(self):
        responses = [truncated("R1"), truncated("R2"), truncated("R3"), truncated("R4"), truncated("R5")]
        client, result = solve_with(tail_config(), responses)
        # Budget capped at five calls; no salvage, no extra calls.
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(result["final_response"], FALLBACK_FINAL)
        self.assertEqual(result["extracted_answer"], "")
        json.dumps(result, ensure_ascii=False)


class TailSourceHygieneTest(unittest.TestCase):
    def test_fourth_call_model_error_falls_back_to_fresh_fifth(self):
        responses = [truncated("R1"), truncated("R2"), truncated("R3"), RuntimeError("boom"), ok("24")]
        on_client, on_result = solve_with(tail_config(), responses)
        off_client, off_result = solve_with(baseline_config(), responses)
        self.assertEqual(len(on_client.calls), 5)
        # The 4th call failed, so there is no 4th response to continue: the
        # fifth slot must be exactly the baseline fresh recompute.
        self.assertEqual(prompts(on_client), prompts(off_client))
        self.assertEqual(on_result, off_result)

    def test_concurrent_solves_are_isolated(self):
        trigger_responses = [truncated("R1"), truncated("R2"), truncated("R3"), truncated("R4"), ok("24")]
        consensus_responses = [ok("6"), ok("6"), ok("6"), ok("6"), ok("6")]
        configs = [tail_config(), tail_config(), tail_config(), tail_config()]
        response_sets = [trigger_responses, consensus_responses, trigger_responses, consensus_responses]

        def run(index):
            client = FakeClient(list(response_sets[index]))
            agent = ReasoningAgent(client=client, config=configs[index])
            result = agent.solve(PROBLEM, {"idx": index})
            return client, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(run, range(4)))
        for index, (client, result) in enumerate(outcomes):
            self.assertTrue(result.get("final_response"))
            json.dumps(result, ensure_ascii=False)
            if index % 2 == 0:
                self.assertEqual(len(client.calls), 5)
                self.assertEqual(client.calls[4][0][0]["content"], STATEFUL_TAIL_CONTINUATION_PROMPT)
            else:
                self.assertEqual(len(client.calls), 3)


if __name__ == "__main__":
    unittest.main()
