import json
import unittest

from reasoning_agent.fesf_verifiers import (
    CounterexampleAdapter,
    FiniteDomainAdapter,
    FiniteVerifierConfig,
    SymbolicConstraintAdapter,
    SymbolicVerifierConfig,
)


class SymbolicAdapterTest(unittest.TestCase):
    def setUp(self):
        self.adapter = SymbolicConstraintAdapter()

    def test_equivalence_and_refutation(self):
        self.assertEqual("EXACT", self.adapter.check_equivalence("(x+1)*(x-1)", "x^2-1", "C1").status)
        self.assertEqual("REFUTED", self.adapter.check_equivalence("x+1", "x+2", "C2").status)

    def test_relation_and_domain_are_conservative(self):
        self.assertEqual("EXACT", self.adapter.check_relation("x+1", ">=", "x", claim_id="C3").status)
        self.assertEqual("UNKNOWN", self.adapter.check_equivalence("1/x", "1/x", "C4").status)
        self.assertEqual(
            "EXACT",
            self.adapter.check_equivalence("1/x", "1/x", "C5", assumptions=["x != 0"]).status,
        )
        self.assertEqual(
            "UNKNOWN",
            self.adapter.check_equivalence("(x-1)/(x-1)", "1", "C6", assumptions=["x != 0"]).status,
        )
        self.assertEqual(
            "UNKNOWN",
            self.adapter.check_equivalence("1/(x-1)", "1/(x-1)", "C7", assumptions=["x != 0"]).status,
        )
        self.assertEqual("UNKNOWN", self.adapter.check_equivalence("x**(0-1)", "x**(0-1)", "C8").status)
        self.assertEqual(
            "EXACT",
            self.adapter.check_equivalence("x**(0-1)", "x**(0-1)", "C9", assumptions=["x != 0"]).status,
        )

    def test_unsafe_syntax_and_post_operation_timeout_fail_closed(self):
        self.assertEqual("UNKNOWN", self.adapter.check_equivalence("__import__('os')", "1").status)
        timed = SymbolicConstraintAdapter(SymbolicVerifierConfig(soft_timeout_seconds=-1.0))
        self.assertEqual("UNKNOWN", timed.check_equivalence("1", "1").status)


class FiniteAndCounterexampleAdapterTest(unittest.TestCase):
    def setUp(self):
        self.finite = FiniteDomainAdapter()
        self.counterexample = CounterexampleAdapter()

    def test_finite_predicate_is_exact_only_on_explicit_domain(self):
        result = self.finite.check_all("x", "x % 2 == 0", [0, 2, 4], claim_id="F1")
        self.assertEqual("EXACT", result.status)
        self.assertIn("checked=3", result.result)
        self.assertEqual("REFUTED", self.finite.check_all("x", "x % 2 == 0", [0, 1], claim_id="F2").status)
        self.assertEqual("x=1", self.finite.check_all("x", "x % 2 == 0", [0, 1], claim_id="F2").witness)

    def test_invalid_or_unbounded_domain_is_unknown(self):
        self.assertEqual("UNKNOWN", self.finite.check_all("x", "x == 0", [], claim_id="F3").status)
        limited = FiniteDomainAdapter(FiniteVerifierConfig(max_values=2))
        self.assertEqual("UNKNOWN", limited.check_all("x", "x == 0", [0, 1, 2]).status)
        self.assertEqual("UNKNOWN", self.finite.check_all("x", "__import__('os')", [0]).status)

    def test_counterexample_adapter_never_proves_universal_claim(self):
        no_witness = self.counterexample.find("x", "x*x >= 0", [-2, -1, 0, 1, 2], claim_id="K1")
        self.assertEqual("UNKNOWN", no_witness.status)
        self.assertIn("not a universal proof", no_witness.assumptions[0])
        witness = self.counterexample.find("x", "x != 0", [0, 1], claim_id="K2")
        self.assertEqual("REFUTED", witness.status)
        self.assertEqual("x=0", witness.witness)

    def test_results_are_json_serializable_and_ids_are_bounded(self):
        result = self.finite.check_all("x", "x == 1", [1], claim_id="F4")
        json.dumps(result.as_dict(), ensure_ascii=False)
        self.assertEqual("F4", result.claim_id)
        self.assertEqual("", self.finite.check_all("x", "x == 1", [1], claim_id="bad id").claim_id)


class FrozenVerifierContractTest(unittest.TestCase):
    def test_symbolic_finite_and_counterexample_oracles(self):
        from tests.support.host_loop_foundations import (
            evaluate_counterexample_case,
            evaluate_finite_case,
            evaluate_symbolic_case,
        )
        from tests.support.host_loop_foundations_cases import (
            COUNTEREXAMPLE_CASES,
            FINITE_CASES,
            SYMBOLIC_CASES,
        )

        self.assertGreaterEqual(len(SYMBOLIC_CASES), 30)
        self.assertGreaterEqual(len(FINITE_CASES), 30)
        self.assertGreaterEqual(len(COUNTEREXAMPLE_CASES), 30)
        families = (
            (SYMBOLIC_CASES, evaluate_symbolic_case),
            (FINITE_CASES, evaluate_finite_case),
            (COUNTEREXAMPLE_CASES, evaluate_counterexample_case),
        )
        failures = []
        for cases, evaluator in families:
            for case in cases:
                result = evaluator(case)
                if not result.get("ok") or result.get("gate") == "EXACT":
                    failures.append(result)
        self.assertEqual([], failures)

    def test_grammar_bounded_fuzz_is_fail_closed_and_deterministic(self):
        from tests.support.host_loop_foundations import evaluate_fuzz_case, generate_fuzz_cases

        cases = generate_fuzz_cases(300)
        self.assertEqual(300, len(cases))
        failures = []
        for case in cases:
            result = evaluate_fuzz_case(case)
            if not result.get("ok") or (case["adapter"] == "counterexample" and result.get("status") == "EXACT"):
                failures.append(result)
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
