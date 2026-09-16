import json
import hashlib
from pathlib import Path
import tempfile
import threading
import time
import unittest
from fractions import Fraction

from reasoning_agent.migration_hardening import (
    DeterministicPlayoff,
    EvidenceAdapter,
    EvidenceRecord,
    HardeningBudget,
    HardeningLedger,
    LogicalAssetRegistry,
    PLAYOFF_A,
    PLAYOFF_B,
    PLAYOFF_BOTH,
    PLAYOFF_INCONCLUSIVE,
    PLAYOFF_NEITHER,
    PrefillAdapter,
    ProcessAuditParser,
    adapt_evidence,
    EVIDENCE_CONTRADICT,
    EVIDENCE_INCONCLUSIVE,
    EVIDENCE_SUPPORT,
    STATE_ATTEMPT,
    STATE_CANDIDATE,
    STATE_SELECTED,
    STATE_START,
    STATE_FINALIZED,
)
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class Client:
    def __init__(self, response="answer"):
        self.response = response
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        return self.response


class PrefillClient(Client):
    def __init__(self, response, *, mode="continue"):
        super().__init__(response)
        self.mode = mode

    def chat(self, messages, temperature, max_tokens, **kwargs):
        self.calls.append((messages, temperature, max_tokens, kwargs))
        if self.mode == "type_error":
            if kwargs:
                raise TypeError("prefill unsupported")
            return self.response
        if self.mode == "ignore":
            return "ignored" if kwargs else "ordinary"
        if self.mode == "echo":
            return kwargs["prefill"] if kwargs else "ordinary"
        return kwargs["prefill"] + self.response


class FakeClock:
    def __init__(self, value=0.0):
        self.value = float(value)

    def __call__(self):
        return self.value


class ExplodingPrefillClient(Client):
    def chat(self, messages, temperature, max_tokens, **kwargs):
        self.calls.append((messages, temperature, max_tokens, kwargs))
        if kwargs:
            raise RuntimeError("PRIVATE_RESPONSE")
        return "ordinary"


