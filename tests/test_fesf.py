import json
import threading
import unittest
from pathlib import Path

from reasoning_agent.fesf_memory import SolveMemory
from reasoning_agent.fork_evidence_synthesize_finish import (
    ForkEvidenceSynthesizeFinishRelay,
    SkillRegistry,
    evaluate_exact_request,
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


def a_packet(choice="exact-evaluation", applicability="YES"):
    return (
        f"SKILL_CHOICE: {choice}\nAPPLICABILITY: {applicability}\n"
        "GOAL: 求唯一值\nANSWER_TYPE: 数值\nCONSTRAINTS: 有限定义域 | 等式\n"
        "STRUCTURE: 代数关系\nBOTTLENECK: 最后一步求值"
    )


def b_packet(secret="B_PRIVATE", candidate="3"):
    return (
        "BRANCH: B\nCLAIMS:\n"
        f"B1: 由原题关系得到候选 3；内部备注 {secret}\n"
        f"CANDIDATE_B: {candidate}\nOPEN: 检查代回"
    )


def c_packet(tool=True, secret="C_PRIVATE"):
    request = "EXACT_EVAL: claim_id=C1; expr=1+2; expected=3; scope=局部表达式" if tool else ""
    return (
        "BRANCH: C\nCLAIMS:\n"
        f"C1: 将目标化为表达式并得到 3；内部备注 {secret}\n"
        f"{request}\nCANDIDATE_C: 3\nOPEN: 检查作用域\n"
        "RAW_C_TEXT_SHOULD_NOT_TRAVEL"
    )


def d_packet(refuted="none"):
    return (
        "PRIMARY_BRANCH: B\nPRIMARY_REASON: B 覆盖全部约束，C 的局部事实可作辅助\n"
        "SUPPORTED_CLAIMS: C1 <- T1\nAUXILIARY_CLAIMS: C1\n"
        f"REFUTED_CLAIMS: {refuted}\nUNRESOLVED_CLAIMS: B1\n"
        "CANDIDATE_D: 3\nOPEN: 完成最终代回"
    )


def e_packet(answer="3"):
    return f"只保留必要结论。\nFINAL: {answer}"


class FESFRelayTest(unittest.TestCase):
    def solve(self, responses, *, exact=True, problem="求满足关系的唯一数值"):
        client = ScriptedClient(responses)
        result = ForkEvidenceSynthesizeFinishRelay(client, enable_exact_eval=exact).solve(problem, "calculation")
        return client, result

    def test_fixed_five_call_sequence_and_tokens(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), e_packet()])
        self.assertEqual([2048, 2048, 2048, 8192, 4096], [call[2] for call in client.calls])
        self.assertEqual("3", result.final_response)
        self.assertEqual(5, result.trace[-1]["model_calls"])

    def test_l0_is_one_call(self):
        client = ScriptedClient(["FINAL: 7"])
        result = ForkEvidenceSynthesizeFinishRelay(client).solve("计算 3+4", "calculation")
        self.assertEqual([4096], [call[2] for call in client.calls])
        self.assertEqual("7", result.final_response)

    def test_a_selects_one_skill_body_only_c_sees_body(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), e_packet()])
        b_user = client.calls[1][0][1]["content"]
        c_user = client.calls[2][0][1]["content"]
        e_user = client.calls[4][0][1]["content"]
        self.assertNotIn("Exact evaluation", b_user)
        self.assertIn("# Exact evaluation", c_user)
        self.assertIn("exact-evaluation", c_user)
        self.assertNotIn("RAW_C_TEXT_SHOULD_NOT_TRAVEL", e_user)
        self.assertTrue(result.trace[-1]["skill_loaded"])

    def test_none_or_invalid_skill_falls_back_without_tool(self):
        for choice, applicability in (("NONE", "NO"), ("not-registered", "YES")):
            with self.subTest(choice=choice):
                client, result = self.solve(
                    [a_packet(choice, applicability), b_packet(), c_packet(tool=True), d_packet(refuted="none"), e_packet()]
                )
                self.assertNotIn("# Exact evaluation", client.calls[2][0][1]["content"])
                self.assertFalse(any(event["stage"] == "tool_exact_eval" for event in result.trace))
                self.assertFalse(result.trace[-1]["skill_loaded"])

    def test_explicit_non_applicable_skill_is_normalized_to_none(self):
        client, result = self.solve(
            [a_packet("exact-evaluation", "NO"), b_packet(), c_packet(tool=True), d_packet(refuted="none"), e_packet()]
        )
        self.assertNotIn("# Exact evaluation", client.calls[2][0][1]["content"])
        self.assertFalse(any(event["stage"] == "tool_exact_eval" for event in result.trace))
        self.assertFalse(result.trace[-1]["skill_loaded"])

    def test_d_keeps_auxiliary_and_downgrades_unsupported_refutation(self):
        d = d_packet("B1 <- T999").replace("SUPPORTED_CLAIMS: C1 <- T1", "SUPPORTED_CLAIMS: none")
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d, e_packet()])
        e_user = client.calls[4][0][1]["content"]
        self.assertIn("AUXILIARY_CLAIMS: C1", e_user)
        self.assertIn("UNRESOLVED_CLAIMS: B1", e_user)
        self.assertNotIn("REFUTED_CLAIMS: B1", e_user)
        self.assertEqual("3", result.final_response)

    def test_d_requires_evidence_claim_binding(self):
        d = d_packet("none").replace(
            "SUPPORTED_CLAIMS: C1 <- T1", "SUPPORTED_CLAIMS: B1 <- T1"
        ).replace("AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none")
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d, e_packet()])
        e_user = client.calls[4][0][1]["content"]
        self.assertIn("UNRESOLVED_CLAIMS: B1, C1", e_user)
        self.assertNotIn("SUPPORTED_CLAIMS: B1", e_user)
        self.assertEqual("3", result.final_response)

    def test_d_conflicting_categories_fail_closed_to_unresolved(self):
        d = d_packet("C1 <- T2").replace("UNRESOLVED_CLAIMS: B1", "UNRESOLVED_CLAIMS: B1")
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d, e_packet()])
        e_user = client.calls[4][0][1]["content"]
        self.assertIn("UNRESOLVED_CLAIMS: B1, C1", e_user)
        self.assertNotIn("SUPPORTED_CLAIMS: C1", e_user)
        self.assertNotIn("REFUTED_CLAIMS: C1", e_user)
        self.assertEqual("3", result.final_response)

    def test_e_sees_only_primary_and_explicit_auxiliary_candidates(self):
        d = d_packet("none").replace("AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none")
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d, e_packet()])
        e_user = client.calls[4][0][1]["content"]
        self.assertIn("B: 3", e_user)
        self.assertNotIn("C: 3", e_user)
        self.assertEqual("3", result.final_response)

    def test_d_invalid_evidence_id_is_not_rendered(self):
        d = d_packet("B1 <- T999").replace(
            "SUPPORTED_CLAIMS: C1 <- T1", "SUPPORTED_CLAIMS: none"
        ).replace("AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none")
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d, e_packet()])
        e_user = client.calls[4][0][1]["content"]
        self.assertIn("UNRESOLVED_CLAIMS: B1, C1", e_user)
        self.assertNotIn("evidence=T999", e_user)
        self.assertEqual("3", result.final_response)

    def test_d_protocol_damage_is_fail_closed(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), "GARBAGE D", e_packet("1")])
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertTrue(any(
            event["stage"] == "synthesize" and event["status"] == "protocol_failed"
            for event in result.trace
        ))
        self.assertIn("D_PROTOCOL: INVALID", client.calls[4][0][1]["content"])

    def test_d_duplicate_or_illegal_marker_is_fail_closed(self):
        valid = d_packet("none")
        for malformed in (
            valid + "\nOPEN: duplicate",
            valid + "\nNOTE: extra field",
        ):
            with self.subTest(malformed=malformed[-32:]):
                client, result = self.solve([a_packet(), b_packet(), c_packet(), malformed, e_packet("1")])
                self.assertEqual("UNKNOWN", result.final_response)
                self.assertTrue(any(
                    event["stage"] == "synthesize" and event["status"] == "protocol_failed"
                    for event in result.trace
                ))

    def test_d_illegal_marker_diagnostic_is_redacted(self):
        malicious = d_packet("none") + "\nSECRET_MARKER_" + ("X" * 500) + ": leaked"
        client, result = self.solve([a_packet(), b_packet(), c_packet(), malicious, e_packet("1")])
        blob = json.dumps(result.as_dict(), ensure_ascii=False)
        self.assertNotIn("SECRET_MARKER_", blob)
        event = next(
            item for item in result.trace
            if item["stage"] == "synthesize" and item["status"] == "protocol_failed"
        )
        self.assertEqual("illegal_marker", event["protocol_error"])

    def test_e_conflicting_finals_fails_closed(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), "FINAL: 3\nFINAL: 4"])
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual("unknown", result.trace[-1]["status"])

    def test_e_cannot_create_answer_outside_host_candidate_set(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), e_packet("99")])
        self.assertEqual("UNKNOWN", result.final_response)
        gate = next(item for item in result.trace if item["stage"] == "candidate_gate")
        self.assertEqual("rejected", gate["status"])
        self.assertEqual("not_in_candidate_set", gate["candidate_gate"])
        self.assertGreaterEqual(gate["eligible_count"], 1)

    def test_refuted_candidate_is_not_rendered_or_accepted(self):
        memory = SolveMemory()
        self.assertTrue(memory.add_claim("B1", "x = 3", "B"))
        self.assertTrue(memory.add_evidence("T1", "exact-evaluation", "REFUTED", "value", "4", claim_id="B1"))
        self.assertTrue(memory.set_claim_status("B1", "REFUTED", ["T1"]))
        memory.set_synthesis(primary_branch="B", primary_reason="evidence", refuted=["B1"])
        self.assertTrue(memory.add_candidate("B", "3", ["B1"]))
        self.assertEqual([], memory.candidate_rows_for_e())
        self.assertNotIn("CANDIDATES:", memory.render_for_e())

    def test_e_withdrawal_or_truncated_final_fails_closed(self):
        for final in ("FINAL: 3\nFINAL: UNKNOWN.", "FINAL: 3\nFINAL: <answer>", "FINAL: x +"):
            with self.subTest(final=final):
                client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), final])
                self.assertEqual("UNKNOWN", result.final_response)

    def test_tool_evidence_must_bind_expression_and_result_to_claim(self):
        for text in ("C1: 1+2=4", "C1: 1+2=30", "C1: 1+2=3 and 1=2"):
            with self.subTest(text=text):
                c = c_packet().replace(
                    "C1: 将目标化为表达式并得到 3；内部备注 C_PRIVATE", text
                )
                d = d_packet().replace("AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none")
                client, result = self.solve([a_packet(), b_packet(), c, d, e_packet()])
                e_user = client.calls[4][0][1]["content"]
                self.assertIn("UNRESOLVED_CLAIMS: B1, C1", e_user)
                self.assertNotIn("SUPPORTED_CLAIMS: C1", e_user)
                self.assertEqual("3", result.final_response)

    def test_tool_event_exposes_bounded_binding_diagnostics(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), d_packet(), e_packet()])
        event = next(item for item in result.trace if item["stage"] == "tool_exact_eval")
        self.assertEqual("UNKNOWN", event["status"])
        self.assertEqual("rejected", event["execution_status"])
        self.assertTrue(event["claim_known"])
        self.assertFalse(event["binding_ok"])
        self.assertEqual("claim_binding", event["error"])

    def test_route_diagnostics_are_enum_bounded(self):
        secret = "SECRET_APPLICABILITY_" + "x" * 10_000
        analysis = a_packet().replace("APPLICABILITY: YES", f"APPLICABILITY: {secret}")
        client, result = self.solve([analysis, b_packet(), c_packet(tool=False), d_packet(), e_packet()])
        route = next(item for item in result.trace if item["stage"] == "route")
        self.assertEqual("unknown", route["applicability"])
        self.assertNotIn(secret, json.dumps(result.as_dict(), ensure_ascii=False))

    def test_noncanonical_claim_id_is_redacted_in_tool_trace(self):
        c = c_packet().replace("claim_id=C1", "claim_id=C_PRIVATE_SECRET")
        client, result = self.solve([a_packet(), b_packet(), c, d_packet(), e_packet()])
        event = next(item for item in result.trace if item["stage"] == "tool_exact_eval")
        self.assertEqual("UNKNOWN", event["claim_id"])
        self.assertNotIn("C_PRIVATE_SECRET", json.dumps(result.as_dict(), ensure_ascii=False))

    def test_canonical_tool_claim_is_accepted_and_consumable(self):
        c = c_packet().replace(
            "C1: 将目标化为表达式并得到 3；内部备注 C_PRIVATE",
            "C1: 1+2=3",
        )
        d = d_packet().replace("AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none")
        client, result = self.solve([a_packet(), b_packet(), c, d, e_packet()])
        event = next(item for item in result.trace if item["stage"] == "tool_exact_eval")
        self.assertEqual("EXACT", event["status"])
        self.assertEqual("ok", event["execution_status"])
        self.assertTrue(event["claim_known"])
        self.assertTrue(event["binding_ok"])
        self.assertEqual("none", event["error"])
        self.assertTrue(event["evidence_consumed"])
        self.assertIn("SUPPORTED_CLAIMS: C1", client.calls[4][0][1]["content"])

    def test_d_protocol_failure_keeps_bounded_parser_reason(self):
        client, result = self.solve([a_packet(), b_packet(), c_packet(), "GARBAGE D", e_packet("1")])
        event = next(
            item for item in result.trace
            if item["stage"] == "synthesize" and item["status"] == "protocol_failed"
        )
        self.assertIn("missing=", event["protocol_error"])

    def test_tool_evidence_domain_and_result_size_are_bounded(self):
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request("EXACT_EVAL: claim_id=C1; expr=0^(-1); scope=value")["status"],
        )
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                "EXACT_EVAL: claim_id=C1; expr=x/x; expected=1; scope=identity for all x"
            )["status"],
        )
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                "EXACT_EVAL: claim_id=C1; expr=x/x; expected=1; scope=x=0, y!=0"
            )["status"],
        )
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                "EXACT_EVAL: claim_id=C1; expr=x^(-1)*x; expected=1; scope=identity for all x"
            )["status"],
        )
        for scope in ("x != 0.5", "x = 0, yx != 0"):
            self.assertEqual(
                "UNKNOWN",
                evaluate_exact_request(
                    f"EXACT_EVAL: claim_id=C1; expr=x/x; expected=1; scope={scope}"
                )["status"],
            )
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                "EXACT_EVAL: claim_id=C1; expr=x^(1-2)*x; expected=1; scope=identity for all x"
            )["status"],
        )
        for expr in ("x^(-2/2)*x", "x^(a-a-1)*x"):
            self.assertEqual(
                "UNKNOWN",
                evaluate_exact_request(
                    f"EXACT_EVAL: claim_id=C1; expr={expr}; expected=1; scope=identity for all x"
                )["status"],
            )
        for scope in ("1+x != 0", "x != 0+1"):
            self.assertEqual(
                "UNKNOWN",
                evaluate_exact_request(
                    f"EXACT_EVAL: claim_id=C1; expr=x/x; expected=1; scope={scope}"
                )["status"],
            )
        self.assertEqual(
            "EXACT",
            evaluate_exact_request(
                "EXACT_EVAL: claim_id=C1; expr=x/x; expected=1; scope=x != 0"
            )["status"],
        )
        nested = "((((10^12)^12)^12)^12)"
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                f"EXACT_EVAL: claim_id=C1; expr={nested}; scope=bounded value"
            )["status"],
        )
        symbolic_nested = "(((1000000000000*x)^12)^12)^12"
        self.assertEqual(
            "UNKNOWN",
            evaluate_exact_request(
                f"EXACT_EVAL: claim_id=C1; expr={symbolic_nested}; scope=bounded symbolic value"
            )["status"],
        )

    def test_evidence_assumptions_are_visible_to_d_and_e(self):
        c = c_packet().replace(
            "C1: 将目标化为表达式并得到 3；内部备注 C_PRIVATE",
            "C1: x/x=1",
        ).replace(
            "expr=1+2; expected=3; scope=局部表达式",
            "expr=x/x; expected=1; scope=x != 0",
        )
        d = d_packet().replace("SUPPORTED_CLAIMS: C1 <- T1", "SUPPORTED_CLAIMS: C1 <- T1").replace(
            "AUXILIARY_CLAIMS: C1", "AUXILIARY_CLAIMS: none"
        )
        client, result = self.solve([a_packet(), b_packet(), c, d, e_packet()])
        self.assertIn("assumptions=restricted arithmetic and symbolic grammar, x != 0", client.calls[3][0][1]["content"])
        self.assertIn("assumptions=restricted arithmetic and symbolic grammar, x != 0", client.calls[4][0][1]["content"])

    def test_unknown_claim_tool_evidence_is_not_accepted(self):
        c = c_packet().replace("claim_id=C1", "claim_id=Z9")
        client, result = self.solve([a_packet(), b_packet(), c, d_packet(), e_packet()])
        tool_events = [event for event in result.trace if event["stage"] == "tool_exact_eval"]
        self.assertEqual(1, len(tool_events))
        self.assertEqual("UNKNOWN", tool_events[0]["claim_id"])
        self.assertEqual("UNKNOWN", tool_events[0]["status"])
        self.assertNotIn("Z9", client.calls[3][0][1]["content"])

    def test_soft_deadline_skips_remaining_model_calls(self):
        class Clock:
            def __init__(self):
                self.calls = 0

            def __call__(self):
                self.calls += 1
                return 901.0 if self.calls > 1 else 0.0

        clock = Clock()
        client = ScriptedClient([])
        result = ForkEvidenceSynthesizeFinishRelay(client, clock=clock).solve("证明一个非平凡命题", "proof")
        self.assertEqual("UNKNOWN", result.final_response)
        self.assertEqual(0, len(client.calls))
        self.assertTrue(any(event.get("error_category") == "soft_deadline" for event in result.trace))

    def test_trace_is_bounded_and_does_not_store_raw_text(self):
        client, result = self.solve([a_packet(), b_packet("SECRET_B"), c_packet(secret="SECRET_C"), d_packet(), e_packet()])
        blob = json.dumps(result.as_dict(), ensure_ascii=False)
        self.assertNotIn("SECRET_B", blob)
        self.assertNotIn("SECRET_C", blob)
        self.assertNotIn("RAW_C_TEXT_SHOULD_NOT_TRAVEL", blob)
        self.assertNotIn("你负责", blob)
        json.dumps(result.as_dict(), ensure_ascii=False)

    def test_memory_isolation_across_consecutive_and_parallel_solves(self):
        def one(value):
            client = ScriptedClient([a_packet("NONE", "NO"), b_packet(str(value), value), c_packet(False), d_packet(), e_packet(str(value))])
            return ForkEvidenceSynthesizeFinishRelay(client).solve(f"题目 {value}", "calculation")

        first, second = one("1"), one("2")
        self.assertNotEqual(first.final_response, second.final_response)
        outputs = [None, None, None]
        threads = [threading.Thread(target=lambda i=i: outputs.__setitem__(i, one(str(i)))) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(["0", "1", "2"], [item.final_response for item in outputs])


class ExactEvaluatorTest(unittest.TestCase):
    def test_exact_refuted_unknown(self):
        self.assertEqual("EXACT", evaluate_exact_request("EXACT_EVAL: claim_id=C1; expr=1+2; scope=value")["status"])
        self.assertEqual("REFUTED", evaluate_exact_request("EXACT_EVAL: claim_id=C1; expr=1+2; expected=4; scope=value")["status"])
        for request in (
            "EXACT_EVAL: claim_id=C1; expr=2^13; scope=value",
            "EXACT_EVAL: claim_id=C1; expr=sin(1); scope=value",
            "EXACT_EVAL: claim_id=C1; expr=x=1; scope=value",
            "EXACT_EVAL: claim_id=C1; expr=1/0; scope=value",
            "not a request",
        ):
            with self.subTest(request=request):
                self.assertEqual("UNKNOWN", evaluate_exact_request(request)["status"])

    def test_case_file_has_twelve_positive_and_negative_rows(self):
        path = Path(__file__).resolve().parents[1] / "reasoning_agent" / "fesf_skills" / "exact-evaluation" / "cases.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(sum(1 for row in rows if row["applicable"]), 12)
        self.assertGreaterEqual(sum(1 for row in rows if not row["applicable"]), 12)
        for row in rows:
            self.assertEqual(row["expected_status"], evaluate_exact_request(row["request"])["status"])


class SolveMemoryInvariantTest(unittest.TestCase):
    def test_evidence_api_rejects_unknown_claim_and_cross_claim_status(self):
        memory = SolveMemory()
        self.assertTrue(memory.add_claim("B1", "完整命题", "B"))
        self.assertTrue(memory.add_claim("C1", "另一个完整命题", "C"))
        self.assertFalse(memory.add_evidence("T0", "exact-evaluation", "EXACT", "局部", "1", (), "Z9"))
        self.assertTrue(memory.add_evidence("T1", "exact-evaluation", "EXACT", "B1 局部", "1", (), "B1"))
        self.assertFalse(memory.set_claim_status("C1", "SUPPORTED", ["T1"]))
        self.assertFalse(memory.set_claim_status("B1", "REFUTED", ["T1"]))
        self.assertTrue(memory.set_claim_status("B1", "SUPPORTED", ["T1"]))
        self.assertEqual(["T1"], memory.claims[0].evidence_ids)

    def test_set_synthesis_normalizes_overlapping_categories_and_omissions(self):
        memory = SolveMemory()
        memory.add_claim("B1", "命题一", "B")
        memory.add_claim("C1", "命题二", "C")
        memory.set_synthesis(
            primary_branch="B",
            primary_reason="覆盖约束",
            supported=["B1"],
            auxiliary=["B1"],
            refuted=[],
            unresolved=[],
        )
        self.assertEqual([], memory.supported_claim_ids)
        self.assertEqual([], memory.auxiliary_claim_ids)
        self.assertEqual(["B1", "C1"], memory.unresolved_claim_ids)


class SolveMemoryGuardTest(unittest.TestCase):
    def test_evidence_and_synthesis_guards_are_fail_closed(self):
        memory = SolveMemory()
        self.assertTrue(memory.add_claim("C1", "x = 3", "C"))
        self.assertFalse(memory.add_evidence("T1", "exact-evaluation", "EXACT", "", "3", claim_id="C1"))
        self.assertFalse(memory.add_evidence("T1", "exact-evaluation", "EXACT", "value", "3", claim_id="Z9"))
        self.assertTrue(memory.add_evidence("T1", "exact-evaluation", "EXACT", "value", "3", claim_id="C1"))
        self.assertFalse(memory.set_claim_status("C1", "SUPPORTED", ["T999"]))
        self.assertEqual("PROPOSED", memory.claims[0].status)
        memory.set_synthesis(
            primary_branch="C",
            primary_reason="evidence",
            supported=["C1"],
            refuted=["C1"],
        )
        self.assertEqual([], memory.supported_claim_ids)
        self.assertEqual([], memory.refuted_claim_ids)
        self.assertEqual(["C1"], memory.unresolved_claim_ids)

class FESFIntegrationConfigTest(unittest.TestCase):
    def test_default_submission_is_rollback_fsdf_and_fesf_off(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)
        self.assertTrue(SUBMISSION_CONFIG.enable_fesf_v1)
        self.assertTrue(SUBMISSION_CONFIG.enable_fesf_exact_eval)
        for name in (
            "enable_fsdf_diagnostics_v2", "enable_fsdf_multiline_handoff_v2",
            "enable_fsdf_final_confirmation_v2", "enable_fsdf_finish_prompt_v2",
            "enable_fsdf_handoff_first_d", "enable_fsdf_d_result_to_e",
        ):
            self.assertFalse(getattr(SUBMISSION_CONFIG, name))

    def test_fesf_exact_eval_requires_fesf_path(self):
        class BareClient:
            def chat(self, **kwargs):
                return "FINAL: 1"

        with self.assertRaises(ValueError):
            ReasoningAgent(BareClient(), AgentConfig(enable_fesf_exact_eval=True)).solve("求 x", {})

    def test_fesf_path_is_opt_in_and_caps_external_values(self):
        config = AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=True, max_model_calls=99, max_tokens=99999)
        client = ScriptedClient([a_packet(), b_packet(), c_packet(), d_packet(), e_packet()])
        result = ReasoningAgent(client, config).solve("求满足关系的唯一数值", {})
        self.assertEqual(5, len(client.calls))
        self.assertEqual([2048, 2048, 2048, 8192, 4096], [call[2] for call in client.calls])
        self.assertEqual("3", result["final_response"])
        json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
