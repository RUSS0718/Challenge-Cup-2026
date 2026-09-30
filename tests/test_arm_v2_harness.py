"""Integration tests for the ARM-Harness v2 local experiment path."""

import unittest

from reasoning_agent.arm_v21_verification import VerificationResult
from reasoning_agent.skill_guidance import SkillRouteDecision
from reasoning_agent.skill_audit import SkillAuditResult
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ModeAwareClient:
    """Return scripted envelopes while recording request-local controls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record mode and timeout before returning the next response."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_mode": reasoning_mode,
                "timeout_seconds": timeout_seconds,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config(**overrides):
    """Build an isolated v2 harness configuration for a test case."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_allow_thinking_on": False,
        "arm_timeout_recovery_mode": "none",
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMHarnessV2Test(unittest.TestCase):
    """Verify selective trust, consensus, conflict resolution, and salvage."""

    @staticmethod
    def _ledger(result):
        """Return the solve-local evidence ledger from a result trace."""
        return next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")

    @staticmethod
    def _summary(result):
        """Return the ARM v2 summary event from a result trace."""
        return next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")

    def test_trusted_direct_candidate_stops_after_one_call(self):
        client = ModeAwareClient([
            {"content": "Final answer: 2", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertEqual("off", client.calls[0]["reasoning_mode"])
        candidate = self._ledger(result)["candidates"][0]
        self.assertEqual("valid", candidate["structural_validity"])
        self.assertEqual("high", candidate["trust_confidence"])
        self.assertTrue(self._summary(result)["early_stop"])

    def test_primary_and_second_prompts_require_explicit_final_answer(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,-1}", "finish_reason": "stop"},
            {"content": "Final answer: {-1,1}", "finish_reason": "stop"},
        ])
        ConstraintFitOrchestrator(client, config=_config()).solve("求满足 x^2=1 的所有解", {})
        self.assertIn("Final answer:", client.calls[0]["messages"][0]["content"])
        self.assertIn("Final answer:", client.calls[1]["messages"][0]["content"])

    def test_high_risk_candidate_gets_one_blind_second_sample(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,-1}", "finish_reason": "stop"},
            {"content": "Final answer: {-1,1}", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求满足 x^2=1 的所有解", {})

        self.assertEqual("{-1,1}", result["final_response"])
        self.assertEqual(["off", "off"], [call["reasoning_mode"] for call in client.calls])
        self.assertTrue(self._summary(result)["agreement"])
        self.assertTrue(self._summary(result)["second_sample_triggered"])
        self.assertEqual("deep_contract", self._summary(result)["second_sample_trigger_reason"])
        self.assertEqual("EQUIVALENT", self._summary(result)["a_b_relation"])
        self.assertEqual("confirmed", self._summary(result)["second_sample_outcome"])
        self.assertEqual("consensus", self._summary(result)["final_source"])
        self.assertEqual("typed_complete", self._summary(result)["primary_parse"]["status"])
        self.assertEqual(1, self._summary(result)["primary_parse"]["candidate_count"])

    def test_conflict_uses_a_b_only_resolver(self):
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": "Final answer: {118,120}", "finish_reason": "stop"},
            "CHECK: 代入关键约束后仅 A 满足\nDECISION: A",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})

        self.assertEqual("{117,119}", result["final_response"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual("off", client.calls[2]["reasoning_mode"])
        self.assertTrue(self._summary(result)["resolver_triggered"])
        self.assertTrue(self._summary(result)["conflict"])
        self.assertEqual("A", self._summary(result)["resolver_decision"])
        self.assertEqual("resolver_a", self._summary(result)["final_source"])
        self.assertEqual("candidate_a", self._summary(result)["resolver"]["selected_source"])

    def test_challenger_shadow_preserves_incumbent_on_conflict(self):
        challenger = (
            '{"verdict":"OBJECTION","issue_type":"arithmetic",'
            '"issue_location":"final value","claim":"conflict",'
            '"evidence":"independent check","repairable":false,'
            '"coverage":"final value"}\nFinal answer: {118,120}'
        )
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": challenger, "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_harness_version="v2.1.4", arm_challenger_shadow=True),
        ).solve("求所有可能的值", {})
        summary = self._summary(result)
        self.assertEqual("{117,119}", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertTrue(summary["challenger_shadow"])
        self.assertEqual("OBJECTION", summary["challenger_status"])
        self.assertFalse(summary["challenger"]["repairable"])
        self.assertEqual("challenger_shadow", summary["fallback_reason"])

    def test_typed_rejection_falls_back_to_generic_parser(self):
        client = ModeAwareClient([
            {"content": "Final answer: 21", "finish_reason": "stop"},
            {"content": "Final answer: 21", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "用 n 表示该复杂递推问题的最终结果",
            {},
        )
        self.assertEqual("21", result["final_response"])
        ledger = self._ledger(result)
        self.assertTrue(
            any(
                check.get("type") == "typed_parser_fallback"
                for candidate in ledger["candidates"]
                for check in candidate.get("checks", [])
            )
        )

    def test_equivalent_same_response_candidates_are_consolidated(self):
        client = ModeAwareClient([
            {
                "content": (
                    r"Final answer: \begin{bmatrix}-2\\5\\2\end{bmatrix}" "\n"
                    r"Final answer: \boxed{\begin{bmatrix}-2\\5\\2\end{bmatrix}}"
                ),
                "finish_reason": "stop",
            },
            {
                "content": r"Final answer: \begin{bmatrix}-2\\5\\2\end{bmatrix}",
                "finish_reason": "stop",
            },
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求一个复杂线性代数问题的最终向量",
            {},
        )
        self.assertNotEqual("UNKNOWN", result["final_response"])
        # Representation-equivalent boxed/unboxed values collapse before they
        # can become a same-response conflict.
        primary_values = [
            candidate["normalized_value"]
            for candidate in self._ledger(result)["candidates"]
            if candidate["source"] == "arm_primary"
        ]
        self.assertEqual(1, len(set(primary_values)))

    def test_truncated_explicit_primary_is_preserved_as_weak_incumbent(self):
        client = ModeAwareClient([
            {"content": "Final answer: 294", "finish_reason": "length"},
            {"content": "Final answer: 490", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求一个复杂组合问题的最终整数值",
            {},
        )
        summary = self._summary(result)
        self.assertEqual("294", result["final_response"])
        self.assertTrue(summary["safe_fallback_used"])
        self.assertEqual("candidate_a", summary["safe_candidate_source"])
        self.assertEqual("weak_truncated_incumbent", summary["safe_candidate"]["trust_reason"])

    def test_second_timeout_with_incumbent_returns_early_with_bounded_timeout(self):
        client = ModeAwareClient([
            {"content": "Final answer: 17", "finish_reason": "stop"},
            TimeoutError("challenger timeout"),
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求一个复杂数论问题的最终整数值",
            {},
        )
        self.assertEqual("17", result["final_response"])
        self.assertEqual(180, client.calls[1]["timeout_seconds"])
        self.assertTrue(self._summary(result)["safe_fallback_used"])

    def test_second_timeout_without_incumbent_uses_third_call_compact_salvage(self):
        client = ModeAwareClient([
            {"content": "无法形成最终答案", "finish_reason": "stop"},
            TimeoutError("challenger timeout"),
            {"content": "Final answer: 23", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求一个复杂组合问题的最终整数值",
            {},
        )
        self.assertEqual("23", result["final_response"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual(300, client.calls[1]["timeout_seconds"])
        self.assertEqual(90, client.calls[2]["timeout_seconds"])
        self.assertEqual(2048, client.calls[2]["max_tokens"])
        self.assertEqual(
            "second_timeout_compact_salvage",
            self._summary(result)["runtime_recovery_action"],
        )

    def test_plain_resolver_choice_cannot_replace_incumbent_without_check(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {3,4}", "finish_reason": "stop"},
            "B",
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求所有可能的值", {})
        summary = self._summary(result)
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual("UNKNOWN", summary["resolver_decision"])
        self.assertEqual("missing_targeted_check", summary["resolver"]["resolver_verdict"])

    def test_timeout_uses_compact_salvage_without_entering_trust_on_failure(self):
        client = ModeAwareClient([
            TimeoutError("provider timeout"),
            {"content": "Final answer: 2", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(
                arm_v2_mode="salvage",
                arm_timeout_recovery_mode="compact_salvage",
                arm_primary_timeout_seconds=30,
            ),
        ).solve("计算 1+1", {})

        self.assertEqual("2", result["final_response"])
        self.assertEqual([30, 15], [call["timeout_seconds"] for call in client.calls])
        self.assertEqual("compact_salvage", self._summary(result)["runtime_recovery_action"])

    def test_v214_keeps_incumbent_without_resolver(self):
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": "Final answer: {118,120}", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config(arm_harness_version="v2.1.4")).solve("求所有可能的值", {})

        self.assertEqual("{117,119}", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual(2, len(self._ledger(result)["candidates"]))
        self.assertFalse(self._summary(result)["resolver_triggered"])
        self.assertTrue(self._summary(result)["safe_fallback_used"])

    def test_v214_does_not_allow_challenger_replacement_without_review(self):
        client = ModeAwareClient([
            {"content": "Final answer: {117,119}", "finish_reason": "stop"},
            {"content": "Final answer: {118,120}", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config(arm_harness_version="v2.1.4")).solve("求所有可能的值", {})
        self.assertEqual("{117,119}", result["final_response"])
        self.assertEqual("v2.1.4_no_replacement_evidence", self._summary(result)["fallback_reason"])

    def test_v214_repair_and_fresh_review_replace_only_after_pass(self):
        challenger = (
            '{"verdict":"OBJECTION","issue_type":"arithmetic",'
            '"issue_location":"final value","claim":"A is wrong",'
            '"evidence":"direct substitution gives 2","repairable":true,'
            '"coverage":"final value"}\nFinal answer: {2,3}'
        )
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": challenger, "finish_reason": "stop"},
            {"content": "Final answer: {2,3}", "finish_reason": "stop"},
            '{"status":"PASS","checked_issue":"final value",'
            '"check_result":"direct substitution gives 2","remaining_problem":null}',
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(
                arm_harness_version="v2.1.4",
                arm_enable_targeted_repair=True,
                arm_enable_fresh_review=True,
                arm_adaptive_token_budget=20_480,
            ),
        ).solve("求所有可能的值", {})
        summary = self._summary(result)
        self.assertEqual("{2,3}", result["final_response"])
        self.assertEqual(4, len(client.calls))
        self.assertEqual("OBJECTION", summary["challenger_status"])
        self.assertEqual("PASS", summary["fresh_review_status"])
        self.assertEqual("repair", summary["final_source"])

    def test_v214_plain_pass_cannot_replace_primary(self):
        challenger = (
            '{"verdict":"OBJECTION","issue_type":"arithmetic",'
            '"issue_location":"final value","claim":"A is wrong",'
            '"evidence":"direct substitution gives 2","repairable":true,'
            '"coverage":"final value"}\nFinal answer: {2,3}'
        )
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": challenger, "finish_reason": "stop"},
            {"content": "Final answer: {2,3}", "finish_reason": "stop"},
            "PASS",
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(
                arm_harness_version="v2.1.4",
                arm_enable_targeted_repair=True,
                arm_enable_fresh_review=True,
                arm_adaptive_token_budget=20_480,
            ),
        ).solve("求所有可能的值", {})
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual("UNKNOWN", self._summary(result)["fresh_review_status"])
        self.assertEqual(4, len(client.calls))

    def test_v214_keeps_primary_without_spending_a_resolver_call(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {2,3}", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_harness_version="v2.1.4"),
        ).solve("求所有可能的值", {})
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual(2, len(client.calls))

    def test_v214_injected_verifier_cannot_select_b_without_review(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {2,3}", "finish_reason": "stop"},
        ])
        orchestrator = ConstraintFitOrchestrator(client, config=_config(arm_harness_version="v2.1.4"))

        class SelectB:
            """Simulate a verifier that recommends the challenger."""

            def verify(self, candidate_a, candidate_b, problem):
                """Return B so the host replacement boundary is exercised."""
                return VerificationResult("B", candidate_b.candidate_id, "candidate_check")

        orchestrator.deterministic_verifier = SelectB()
        result = orchestrator.solve("求所有可能的值", {})
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual("B", self._summary(result)["verification"]["status"])
        self.assertEqual(2, len(client.calls))

    def test_v214_skill_refutation_keeps_primary_as_incumbent(self):
        client = ModeAwareClient([
            {"content": "Final answer: 2", "finish_reason": "stop"},
            TimeoutError("challenger timeout"),
        ])

        class RefutingAuditor:
            """Return negative evidence without deleting the candidate."""

            def audit(self, **kwargs):
                """Mark the primary as refuted so the safe checkpoint is tested."""
                return SkillAuditResult("refuted", "exact-evaluation", "counterexample")

        result = ConstraintFitOrchestrator(
            client,
            config=_config(
                arm_harness_version="v2.1.4",
                arm_enable_skill_audit=True,
                arm_max_skill_audits=1,
                arm_trust_policy="positive_evidence",
            ),
            skill_auditor=RefutingAuditor(),
        ).solve("计算一个复杂的函数极限", {})
        self.assertEqual("2", result["final_response"])
        self.assertEqual("refuted", self._summary(result)["skill_status"])
        self.assertIsNotNone(self._summary(result)["safe_candidate"])

    def test_fragment_is_not_a_safe_candidate_and_exposes_failure_reason(self):
        client = ModeAwareClient([
            {"content": "Final answer: x_s", "finish_reason": "stop"},
            {"content": "Final answer: x_s", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve("求一个数", {})

        summary = self._summary(result)
        self.assertEqual("UNKNOWN", result["final_response"])
        self.assertEqual("second_sample_incomplete", result["final_failure_reason"])
        self.assertFalse(summary["primary_candidate"]["answer_complete"])
        self.assertEqual("primary_incomplete", summary["second_sample_trigger_reason"])
        self.assertEqual("NO_VALID_PAIR", summary["a_b_relation"])
        self.assertIsNone(summary["safe_candidate"])
        self.assertFalse(summary["resolver_triggered"])

    def test_deterministic_verifier_selects_existing_candidate_before_resolver(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {3,4}", "finish_reason": "stop"},
        ])
        orchestrator = ConstraintFitOrchestrator(client, config=_config())

        class SelectA:
            def verify(self, candidate_a, candidate_b, problem):
                return VerificationResult("A", candidate_a.candidate_id, "cheap_falsification")

        orchestrator.deterministic_verifier = SelectA()
        result = orchestrator.solve("求所有可能的值", {})

        summary = self._summary(result)
        self.assertEqual("{1,2}", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual("A", summary["verification"]["status"])
        self.assertFalse(summary["resolver_triggered"])
        self.assertEqual("candidate_a", summary["final_source"])

    def test_verifier_exception_fails_open_to_resolver(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {3,4}", "finish_reason": "stop"},
            "CHECK: 直接检查关键约束后 A 成立\nDECISION: A",
        ])
        orchestrator = ConstraintFitOrchestrator(client, config=_config())

        class BrokenVerifier:
            def verify(self, candidate_a, candidate_b, problem):
                raise RuntimeError("not applicable")

        orchestrator.deterministic_verifier = BrokenVerifier()
        result = orchestrator.solve("求所有可能的值", {})

        summary = self._summary(result)
        self.assertEqual(3, len(client.calls))
        self.assertEqual("UNKNOWN", summary["verification"]["status"])
        self.assertTrue(summary["resolver_triggered"])

    def test_skill_guidance_is_only_injected_into_primary_by_default(self):
        client = ModeAwareClient([
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
            {"content": "Final answer: {1,2}", "finish_reason": "stop"},
        ])
        orchestrator = ConstraintFitOrchestrator(
            client,
            config=_config(arm_enable_skill_guidance=True),
        )

        class Router:
            def route(self, problem, contract):
                return SkillRouteDecision("demo", 0.9, "test_route")

            def guidance(self, decision):
                return "先检查对称性"

        orchestrator.skill_router = Router()
        orchestrator.solve("求所有可能的值", {})

        self.assertIn("先检查对称性", client.calls[0]["messages"][0]["content"] + client.calls[0]["messages"][1]["content"])
        self.assertNotIn("先检查对称性", client.calls[1]["messages"][0]["content"] + client.calls[1]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