class MigrationHardeningTest(unittest.TestCase):
    def test_budget_is_bounded_and_records_refusal(self):
        budget = HardeningBudget(max_calls=99, total_tokens=100)
        reservation = budget.reserve("attempt", 60)
        self.assertIsNotNone(reservation)
        budget.finish(reservation, completion_tokens=4, finish_reason="stop", duration_ms=12)
        self.assertIsNone(budget.reserve("retry", 41))
        self.assertEqual(1, budget.summary()["calls"])
        self.assertEqual("token_budget_exhausted", budget.summary()["refusals"][0]["reason"])
        json.dumps(budget.summary())

    def test_budget_checks_calls_tokens_and_absolute_deadline_together(self):
        clock = FakeClock(10)
        budget = HardeningBudget(
            max_logical_calls=2,
            max_requested_tokens=30,
            wall_deadline=15,
            clock=clock,
        )
        reservation = budget.admit("attempt", 20)
        self.assertIsNotNone(reservation)
        self.assertEqual(1, budget.remaining()["logical_calls"])
        self.assertEqual(10, budget.remaining()["requested_tokens"])
        clock.value = 12
        record = budget.finish(reservation, actual_tokens=7, error="timeout")
        self.assertEqual(20, record["requested_tokens"])
        self.assertEqual(7, record["actual_tokens"])
        self.assertEqual("timeout", record["finish"])
        self.assertEqual(2.0, record["duration"])
        self.assertEqual("timeout", record["error"])
        self.assertIsNone(budget.admit("too_many_tokens", 11))
        self.assertIn("token_budget_exhausted", budget.summary()["refusals"][-1]["reason"])
        clock.value = 15
        self.assertIsNone(budget.admit("past_deadline", 1))
        self.assertIn("wall_clock_exhausted", budget.summary()["refusals"][-1]["reason"])
        self.assertEqual(1, len(budget.summary()["records"]))
        json.dumps(budget.summary())

    def test_budget_keeps_failed_call_in_denominator_and_rejects_duplicate_finish(self):
        clock = FakeClock()
        budget = HardeningBudget(max_calls=1, total_tokens=8, max_wall_seconds=10, clock=clock)
        reservation = budget.admit(8)
        self.assertIsNotNone(reservation)
        clock.value = 11
        budget.finish(reservation, actual_tokens=None, error_category="client_error")
        self.assertEqual(1, budget.summary()["calls"])
        self.assertEqual("client_error", budget.summary()["records"][0]["error"])
        with self.assertRaisesRegex(ValueError, "unknown_reservation"):
            budget.finish(reservation)
        self.assertIsNone(budget.admit(1))
        self.assertIn("call_budget_exhausted", budget.summary()["refusals"][-1]["reason"])

    def test_ledger_accepts_only_finite_states_and_hides_raw_fields(self):
        ledger = HardeningLedger()
        ledger.transition(STATE_START)
        ledger.transition(STATE_ATTEMPT, reason="first attempt")
        ledger.add_candidate("A", "7", source="attempt_a", extraction_status="parsed")
        ledger.transition(STATE_CANDIDATE)
        ledger.add_call({"stage": "attempt", "prompt": "SECRET", "response": "PRIVATE", "status": "ok"})
        ledger.add_conflict(["A", {"candidate_id": "B", "value": "8"}], summary="different candidates")
        ledger.add_audit_hint("check arithmetic")
        ledger.add_evidence(EvidenceRecord("A", EVIDENCE_INCONCLUSIVE, "finite", "not applicable"))
        ledger.transition(STATE_SELECTED)
        ledger.transition(STATE_FINALIZED)
        trace = ledger.trace()
        serialized = json.dumps(trace, ensure_ascii=False)
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("PRIVATE", serialized)
        self.assertEqual((("A", "B"),), ledger.conflict_sides)
        self.assertEqual("A", trace["candidates"][0]["candidate_id"])
        self.assertEqual("not applicable", trace["evidence"][0]["summary"])
        with self.assertRaises(ValueError):
            ledger.transition("invented_state")
        with self.assertRaisesRegex(ValueError, "invalid_state_transition"):
            HardeningLedger().transition("repair")

    def test_trace_redacts_sensitive_compatibility_fields(self):
        ledger = HardeningLedger()
        ledger.add_call(
            {
                "stage": "PRIVATE_RESPONSE",
                "status": "PRIVATE_RESPONSE",
                "finish_reason": "PRIVATE_RESPONSE",
                "error_category": "PRIVATE_RESPONSE",
            }
        )
        self.assertNotIn("PRIVATE_RESPONSE", json.dumps(ledger.trace()))

    def test_ledgers_are_solve_local(self):
        first = HardeningLedger()
        second = HardeningLedger()
        first.add_candidate("A", "1", source="first", extraction_status="parsed")
        first.transition(STATE_CANDIDATE)
        self.assertEqual([], second.candidates)
        self.assertEqual(STATE_START, second.state)
        first.add_audit_hint("first-only")
        self.assertEqual([], second.audit_hints)

    def test_evidence_does_not_upgrade_execution_success(self):
        self.assertEqual(
            "inconclusive",
            EvidenceAdapter(lambda _: {"execution_status": "ok", "result": True}).evaluate("A").status,
        )
        supported = EvidenceAdapter(
            lambda _: {"status": "support", "evidence": "finite equality checked", "deterministic": True}
        ).evaluate("A")
        self.assertEqual("support", supported.status)
        self.assertEqual("inconclusive", EvidenceAdapter().evaluate("A").status)
        with self.assertRaises(ValueError):
            EvidenceRecord("A", "truth", "test")
        bound = EvidenceAdapter(
            lambda _: EvidenceRecord("B", "support", "trusted", "wrong candidate")
        ).evaluate("A")
        self.assertEqual("inconclusive", bound.status)
        self.assertEqual("candidate_mismatch", bound.error)

    def test_evidence_accepts_only_explicit_attributable_three_states(self):
        self.assertEqual(
            EVIDENCE_INCONCLUSIVE,
            adapt_evidence(
                {"status": EVIDENCE_SUPPORT, "summary": "checked"}
            ).status,
        )
        supported = adapt_evidence(
            {"status": EVIDENCE_SUPPORT, "provider": "finite-check", "summary": "equal", "deterministic": True},
            candidate_id="A",
        )
        contradicted = adapt_evidence(
            {"status": EVIDENCE_CONTRADICT, "source": "finite-check", "summary": "counterexample", "trusted": True},
            candidate_id="B",
        )
        self.assertEqual(EVIDENCE_SUPPORT, supported.status)
        self.assertEqual(EVIDENCE_CONTRADICT, contradicted.status)
        self.assertEqual(
            EVIDENCE_INCONCLUSIVE,
            adapt_evidence({"status": EVIDENCE_SUPPORT, "source": "model", "summary": "looks right"}).status,
        )
        self.assertEqual(
            EVIDENCE_INCONCLUSIVE,
            adapt_evidence({"status": "exact", "source": "wrong-alias"}).status,
        )
        self.assertEqual(
            EVIDENCE_INCONCLUSIVE,
            adapt_evidence({"status": "not_applicable", "source": "finite"}).status,
        )
        failed = EvidenceAdapter(lambda _: (_ for _ in ()).throw(TimeoutError("PRIVATE_RESPONSE"))).evaluate("A")
        self.assertEqual(EVIDENCE_INCONCLUSIVE, failed.status)
        self.assertEqual("timeout", failed.error)
        json.dumps(supported.as_dict())

    def test_playoff_selects_existing_candidate_and_runs_once(self):
        candidates = [
            {"candidate_id": "A", "value": "4", "normalized_value": "4"},
            {"candidate_id": "B", "value": "5", "normalized_value": "5"},
        ]

        def checker(candidate):
            return {"status": "support" if candidate["value"] == "4" else "contradict", "evidence": "bounded check"}

        playoff = DeterministicPlayoff(checker)
        result = playoff.run(candidates)
        self.assertEqual(PLAYOFF_A, result.decision)
        self.assertEqual(("A", "B"), result.candidate_ids)
        self.assertEqual(PLAYOFF_INCONCLUSIVE, playoff.run(candidates).decision)

    def test_playoff_never_invents_third_answer(self):
        candidates = [
            {"candidate_id": "A", "value": "x+1"},
            {"candidate_id": "B", "value": "x+2"},
        ]
        result = DeterministicPlayoff(lambda _: {"status": "support", "evidence": "ignored"}).run(candidates)
        self.assertEqual(PLAYOFF_INCONCLUSIVE, result.decision)
        self.assertEqual(("A", "B"), result.candidate_ids)
        same = DeterministicPlayoff().run(
            [{"candidate_id": "A", "value": "1"}, {"candidate_id": "B", "value": "1"}]
        )
        self.assertEqual(PLAYOFF_BOTH, same.decision)
        same_set = DeterministicPlayoff().run(
            [{"candidate_id": "A", "value": "{1, 2}"}, {"candidate_id": "B", "value": "{2,1}"}]
        )
        self.assertEqual(PLAYOFF_BOTH, same_set.decision)

    def test_playoff_covers_both_neither_and_inconclusive_without_new_candidate(self):
        candidates = [
            {"candidate_id": "A", "value": Fraction(1, 2)},
            {"candidate_id": "B", "value": "3/4"},
        ]

        def checker_for(statuses):
            def checker(candidate):
                return {
                    "status": statuses[candidate["candidate_id"]],
                    "source": "finite-check",
                    "summary": "bounded result",
                }

            return checker

        self.assertEqual(
            PLAYOFF_B,
            DeterministicPlayoff(
                checker_for({"A": EVIDENCE_CONTRADICT, "B": EVIDENCE_SUPPORT})
            ).run(candidates).decision,
        )
        self.assertEqual(
            PLAYOFF_BOTH,
            DeterministicPlayoff(
                checker_for({"A": EVIDENCE_SUPPORT, "B": EVIDENCE_SUPPORT})
            ).run(candidates).decision,
        )
        self.assertEqual(
            PLAYOFF_NEITHER,
            DeterministicPlayoff(
                checker_for({"A": EVIDENCE_CONTRADICT, "B": EVIDENCE_CONTRADICT})
            ).run(candidates).decision,
        )
        self.assertEqual(
            PLAYOFF_INCONCLUSIVE,
            DeterministicPlayoff(
                checker_for({"A": EVIDENCE_INCONCLUSIVE, "B": EVIDENCE_SUPPORT})
            ).run(candidates).decision,
        )
        self.assertEqual(
            PLAYOFF_INCONCLUSIVE,
            DeterministicPlayoff().run(
                candidates + [{"candidate_id": "C", "value": "1"}]
            ).decision,
        )

    def test_playoff_normalizes_numeric_and_choice_sets_but_never_runs_expression(self):
        self.assertEqual(
            PLAYOFF_BOTH,
            DeterministicPlayoff().run(
                [{"candidate_id": "A", "value": "0.50"}, {"candidate_id": "B", "value": "1/2"}]
            ).decision,
        )
        self.assertEqual(
            PLAYOFF_BOTH,
            DeterministicPlayoff().run(
                [{"candidate_id": "A", "value": [1, "2"]}, {"candidate_id": "B", "value": {"type": "set", "items": ["2", 1]}}]
            ).decision,
        )
        calls = []
        result = DeterministicPlayoff(lambda candidate: calls.append(candidate)).run(
            [
                {"candidate_id": "A", "value": "__import__('os').system('bad')"},
                {"candidate_id": "B", "value": "2"},
            ]
        )
        self.assertEqual(PLAYOFF_INCONCLUSIVE, result.decision)
        self.assertEqual([], calls)

    def test_prefill_supports_continue_echo_ignore_and_type_error_fallback(self):
        messages = [{"role": "user", "content": "select"}]
        for mode, expected in (("continue", "continued"), ("echo", "echoed"), ("ignore", "ignored")):
            client = PrefillClient(" body", mode=mode)
            result = PrefillAdapter().call(client, messages, 0.0, 32, prefill="SELECT: ", purpose="selection")
            self.assertEqual({"continue": "continuation", "echo": "echo_fallback", "ignore": "ignored_fallback"}[mode], result.status)
            self.assertEqual(1, result.logical_calls)
            self.assertEqual(1 if mode == "continue" else 2, result.physical_calls)
        client = PrefillClient("ordinary", mode="type_error")
        result = PrefillAdapter().call(client, messages, 0.0, 32, prefill="SELECT: ", purpose="selection")
        self.assertEqual("type_error_fallback", result.status)
        self.assertTrue(result.fallback)
        self.assertEqual(2, len(client.calls))
        self.assertEqual(2, result.physical_calls)

    def test_prefill_is_not_used_for_high_entropy_purpose(self):
        client = Client("ordinary")
        result = PrefillAdapter().call(
            client, [{"role": "user", "content": "solve"}], 0.0, 32,
            prefill="ANSWER: ", purpose="solve",
        )
        self.assertEqual("not_applicable", result.status)
        self.assertFalse(result.attempted)
        self.assertEqual(0, len(client.calls))

    def test_prefill_exception_also_falls_back_without_extra_logical_call(self):
        client = ExplodingPrefillClient("ordinary")
        result = PrefillAdapter().call(
            client,
            [{"role": "user", "content": "select"}],
            0.0,
            32,
            prefill="SELECT: ",
            purpose="selection",
        )
        self.assertEqual("exception_fallback", result.status)
        self.assertTrue(result.fallback)
        self.assertFalse(result.used)
        self.assertEqual(1, result.logical_calls)
        self.assertEqual(2, len(client.calls))
        json.dumps(result.as_dict())

    def test_process_audit_returns_hints_without_answer(self):
        parsed = ProcessAuditParser().parse("AUDIT: REPAIR\nHINT: check the boundary")
        self.assertEqual("repair", parsed.status)
        self.assertEqual(("check the boundary",), parsed.hints)
        malformed = ProcessAuditParser().parse("REPAIR: 999")
        self.assertEqual("inconclusive", malformed.status)
        self.assertNotIn("999", json.dumps(parsed.as_dict()))

    def test_assets_use_logical_ids_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "routes.txt").write_text("route", encoding="utf-8")
            registry = LogicalAssetRegistry(root, {"math.route": "routes.txt"})
            asset = registry.load("math.route")
            self.assertTrue(asset.available)
            self.assertTrue(asset.enabled)
            self.assertEqual("enabled", asset.status)
            self.assertEqual("route", asset.content)
            self.assertEqual(
                hashlib.sha256(b"route").hexdigest(),
                asset.sha256,
            )
            missing = registry.load("missing")
            self.assertEqual("unavailable", missing.status)
            self.assertFalse(missing.enabled)
            with self.assertRaises(ValueError):
                registry.register("escape", "../outside")
            with self.assertRaises(ValueError):
                registry.register("absolute", "C:\\secret.txt")
            with self.assertRaises(ValueError):
                registry.register("absolute_posix", "/secret.txt")
            (root / "bad.bin").write_bytes(b"\xff")
            registry.register("bad", "bad.bin")
            bad = registry.load("bad")
            self.assertEqual("asset_encoding_error", bad.reason)
            self.assertFalse(bad.enabled)
            (root / "directory").mkdir()
            registry.register("directory", "directory")
            self.assertEqual("asset_read_error", registry.load("directory").reason)
            json.dumps(asset.as_dict())


