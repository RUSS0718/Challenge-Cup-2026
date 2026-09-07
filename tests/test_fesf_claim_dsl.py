import ast
import json
import unittest
from pathlib import Path

from reasoning_agent.fesf_verifiers.claim_dsl import (
    ClaimDslError,
    ClaimLedger,
    bind_verify,
    execute_verify,
    parse_claim,
    parse_verify,
)
from user_agent import AgentConfig, SUBMISSION_CONFIG


def claim_payload(**overrides):
    payload = {
        "v": 1,
        "kind": "claim",
        "id": "C1",
        "type": "relation",
        "left": "(x+1)*(x-1)",
        "relation": "==",
        "right": "x**2-1",
        "assumptions": [],
        "scope": "symbolic_identity",
        "branch": "C",
    }
    payload.update(overrides)
    return payload


def verify_payload(**overrides):
    payload = {"v": 1, "kind": "verify", "id": "T1", "claim_id": "C1", "adapter": "symbolic-constraint", "branch": "C"}
    payload.update(overrides)
    return payload


class ClaimDslParserTest(unittest.TestCase):
    def test_legal_claim_round_trip(self):
        claim = parse_claim(json.dumps(claim_payload(), separators=(",", ":")))
        self.assertEqual("C1", claim.id)
        self.assertEqual("symbolic_identity", claim.scope)

    def test_duplicate_and_missing_and_unknown_fields_fail_closed(self):
        ledger = ClaimLedger()
        ledger.add_claim(parse_claim(claim_payload()))
        with self.assertRaisesRegex(ClaimDslError, "duplicate_id"):
            ledger.add_claim(parse_claim(claim_payload()))
        missing = claim_payload()
        missing.pop("scope")
        with self.assertRaisesRegex(ClaimDslError, "missing_field"):
            parse_claim(missing)
        with self.assertRaisesRegex(ClaimDslError, "unknown_field"):
            parse_claim(claim_payload(extra="no"))

    def test_illegal_scope_id_adapter_and_nested_json_fail_closed(self):
        with self.assertRaisesRegex(ClaimDslError, "scope_invalid"):
            parse_claim(claim_payload(scope="whole_problem"))
        with self.assertRaisesRegex(ClaimDslError, "scope_invalid"):
            parse_claim(claim_payload(scope="answer_verified"))
        with self.assertRaisesRegex(ClaimDslError, "id_invalid"):
            parse_claim(claim_payload(id="bad id"))
        with self.assertRaisesRegex(ClaimDslError, "adapter_invalid"):
            parse_verify(verify_payload(adapter="python-eval"))
        pretty = json.dumps(claim_payload(), indent=2)
        with self.assertRaisesRegex(ClaimDslError, "multiline_object"):
            parse_claim(pretty)
        with self.assertRaisesRegex(ClaimDslError, "expression_invalid"):
            parse_claim(claim_payload(left="x" * 300))
        with self.assertRaisesRegex(ClaimDslError, "forbidden_field"):
            parse_claim(claim_payload(gold="17"))

    def test_forged_evidence_object_is_rejected(self):
        with self.assertRaisesRegex(ClaimDslError, "kind_invalid"):
            parse_claim({"v": 1, "kind": "evidence", "id": "T9", "type": "relation", "scope": "symbolic_identity"})


class ClaimDslBindingTest(unittest.TestCase):
    def test_verify_must_reference_same_branch_claim(self):
        ledger = ClaimLedger()
        ledger.add_claim(parse_claim(claim_payload()))
        with self.assertRaisesRegex(ClaimDslError, "unknown_claim"):
            bind_verify(parse_verify(verify_payload(claim_id="Z9")), ledger)
        with self.assertRaisesRegex(ClaimDslError, "cross_branch"):
            bind_verify(parse_verify(verify_payload(branch="B")), ledger)
        with self.assertRaisesRegex(ClaimDslError, "verify_rewrites_claim"):
            parse_verify(verify_payload(left="1", right="2", relation="=="))

    def test_unknown_evidence_and_scope_mismatch_stay_unresolved(self):
        ledger = ClaimLedger()
        ledger.add_claim(parse_claim(claim_payload()))
        self.assertEqual("UNRESOLVED", ledger.bind_synthesis("C1", "T999"))
        with self.assertRaisesRegex(ClaimDslError, "scope_mismatch"):
            parse_claim(claim_payload(scope="finite_predicate"))

    def test_unknown_status_never_upgrades(self):
        ledger = ClaimLedger()
        ledger.add_claim(
            parse_claim(
                claim_payload(left="1/x", right="1/x", assumptions=[], id="C2")
            )
        )
        evidence = execute_verify(parse_verify(verify_payload(claim_id="C2", id="T2")), ledger)
        self.assertEqual("UNKNOWN", evidence.status)
        self.assertEqual("UNRESOLVED", ledger.bind_synthesis("C2", "T2"))


