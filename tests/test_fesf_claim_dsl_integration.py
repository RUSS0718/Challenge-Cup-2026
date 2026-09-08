import ast
import json
import threading
import unittest
from pathlib import Path

from reasoning_agent.fork_evidence_synthesize_finish import ForkEvidenceSynthesizeFinishRelay
from tests.test_fesf import ScriptedClient, a_packet, b_packet, d_packet, e_packet
from user_agent import AgentConfig, ReasoningAgent, SUBMISSION_CONFIG


IDENTITY_CLAIM = (
    '{"v":1,"kind":"claim","id":"C1","type":"relation","left":"(x+1)*(x-1)",'
    '"relation":"==","right":"x**2-1","assumptions":[],"scope":"symbolic_identity","branch":"C"}'
)
IDENTITY_VERIFY = '{"v":1,"kind":"verify","id":"T1","claim_id":"C1","adapter":"symbolic-constraint","branch":"C"}'
DOMAIN_CLAIM = (
    '{"v":1,"kind":"claim","id":"C2","type":"relation","left":"1/x","relation":"==",'
    '"right":"1/x","assumptions":[],"scope":"symbolic_identity","branch":"C"}'
)
COUNTER_CLAIM = (
    '{"v":1,"kind":"claim","id":"K1","type":"counterexample_search","scope":"counterexample_search",'
    '"variable":"x","predicate":"x*x >= 0","values":["-1","0","1"],"branch":"C"}'
)


def c_dsl_packet(claim=IDENTITY_CLAIM, verify=IDENTITY_VERIFY, extra=""):
    return (
        "BRANCH: C\nCLAIMS:\n"
        "C1: (x+1)*(x-1)==x**2-1\n"
        f"CLAIM_DSL: {claim}\n"
        f"VERIFY_DSL: {verify}\n"
        f"{extra}"
        "CANDIDATE_C: 3\nOPEN: 无"
    )


def d_supported():
    return (
        "PRIMARY_BRANCH: B\nPRIMARY_REASON: B 覆盖约束\n"
        "SUPPORTED_CLAIMS: C1 <- T1\nAUXILIARY_CLAIMS: none\n"
        "REFUTED_CLAIMS: none\nUNRESOLVED_CLAIMS: B1\n"
        "CANDIDATE_D: 3\nOPEN: 完成"
    )


def packets(c_text=None, d_text=None):
    return [a_packet("NONE", "NO"), b_packet(), c_text or c_dsl_packet(), d_text or d_supported(), e_packet()]


