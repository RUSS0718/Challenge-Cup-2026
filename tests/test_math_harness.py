import json
import unittest
from dataclasses import replace

from reasoning_agent.math_harness import (
    CANDIDATE_CONFLICT,
    CANDIDATE_PARSED,
    CANDIDATE_REJECTED,
    CANDIDATE_TRUNCATED,
    ConstraintFitOrchestrator,
    EvidenceLedger,
    FrozenErrorNotebook,
    HarnessConfig,
    HostParser,
    HostRouter,
    METHOD_ID,
    SubmissionGateway,
    TypedMicroToolError,
    TypedMicroToolProvider,
    answer_equivalence,
    normalize_answer,
)
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        if not self.responses:
            raise AssertionError("scripted client exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class BankHit:
    answer = "17"
    case_id = "case-17"
    source_family = "reviewed"


class MathHarnessParserTest(unittest.TestCase):
    def test_free_format_and_answer_types(self):
        parser = HostParser()
        parsed = parser.parse("先计算得到 42", problem="计算 6×7", source="attempt_a")
        self.assertEqual(CANDIDATE_PARSED, parsed.status)
        self.assertEqual("42", parsed.candidates[0].value)
        self.assertEqual("integer", parsed.candidates[0].answer_type)

        choice = parser.parse("答案：B", problem="选择正确选项 A. 1\nB. 2", source="attempt_a")
        self.assertEqual("choice", choice.candidates[0].answer_type)
        self.assertEqual("B", choice.candidates[0].value)

    def test_boxed_fraction_and_unordered_set_are_safe(self):
        parser = HostParser()
        fraction = parser.parse(r"\boxed{\frac{1}{2}}", problem="求一个分数", source="attempt_a")
        self.assertEqual("1/2", fraction.candidates[0].normalized_value)
        self.assertEqual("EQUIVALENT", answer_equivalence(r"\frac{1}{2}", "0.5"))

        left = parser.parse("最终答案：{1, -1}", problem="求根", source="attempt_a")
        right = parser.parse("最终答案：{-1,1}", problem="求根", source="attempt_a")
        self.assertEqual(left.candidates[0].normalized_value, right.candidates[0].normalized_value)

    def test_choice_punctuation_is_canonicalized(self):
        parser = HostParser()
        left = parser.parse("最终答案：a.", problem="选择正确选项 A. 1\nB. 2", source="attempt_a")
        right = parser.parse("最终答案：A", problem="选择正确选项 A. 1\nB. 2", source="attempt_b")
        self.assertEqual("A", left.candidates[0].value)
        self.assertEqual("EQUIVALENT", answer_equivalence(left.candidates[0].value, right.candidates[0].value))

    def test_duplicates_do_not_create_a_conflict(self):
        parser = HostParser()
        parsed = parser.parse(
            "最终答案：1/2\n最终答案：0.5",
            problem="计算一个分数",
            source="attempt_a",
        )
        self.assertEqual(1, len(parsed.candidates))
        self.assertNotEqual(CANDIDATE_CONFLICT, parsed.status)

    def test_placeholder_and_incomplete_formula_are_rejected(self):
        parser = HostParser()
        placeholder = parser.parse("最终答案：<具体答案>", problem="计算 1+1", source="attempt_a")
        incomplete = parser.parse("最终答案：(1+2", problem="计算 1+1", source="attempt_a")
        self.assertEqual(CANDIDATE_REJECTED, placeholder.status)
        self.assertEqual(CANDIDATE_REJECTED, incomplete.status)

    def test_length_envelope_distinguishes_candidate_and_no_candidate(self):
        parser = HostParser()
        with_candidate = parser.parse(
            "最终答案：7",
            problem="计算 3+4",
            source="attempt_a",
            finish_reason="length",
        )
        without_candidate = parser.parse(
            "推理在中途结束",
            problem="计算 3+4",
            source="attempt_a",
            finish_reason="length",
        )
        self.assertEqual(CANDIDATE_TRUNCATED, with_candidate.status)
        self.assertEqual("truncated_without_candidate", without_candidate.status)

    def test_terminal_scalar_equation_uses_final_rhs(self):
        parser = HostParser()
        parsed = parser.parse("2^7 = 128", problem="计算一个数", source="attempt_a")
        self.assertEqual(CANDIDATE_PARSED, parsed.status)
        self.assertEqual("128", parsed.candidates[0].normalized_value)

    def test_terminal_scalar_equation_strips_trailing_math_delimiter(self):
        parser = HostParser()
        parsed = parser.parse("$2^7 = 128$$", problem="计算一个数", source="attempt_a")
        self.assertEqual(CANDIDATE_PARSED, parsed.status)
        self.assertEqual("128", parsed.candidates[0].normalized_value)

    def test_marked_scalar_equation_uses_final_rhs(self):
        parser = HostParser()
        parsed = parser.parse("答案：m=12", problem="计算一个数", source="attempt_a")
        self.assertEqual(CANDIDATE_PARSED, parsed.status)
        self.assertEqual("12", parsed.candidates[0].normalized_value)

    def test_scalar_candidate_strips_one_unmatched_math_delimiter(self):
        parser = HostParser()
        parsed = parser.parse("最终答案：9$", problem="计算一个数", source="attempt_a")
        self.assertEqual(CANDIDATE_PARSED, parsed.status)
        self.assertEqual("9", parsed.candidates[0].normalized_value)


class MathHarnessOrchestratorTest(unittest.TestCase):
    @staticmethod
    def _ledger(result):
        return next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")

    @staticmethod
    def _finalize(result):
        return next(item for item in reversed(result["trace"]) if item.get("stage") == "finalize")

    def test_bare_and_submission_profiles_have_distinct_harness_modes(self):
        self.assertFalse(AgentConfig().enable_constraint_fit_harness)
        self.assertFalse(AgentConfig().enable_constraint_fit_deep_lane)
        self.assertTrue(SUBMISSION_CONFIG.enable_constraint_fit_harness)
        self.assertTrue(SUBMISSION_CONFIG.enable_constraint_fit_deep_lane)
        self.assertTrue(SUBMISSION_CONFIG.enable_constraint_fit_hybrid_router)
        self.assertTrue(SUBMISSION_CONFIG.enable_temporary_answer_bank)
        self.assertEqual("on", SUBMISSION_CONFIG.harness_bank_mode)
        self.assertEqual("bounded_evidence_trajectory_selection_v1", METHOD_ID)

    def test_ordinary_first_attempt_early_stops(self):
        client = ScriptedClient(["答案是 12"])
        result = ConstraintFitOrchestrator(client).solve("计算 3×4", {"answer": "999"})
        self.assertEqual("12", result["final_response"])
        self.assertEqual("12", result["extracted_answer"])
        self.assertEqual([4096], [call[2] for call in client.calls])
        self.assertEqual("candidate_unproven", self._finalize(result)["source"])

    def test_missing_candidate_uses_blind_second_attempt(self):
        client = ScriptedClient(["SECRET_RESPONSE without a conclusion", "最终答案：9"])
        result = ConstraintFitOrchestrator(client).solve("计算 3×3")
        self.assertEqual("9", result["final_response"])
        self.assertEqual([4096, 4096], [call[2] for call in client.calls])
        second_user = client.calls[1][0][1]["content"]
        self.assertNotIn("SECRET_RESPONSE", second_user)
        ledger = self._ledger(result)
        states = [item["state"] for item in ledger["states"]]
        self.assertIn("attempt_b", states)
        self.assertIn("candidate_b", states)

    def test_conflict_is_retained_and_critic_selects_existing_candidate(self):
        client = ScriptedClient([
            "最终答案：8\n最终答案：9",
            "最终答案：10",
            "SELECT: B",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算一个未知量")
        self.assertEqual("9", result["final_response"])
        self.assertEqual([4096, 4096, 2048], [call[2] for call in client.calls])
        ledger = self._ledger(result)
        self.assertTrue(ledger["conflicts"])
        self.assertEqual("critic_selected", self._finalize(result)["source"])
        json.dumps(result, ensure_ascii=False)

    def test_unresolved_conflict_abstains(self):
        client = ScriptedClient([
            "最终答案：8\n最终答案：9",
            "最终答案：10",
            "UNKNOWN",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算一个未知量")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("", result["extracted_answer"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual("abstained", self._finalize(result)["status"])

    def test_repair_without_diagnosis_is_not_allowed(self):
        client = ScriptedClient([
            "最终答案：8\n最终答案：9",
            "最终答案：10",
            "REPAIR: A",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算一个未知量")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertNotIn("repair", [event["state"] for event in self._ledger(result)["states"]])

    def test_repair_requires_explicit_critic_request(self):
        client = ScriptedClient([
            "最终答案：8\n最终答案：9",
            "最终答案：10",
            "REPAIR: A\n错误：候选 A 的符号与条件冲突",
            "最终答案：9",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算一个未知量")
        self.assertEqual("9", result["final_response"])
        self.assertEqual([4096, 4096, 2048, 4096], [call[2] for call in client.calls])
        self.assertIn("repair", [event["state"] for event in self._ledger(result)["states"]])
        self.assertEqual("critic_repair", self._finalize(result)["source"])

    def test_truncated_candidate_gets_one_short_continuation(self):
        client = ScriptedClient([
            {"content": "最终答案：7", "finish_reason": "length", "usage": {"completion_tokens": 4096}},
            "最终答案：7",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算 3+4")
        self.assertEqual("7", result["final_response"])
        self.assertEqual([4096, 2048], [call[2] for call in client.calls])
        self.assertEqual("continuation_agreement", self._finalize(result)["source"])
        ledger = self._ledger(result)
        self.assertEqual(4096, ledger["budget"]["actual_completion_tokens"])
        self.assertEqual(CANDIDATE_TRUNCATED, ledger["candidates"][0]["extraction_status"])
        self.assertIn("continuation", [candidate["source"] for candidate in ledger["candidates"]])

    def test_truncated_without_candidate_fails_closed_if_recovery_also_fails(self):
        client = ScriptedClient([
            {"content": "推理被截断", "finish_reason": "length"},
            "仍然没有明确结论",
        ])
        result = ConstraintFitOrchestrator(client).solve("计算 3+4")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertNotIn("推理被截断", json.dumps(result, ensure_ascii=False))

    def test_early_stop_can_be_disabled_without_changing_hard_cap(self):
        client = ScriptedClient(["最终答案：7", "最终答案：7"])
        config = HarnessConfig(early_stop=False, max_model_calls=2, total_token_budget=8192)
        result = ConstraintFitOrchestrator(client, config=config).solve("计算 3+4")
        self.assertEqual("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual(8192, self._ledger(result)["budget"]["requested_tokens"])

    def test_call_and_token_caps_are_hard(self):
        client = ScriptedClient([
            "最终答案：8\n最终答案：9",
            "最终答案：10",
            "UNKNOWN",
            "最终答案：11",
        ])
        config = HarnessConfig(max_model_calls=99, total_token_budget=16_384)
        result = ConstraintFitOrchestrator(client, config=config).solve("计算一个未知量")
        self.assertLessEqual(len(client.calls), 5)
        ledger = self._ledger(result)
        self.assertLessEqual(ledger["budget"]["calls"], 5)
        self.assertLessEqual(ledger["budget"]["requested_tokens"], 16_384)

    def test_trace_is_compact_and_json_serializable(self):
        client = ScriptedClient(["最终答案：42\n秘密原文不应进入 trace"])
        result = ConstraintFitOrchestrator(client).solve("计算 6×7")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("秘密原文", serialized)
        self.assertNotIn("ATTEMPT_A_SYSTEM", serialized)
        self.assertTrue(result["final_response"].strip())

    def test_bank_off_never_calls_lookup(self):
        def forbidden_lookup(_problem):
            raise AssertionError("bank lookup must not run in bank-off mode")

        client = ScriptedClient(["最终答案：5"])
        result = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(bank_mode="off"),
            bank_lookup=forbidden_lookup,
        ).solve("计算 2+3")
        self.assertEqual("5", result["final_response"])

    def test_bank_on_hit_is_separate_from_model_capability(self):
        calls = []

        def lookup(problem):
            calls.append(problem)
            return BankHit()

        client = ScriptedClient([])
        result = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(bank_mode="on"),
            bank_lookup=lookup,
        ).solve("计算 3+14")
        self.assertEqual("17", result["final_response"])
        self.assertEqual([], client.calls)
        self.assertEqual(1, len(calls))
        self.assertEqual("temporary_answer_bank", result["trace"][0]["source"])

    def test_hybrid_router_uses_explicit_legacy_backend(self):
        class Legacy:
            def solve(self, problem, metadata):
                self_problem = problem
                self_metadata = metadata
                return {
                    "final_response": "legacy proof",
                    "extracted_answer": "",
                    "trace": [],
                }

        client = ScriptedClient([])
        result = ConstraintFitOrchestrator(
            client,
            legacy_backend=Legacy(),
        ).solve("请证明一个命题", {"idx": 4})
        self.assertEqual("legacy proof", result["final_response"])
        self.assertEqual([], client.calls)
        self.assertTrue(any(event.get("stage") == "route" and event["target"] == "legacy_fsdf" for event in result["trace"]))

    def test_response_after_wall_limit_is_fail_closed(self):
        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        class SlowClient(ScriptedClient):
            def chat(self, messages, temperature, max_tokens):
                clock.now = 2.0
                return super().chat(messages, temperature, max_tokens)

        client = SlowClient(["最终答案：7"])
        result = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(max_wall_seconds=1.0),
            clock=clock,
        ).solve("计算 3+4")
        self.assertEqual("UNKNOWN", result["final_response"])
        ledger = self._ledger(result)
        self.assertEqual("timeout", ledger["calls"][0]["error_category"])

    def test_mixed_task_fails_closed_without_hybrid(self):
        client = ScriptedClient([])
        result = ConstraintFitOrchestrator(client).solve("请证明该命题并解释原因")
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual([], client.calls)
        route = next(item for item in result["trace"] if item.get("stage") == "route")
        self.assertEqual("mixed", route["answer_type"])


class BoundaryAndSupportTest(unittest.TestCase):
    def test_budget_ledger_reserves_before_call_and_caps(self):
        from reasoning_agent.math_harness import BudgetLedger

        ledger = BudgetLedger(max_calls=99, total_tokens=16_384)
        reservations = []
        for stage, tokens in (
            ("attempt_a", 4096),
            ("attempt_b", 4096),
            ("critic", 2048),
            ("repair", 4096),
            ("continuation", 2048),
        ):
            reservation = ledger.reserve(stage, tokens)
            self.assertIsNotNone(reservation)
            reservations.append(reservation)
        self.assertIsNone(ledger.reserve("extra", 1))
        self.assertEqual(5, ledger.calls_used)
        self.assertEqual(16_384, ledger.requested_tokens)

    def test_typed_tools_are_disabled_bounded_and_whitelisted(self):
        with self.assertRaisesRegex(TypedMicroToolError, "tool_disabled"):
            TypedMicroToolProvider().call("gcd", {"a": 2, "b": 4})
        provider = TypedMicroToolProvider(enabled=True, max_abs_integer=100)
        self.assertEqual(6, provider.call("gcd", {"a": 12, "b": 18}))
        self.assertEqual([2, 2, 3], provider.call("prime_factors", {"n": 12}))
        self.assertEqual("EQUIVALENT", provider.call("rational_compare", {"left": "1/2", "right": "0.5"}))
        with self.assertRaisesRegex(TypedMicroToolError, "tool_not_allowed"):
            provider.call("python", {"code": "1+1"})
        with self.assertRaisesRegex(TypedMicroToolError, "integer_out_of_bounds"):
            provider.call("gcd", {"a": 101, "b": 1})
        with self.assertRaisesRegex(TypedMicroToolError, "tool_timeout"):
            provider.call("gcd", {"a": 1, "b": 2}, timeout_seconds=0)

    def test_frozen_notebook_cannot_learn(self):
        notebook = FrozenErrorNotebook([{"id": "x", "category": "generic", "hint": "bounded"}])
        self.assertEqual("bounded", notebook.snapshot()[0]["hint"])
        with self.assertRaisesRegex(RuntimeError, "read_only"):
            notebook.record("new")
        self.assertEqual("bounded", notebook.snapshot()[0]["hint"])

    def test_gateway_validates_explicit_modes(self):
        with self.assertRaises(ValueError):
            SubmissionGateway("maybe")
        self.assertEqual("model", SubmissionGateway("off").resolve("question").source)

    def test_gateway_accepts_mapping_hit_and_falls_back_on_lookup_error(self):
        hit = SubmissionGateway(
            "on", lambda _problem: {"answer": "17", "case_id": "case-17", "source_family": "reviewed"}
        ).resolve("question")
        self.assertEqual("hit", hit.status)
        self.assertEqual("17", hit.answer)
        failed = SubmissionGateway("on", lambda _problem: (_ for _ in ()).throw(RuntimeError("secret"))).resolve("question")
        self.assertEqual("error", failed.status)
        self.assertEqual("temporary_answer_bank", failed.source)

    def test_config_rejects_non_finite_wall_limit(self):
        with self.assertRaises(ValueError):
            HarnessConfig(max_wall_seconds=float("nan"))

    def test_router_never_uses_metadata_as_answer(self):
        router = HostRouter()
        decision = router.route("计算 3+4", {"answer": "999", "idx": 0})
        self.assertEqual("harness", decision.target)
        self.assertEqual("scalar_or_exact_answer", decision.reason)


class ReasoningAgentIntegrationTest(unittest.TestCase):
    def test_reasoning_agent_harness_is_opt_in_and_bank_off_is_enforced(self):
        client = ScriptedClient(["最终答案：12"])
        config = AgentConfig(
            enable_constraint_fit_harness=True,
            enable_temporary_answer_bank=False,
        )
        result = ReasoningAgent(client, config).solve("计算 3×4", {"answer": "999"})
        self.assertEqual("12", result["final_response"])
        self.assertEqual(1, len(client.calls))
        gateway = next(item for item in result["trace"] if item.get("stage") == "submission_gateway")
        self.assertEqual("off", gateway["bank_mode"])

    def test_reasoning_agent_harness_can_use_explicit_bank_on(self):
        client = ScriptedClient(["最终答案：12"])
        config = AgentConfig(
            enable_constraint_fit_harness=True,
            enable_temporary_answer_bank=True,
            harness_bank_mode="on",
        )
        result = ReasoningAgent(client, config).solve("计算 3×4", {})
        # The fixture bank does not contain this new question, so model path is used.
        self.assertEqual("12", result["final_response"])
        self.assertEqual(1, len(client.calls))


if __name__ == "__main__":
    unittest.main()