class ClaimDslAdapterTest(unittest.TestCase):
    def test_symbolic_exact_refuted_unknown(self):
        ledger = ClaimLedger()
        ledger.add_claim(parse_claim(claim_payload()))
        exact = execute_verify(parse_verify(verify_payload()), ledger)
        self.assertEqual("EXACT", exact.status)
        self.assertEqual("SUPPORTED", ledger.bind_synthesis("C1", "T1"))

        refuted_ledger = ClaimLedger()
        refuted_ledger.add_claim(parse_claim(claim_payload(id="C3", left="x+1", right="x+2")))
        refuted = execute_verify(parse_verify(verify_payload(id="T3", claim_id="C3")), refuted_ledger)
        self.assertEqual("REFUTED", refuted.status)
        self.assertEqual("REFUTED", refuted_ledger.bind_synthesis("C3", "T3"))

    def test_finite_and_counterexample_semantics(self):
        finite = parse_claim(
            {
                "v": 1,
                "kind": "claim",
                "id": "F1",
                "type": "finite_predicate",
                "scope": "finite_predicate",
                "variable": "x",
                "predicate": "x % 2 == 0",
                "values": ["0", "2", "4"],
                "branch": "C",
            }
        )
        ledger = ClaimLedger()
        ledger.add_claim(finite)
        evidence = execute_verify(
            parse_verify({"v": 1, "kind": "verify", "id": "T4", "claim_id": "F1", "adapter": "finite-domain", "branch": "C"}),
            ledger,
        )
        self.assertEqual("EXACT", evidence.status)

        search = parse_claim(
            {
                "v": 1,
                "kind": "claim",
                "id": "K1",
                "type": "counterexample_search",
                "scope": "counterexample_search",
                "variable": "x",
                "predicate": "x * x >= 0",
                "values": ["-1", "0", "1"],
                "branch": "C",
            }
        )
        other = ClaimLedger()
        other.add_claim(search)
        none = execute_verify(
            parse_verify({"v": 1, "kind": "verify", "id": "T5", "claim_id": "K1", "adapter": "counterexample", "branch": "C"}),
            other,
        )
        self.assertEqual("UNKNOWN", none.status)
        self.assertNotEqual("EXACT", none.status)


class ClaimDslSecurityAndDefaultOffTest(unittest.TestCase):
    def test_unsafe_syntax_stays_unknown_and_trace_is_bounded(self):
        ledger = ClaimLedger()
        ledger.add_claim(parse_claim(claim_payload(id="C9", left="__import__('os')", right="1")))
        evidence = execute_verify(parse_verify(verify_payload(id="T9", claim_id="C9")), ledger)
        self.assertEqual("UNKNOWN", evidence.status)
        blob = json.dumps(evidence.as_dict(), ensure_ascii=False)
        self.assertNotIn("__import__", blob)

    def test_submission_config_enables_claim_dsl_without_top_level_import(self):
        self.assertTrue(SUBMISSION_CONFIG.enable_fesf_claim_dsl)
        self.assertFalse(getattr(AgentConfig(), "enable_fesf_claim_dsl", False))
        source = Path(__file__).resolve().parents[1] / "user_agent.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("reasoning_agent.fesf_verifiers.claim_dsl"):
                imported.append(node.module)
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names if "claim_dsl" in alias.name)
        self.assertEqual([], imported)
        relay = Path(__file__).resolve().parents[1] / "reasoning_agent" / "fork_evidence_synthesize_finish.py"
        relay_tree = ast.parse(relay.read_text(encoding="utf-8"))
        relay_imports = []
        for node in ast.walk(relay_tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("reasoning_agent.fesf_verifiers.claim"):
                relay_imports.append(node.module)
            if isinstance(node, ast.ImportFrom) and node.module in {"fesf_verifiers.claim_dsl", "fesf_verifiers.claim_executor"}:
                relay_imports.append(node.module)
        self.assertEqual([], relay_imports)


if __name__ == "__main__":
    unittest.main()