class HarnessIntegrationTest(unittest.TestCase):
    @staticmethod
    def _hardening_trace(result):
        return next(item for item in result["trace"] if item.get("stage") == "migration_hardening_ledger")

    def test_migration_hardening_is_default_off(self):
        result = ConstraintFitOrchestrator(Client("最终答案：7")).solve("计算 3+4")
        self.assertFalse(any(item.get("stage") == "migration_hardening_ledger" for item in result["trace"]))

    def test_deterministic_playoff_selects_only_an_existing_candidate(self):
        client = Client()
        client.response = ["最终答案：8", "最终答案：9"]

        def chat(messages, temperature, max_tokens):
            client.calls.append((messages, temperature, max_tokens))
            return client.response.pop(0)

        client.chat = chat
        config = HarnessConfig(
            early_stop=False,
            max_model_calls=2,
            total_token_budget=8192,
            enable_migration_hardening=True,
            enable_deterministic_playoff=True,
        )
        harness = ConstraintFitOrchestrator(
            client,
            config=config,
            playoff_checker=lambda candidate: {
                "status": "support" if candidate["value"] == "9" else "contradict",
                "evidence": "finite host check",
                "deterministic": True,
            },
        )
        result = harness.solve("计算 3+4")
        self.assertEqual("9", result["final_response"])
        self.assertEqual(2, len(client.calls))
        hardening = self._hardening_trace(result)
        self.assertEqual("B", hardening["playoffs"][0]["decision"])
        finalize = next(item for item in result["trace"] if item.get("stage") == "finalize")
        self.assertEqual("deterministic_playoff", finalize["source"])
        self.assertNotIn("critic", [call["stage"] for call in hardening["calls"]])

    def test_process_audit_can_request_one_repair_without_replacing_original(self):
        client = Client()
        client.response = ["最终答案：7", "AUDIT: REPAIR\nHINT: check arithmetic", "最终答案：8"]

        def chat(messages, temperature, max_tokens):
            client.calls.append((messages, temperature, max_tokens))
            return client.response.pop(0)

        client.chat = chat
        config = HarnessConfig(
            enable_migration_hardening=True,
            enable_process_audit=True,
            max_model_calls=3,
            total_token_budget=10240,
        )
        result = ConstraintFitOrchestrator(client, config=config).solve("计算 3+4")
        self.assertEqual("8", result["final_response"])
        self.assertEqual(3, len(client.calls))
        hardening = self._hardening_trace(result)
        self.assertEqual("check arithmetic", hardening["audit_hints"][0])
        self.assertEqual(2, len(hardening["candidates"]))
        self.assertIn("repair", [event["state"] for event in hardening["states"]])

    def test_prefill_type_error_falls_back_with_one_logical_call(self):
        client = Client()
        client.response = ["最终答案：8", "最终答案：9", "SELECT: B"]

        def chat(messages, temperature, max_tokens, **kwargs):
            client.calls.append((messages, temperature, max_tokens, kwargs))
            if kwargs:
                raise TypeError("prefill unsupported")
            return client.response.pop(0)

        client.chat = chat
        config = HarnessConfig(
            early_stop=False,
            max_model_calls=3,
            total_token_budget=10240,
            enable_migration_hardening=True,
            enable_prefill=True,
        )
        result = ConstraintFitOrchestrator(client, config=config).solve("计算 3+4")
        self.assertEqual("9", result["final_response"])
        hardening = self._hardening_trace(result)
        critic = next(call for call in hardening["calls"] if call["stage"] == "critic")
        self.assertEqual("type_error_fallback", critic["prefill_status"])
        self.assertTrue(critic["prefill_fallback"])
        self.assertEqual(2, critic["physical_calls"])

    def test_same_orchestrator_serializes_solve_local_state(self):
        class SerialClient:
            def __init__(self):
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()

            def chat(self, messages, temperature, max_tokens):
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.01)
                with self.lock:
                    self.active -= 1
                return "最终答案：7"

        client = SerialClient()
        harness = ConstraintFitOrchestrator(
            client,
            config=HarnessConfig(max_model_calls=1, total_token_budget=4096, enable_migration_hardening=True),
        )
        results = []
        threads = [threading.Thread(target=lambda: results.append(harness.solve("计算 3+4"))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, client.max_active)
        self.assertEqual(["7", "7"], sorted(result["final_response"] for result in results))
        self.assertEqual(1, self._hardening_trace(results[0])["budget"]["calls"])


if __name__ == "__main__":
    unittest.main()