class ClaimDslIntegrationTest(unittest.TestCase):
    def test_submission_profile_disables_claim_dsl_without_top_level_import(self):
        self.assertFalse(SUBMISSION_CONFIG.enable_fesf_claim_dsl)
        self.assertFalse(AgentConfig().enable_fesf_claim_dsl)
        source = Path(__file__).resolve().parents[1] / "user_agent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        top_imports = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("reasoning_agent.fesf_verifiers.claim"):
                top_imports.append(node.module)
            if isinstance(node, ast.Import):
                top_imports.extend(alias.name for alias in node.names if "claim_dsl" in alias.name or "claim_executor" in alias.name)
        self.assertEqual([], top_imports)
        relay = Path(__file__).resolve().parents[1] / "reasoning_agent" / "fork_evidence_synthesize_finish.py"
        relay_text = relay.read_text(encoding="utf-8")
        self.assertNotIn("fesf_verifiers.claim_dsl", relay_text)
        self.assertNotIn("fesf_verifiers.claim_executor", relay_text)

    def test_disabled_switch_matches_baseline_budget_and_answer(self):
        problem = "求满足关系的唯一数值"
        baseline = ScriptedClient(packets())
        disabled = ScriptedClient(packets())
        ReasoningAgent(baseline, AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False)).solve(problem, {})
        result = ReasoningAgent(
            disabled,
            AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=False),
        ).solve(problem, {"gold": "secret"})
        self.assertEqual([call[2] for call in baseline.calls], [call[2] for call in disabled.calls])
        self.assertEqual([2048, 2048, 2048, 8192, 4096], [call[2] for call in disabled.calls])
        self.assertEqual("3", result["final_response"])
        self.assertFalse(any(item.get("stage") == "tool_claim_dsl" for item in result["trace"]))
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("CLAIM_DSL", disabled.calls[2][0][1]["content"])

    def test_legal_claim_is_bound_and_consumable(self):
        client = ScriptedClient(packets())
        result = ReasoningAgent(
            client,
            AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=True),
        ).solve("求满足关系的唯一数值", {})
        event = next(item for item in result["trace"] if item.get("stage") == "tool_claim_dsl" and item.get("evidence_id") == "T1")
        self.assertEqual("EXACT", event["status"])
        self.assertTrue(event["binding_ok"])
        self.assertIn("SUPPORTED_CLAIMS: C1", client.calls[4][0][1]["content"])
        self.assertEqual(5, len(client.calls))
        self.assertEqual("3", result["final_response"])
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("(x+1)*(x-1)", blob)

    def test_unknown_rewrite_cross_branch_and_missing_evidence_fail_closed(self):
        cases = [
            c_dsl_packet(verify='{"v":1,"kind":"verify","id":"T1","claim_id":"Z9","adapter":"symbolic-constraint","branch":"C"}'),
            c_dsl_packet(verify='{"v":1,"kind":"verify","id":"T1","claim_id":"C1","adapter":"symbolic-constraint","left":"1","right":"2","relation":"=="}'),
            c_dsl_packet(verify='{"v":1,"kind":"verify","id":"T1","claim_id":"C1","adapter":"symbolic-constraint","branch":"B"}'),
        ]
        for packet in cases:
            with self.subTest(packet=packet[-40:]):
                client = ScriptedClient(packets(c_text=packet, d_text=d_supported()))
                result = ReasoningAgent(
                    client,
                    AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=True),
                ).solve("求满足关系的唯一数值", {})
                self.assertNotIn("SUPPORTED_CLAIMS: C1", client.calls[4][0][1]["content"])
                self.assertIn("UNRESOLVED_CLAIMS: B1, C1", client.calls[4][0][1]["content"])
                json.dumps(result, ensure_ascii=False)

    def test_unknown_never_upgrades(self):
        packet = (
            "BRANCH: C\nCLAIMS:\nC2: 1/x==1/x\n"
            f"CLAIM_DSL: {DOMAIN_CLAIM}\n"
            'VERIFY_DSL: {"v":1,"kind":"verify","id":"T2","claim_id":"C2","adapter":"symbolic-constraint","branch":"C"}\n'
            "CANDIDATE_C: 3\nOPEN: 无"
        )
        d = (
            "PRIMARY_BRANCH: B\nPRIMARY_REASON: B 覆盖约束\n"
            "SUPPORTED_CLAIMS: C2 <- T2\nAUXILIARY_CLAIMS: none\n"
            "REFUTED_CLAIMS: none\nUNRESOLVED_CLAIMS: B1\n"
            "CANDIDATE_D: 3\nOPEN: 完成"
        )
        client = ScriptedClient(packets(c_text=packet, d_text=d))
        ReasoningAgent(
            client,
            AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=True),
        ).solve("求满足关系的唯一数值", {})
        self.assertNotIn("SUPPORTED_CLAIMS: C2", client.calls[4][0][1]["content"])
        self.assertIn("UNRESOLVED_CLAIMS: B1, C2", client.calls[4][0][1]["content"])

    def test_counterexample_absence_is_unknown(self):
        packet = (
            "BRANCH: C\nCLAIMS:\nK1: x*x>=0\n"
            f"CLAIM_DSL: {COUNTER_CLAIM}\n"
            'VERIFY_DSL: {"v":1,"kind":"verify","id":"T5","claim_id":"K1","adapter":"counterexample","branch":"C"}\n'
            "CANDIDATE_C: 3\nOPEN: 无"
        )
        client = ScriptedClient(packets(c_text=packet))
        result = ReasoningAgent(
            client,
            AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=True),
        ).solve("求满足关系的唯一数值", {})
        event = next(item for item in result["trace"] if item.get("stage") == "tool_claim_dsl" and item.get("evidence_id") == "T5")
        self.assertEqual("UNKNOWN", event["status"])

    def test_consecutive_and_parallel_solves_do_not_share_evidence(self):
        def one(value):
            client = ScriptedClient(packets())
            agent = ReasoningAgent(
                client,
                AgentConfig(enable_fesf_v1=True, enable_fesf_exact_eval=False, enable_fesf_claim_dsl=True),
            )
            return agent.solve(f"题目 {value}", {})

        first, second = one("1"), one("2")
        self.assertEqual("3", first["final_response"])
        self.assertEqual("3", second["final_response"])
        outputs = [None, None, None]
        threads = [threading.Thread(target=lambda i=i: outputs.__setitem__(i, one(str(i)))) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(["3", "3", "3"], [item["final_response"] for item in outputs])


if __name__ == "__main__":
    unittest.main()
