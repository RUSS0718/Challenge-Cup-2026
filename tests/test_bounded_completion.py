import json
from pathlib import Path
import threading
import time
import unittest

from reasoning_agent.bounded_completion import (
    ArtifactStore,
    BoundaryPolicy,
    BoundedCompletionObserver,
    BoundedProbeRunner,
    FAILURE_BUDGET_REFUSAL,
    FAILURE_TIMEOUT,
    ProbeArm,
    ProbeConfig,
    ProbeItem,
    assess_formation,
    build_probe_plan,
    replay_formations,
    sha256_text,
)
from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig
from user_agent import AgentConfig, ReasoningAgent


class ScriptedClient:
    def __init__(self, response="Final answer: 4"):
        self.response = response
        self.calls = []

    def chat(self, messages, temperature, max_tokens):
        self.calls.append((messages, temperature, max_tokens))
        return self.response


def make_config(
    *,
    arms=(ProbeArm("A", 32, "ordinary free-form response"),),
    boundary=None,
    bank_mode="off",
    planned_items=2,
):
    return ProbeConfig(
        run_id="BCOMP-TEST-001",
        method_id="bounded_completion_foundations_v1",
        code_sha256=sha256_text("code"),
        protocol_sha256=sha256_text("protocol"),
        model_id="test-model",
        endpoint_id="test-endpoint",
        dataset_path="sample_data/test.jsonl",
        dataset_sha256=sha256_text("dataset"),
        seed=7,
        prompt_id="bcomp-test-prompt-v1",
        system_prompt="Solve the problem in ordinary free-form prose.",
        user_prompt_prefix="Problem:\n",
        parser_version="host_parser_v1",
        scorer_version="host_only_test_scorer_v1",
        actual_route="model",
        bank_mode=bank_mode,
        boundary=boundary or BoundaryPolicy(
            per_item_seconds=1.0,
            window_seconds=5.0,
            call_wait_seconds=0.2,
            finalization_allowance_seconds=0.1,
            max_workers=2,
            max_calls_per_item=len(arms),
            max_requested_tokens_per_item=128,
        ),
        arms=arms,
        planned_items=planned_items,
        stop_rules={
            "void_on_incomplete_records": True,
            "void_on_unstable_endpoint": True,
            "first_three_formed_zero": True,
            "max_model_error_rate": 0.2,
        },
    )


class BoundedCompletionInfrastructureTest(unittest.TestCase):
    def test_preregistration_rejects_bank_and_missing_stop_rules(self):
        config = make_config(bank_mode="on")
        with self.assertRaisesRegex(ValueError, "bank_must_be_off"):
            config.validate()
        config = make_config()
        object.__setattr__(config, "stop_rules", {})
        with self.assertRaisesRegex(ValueError, "stop_rules_incomplete"):
            config.validate()

    def test_plan_rotates_first_arm(self):
        arms = (ProbeArm("A", 32, "scope A"), ProbeArm("B", 32, "scope B"))
        config = make_config(arms=arms)
        plan = build_probe_plan(
            config,
            [ProbeItem("i1", "Compute 1+1"), ProbeItem("i2", "Compute 2+2")],
        )
        self.assertEqual(["A", "B", "B", "A"], [task.arm_id for task in plan])
        self.assertEqual(["i1:A", "i1:B", "i2:B", "i2:A"], [task.task_id for task in plan])

    def test_admission_reserves_finalization_time_for_item_and_window(self):
        boundary = BoundaryPolicy(
            per_item_seconds=1.0,
            window_seconds=2.0,
            call_wait_seconds=0.2,
            finalization_allowance_seconds=0.1,
            max_workers=1,
            max_calls_per_item=1,
            max_requested_tokens_per_item=128,
        )
        self.assertEqual(
            "deadline_refusal",
            boundary.admit(
                item_elapsed_seconds=0.8,
                window_elapsed_seconds=0.0,
                calls_used=0,
                requested_tokens=0,
                requested_this_call=32,
            )[1],
        )
        self.assertEqual(
            "deadline_refusal",
            boundary.admit(
                item_elapsed_seconds=0.0,
                window_elapsed_seconds=1.8,
                calls_used=0,
                requested_tokens=0,
                requested_this_call=32,
            )[1],
        )

    def test_observer_persists_call_lifecycle_but_not_trace(self):
        root = Path(self.id().replace(".", "_") + "-artifacts")
        try:
            store = ArtifactStore(root)
            observer = BoundedCompletionObserver(store, run_id="run-1")
            client = ScriptedClient("答案是 7\nSECRET_RESPONSE")
            harness = ConstraintFitOrchestrator(
                client,
                config=HarnessConfig(max_model_calls=1, total_token_budget=4096),
                call_observer=observer,
                observation_context={"item_id": "item-1", "arm_id": "direct"},
            )
            result = harness.solve("计算 3+4")
            self.assertEqual("7", result["final_response"])
            self.assertNotIn("SECRET_RESPONSE", json.dumps(result, ensure_ascii=False))
            events = store.read("events")
            self.assertEqual(["start", "terminal"], [event["event_type"] for event in events])
            self.assertIn("run-1:item-1:direct:1:1", events[0]["event_id"])
            artifacts = store.read("artifacts")
            self.assertEqual("SECRET_RESPONSE", artifacts[0]["response"].splitlines()[-1])
            self.assertEqual("complete_candidate", store.read("assessments")[0]["formation_status"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_budget_refusal_is_observed_without_a_model_call(self):
        root = Path(self.id().replace(".", "_") + "-budget")
        try:
            store = ArtifactStore(root)
            observer = BoundedCompletionObserver(store, run_id="run-budget")
            client = ScriptedClient()
            result = ConstraintFitOrchestrator(
                client,
                config=HarnessConfig(max_model_calls=1, total_token_budget=1024),
                call_observer=observer,
                observation_context={"item_id": "item-1", "arm_id": "direct"},
            ).solve("计算 3+4")
            self.assertEqual("UNKNOWN", result["final_response"])
            self.assertEqual([], client.calls)
            refusal = store.read("events")[0]
            self.assertEqual("refusal", refusal["event_type"])
            self.assertEqual(FAILURE_BUDGET_REFUSAL, refusal["error_category"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_replay_creates_derived_assessment_without_overwriting_source(self):
        root = Path(self.id().replace(".", "_") + "-replay")
        try:
            store = ArtifactStore(root)
            observer = BoundedCompletionObserver(store, run_id="run-replay")
            handle = observer.start_call(
                stage="probe",
                requested_tokens=32,
                attempt=1,
                context={"item_id": "item-1", "arm_id": "A", "problem": "Compute 2+2"},
            )
            observer.finish_call(handle, response="答案是 4", finish_reason=None)
            before = store.read("artifacts")[0]
            replayed = replay_formations(store)
            after = store.read("artifacts")[0]
            self.assertEqual(before, after)
            self.assertEqual("complete_candidate", replayed[0]["formation_status"])
            self.assertEqual("model", replayed[0]["support_source"])
            self.assertEqual("none", replayed[0]["recovery_source"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_append_recovers_a_partial_tail_without_losing_complete_events(self):
        root = Path(self.id().replace(".", "_") + "-partial")
        try:
            store = ArtifactStore(root)
            store.append_event({"event_id": "complete-1", "status": "started"})
            with (root / "events.jsonl").open("ab") as handle:
                handle.write(b'{"event_id":"partial"')
            store.append_event({"event_id": "complete-2", "status": "finished"})
            self.assertEqual(
                ["complete-1", "complete-2"],
                [event["event_id"] for event in store.read("events")],
            )
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_runner_dry_run_has_planned_and_skipped_counts_and_zero_calls(self):
        root = Path(self.id().replace(".", "_") + "-dry")
        try:
            calls = []
            runner = BoundedProbeRunner(make_config(), output_dir=root)
            report = runner.run(
                [ProbeItem("i1", "Compute 1+1"), ProbeItem("i2", "Compute 2+2")],
                client_factory=lambda: calls.append("factory"),
                dry_run=True,
            )
            self.assertTrue(report["zero_model_calls"])
            self.assertEqual(2, report["planned_requests"])
            self.assertEqual(0, report["dispatched_requests"])
            self.assertEqual(2, report["skipped_requests"])
            self.assertEqual([], calls)
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_runner_uses_public_client_shape_and_keeps_missing_usage_unknown(self):
        root = Path(self.id().replace(".", "_") + "-live")
        try:
            clients = []

            def factory():
                client = ScriptedClient({
                    "content": "Final answer: 4",
                    "finish_reason": "stop",
                    "usage": {"completion_tokens": 4},
                })
                clients.append(client)
                return client

            report = BoundedProbeRunner(make_config(), output_dir=root).run(
                [ProbeItem("i1", "Compute 2+2"), ProbeItem("i2", "Compute 2+2")],
                client_factory=factory,
                allow_real_model_calls=True,
            )
            self.assertEqual(2, report["dispatched_requests"])
            self.assertEqual(2, report["completed_requests"])
            self.assertEqual(8, report["actual_completion_tokens"])
            self.assertEqual(2, report["formation_status_counts"]["complete_candidate"])
            self.assertEqual(2, sum(len(client.calls) for client in clients))
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_blocking_call_stops_dispatch_and_keeps_remote_cancel_unknown(self):
        root = Path(self.id().replace(".", "_") + "-blocking")
        release = threading.Event()
        try:
            config = make_config(
                boundary=BoundaryPolicy(
                    per_item_seconds=0.05,
                    window_seconds=2.0,
                    call_wait_seconds=0.02,
                    finalization_allowance_seconds=0.01,
                    max_workers=1,
                    max_calls_per_item=1,
                    max_requested_tokens_per_item=128,
                )
            )

            class BlockingClient:
                def chat(self, messages, temperature, max_tokens):
                    release.wait(2.0)
                    return "Final answer: 4"

            started = time.perf_counter()
            report = BoundedProbeRunner(config, output_dir=root).run(
                [ProbeItem("i1", "Compute 2+2"), ProbeItem("i2", "Compute 2+2")],
                client_factory=BlockingClient,
                allow_real_model_calls=True,
            )
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 1.3)
            self.assertEqual(1, report["timed_out_requests"])
            self.assertEqual(1, report["skipped_requests"])
            self.assertEqual(1, report["failure_category_counts"][FAILURE_TIMEOUT])
            row = next(row for row in json.loads("[" + ",".join(
                line for line in (root / "answers.jsonl").read_text(encoding="utf-8").splitlines()
            ) + "]") if row["timed_out"])
            self.assertEqual("unknown", row["remote_cancellation"])
        finally:
            release.set()
            time.sleep(0.1)
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_completed_a_then_blocked_b_stops_before_dispatching_c(self):
        root = Path(self.id().replace(".", "_") + "-a-b-c")
        release = threading.Event()
        calls = []
        try:
            config = make_config(
                planned_items=3,
                boundary=BoundaryPolicy(
                    per_item_seconds=0.7,
                    window_seconds=2.0,
                    call_wait_seconds=0.5,
                    finalization_allowance_seconds=0.1,
                    max_workers=1,
                    max_calls_per_item=1,
                    max_requested_tokens_per_item=128,
                ),
            )

            class AThenBlockingClient:
                def chat(self, messages, temperature, max_tokens):
                    calls.append(messages[1]["content"])
                    if len(calls) == 1:
                        return "Final answer: 4"
                    release.wait(2.0)
                    return "Final answer: 5"

            report = BoundedProbeRunner(config, output_dir=root).run(
                [
                    ProbeItem("i1", "Compute 2+2"),
                    ProbeItem("i2", "Compute 2+3"),
                    ProbeItem("i3", "Compute 2+4"),
                ],
                client_factory=AThenBlockingClient,
                allow_real_model_calls=True,
            )
            self.assertEqual(1, report["completed_requests"])
            self.assertEqual(1, report["timed_out_requests"])
            self.assertEqual(1, report["skipped_requests"])
            self.assertEqual(2, len(calls))
            self.assertLessEqual(report["max_active_workers_observed"], 3)
        finally:
            release.set()
            time.sleep(0.1)
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_first_three_formed_zero_gate_stops_a_live_probe(self):
        root = Path(self.id().replace(".", "_") + "-formation-gate")
        calls = []
        try:
            config = make_config(
                planned_items=4,
                boundary=BoundaryPolicy(
                    per_item_seconds=0.3,
                    window_seconds=2.0,
                    call_wait_seconds=0.2,
                    finalization_allowance_seconds=0.05,
                    max_workers=1,
                    max_calls_per_item=1,
                    max_requested_tokens_per_item=128,
                ),
            )

            class NoFormationClient:
                def chat(self, messages, temperature, max_tokens):
                    calls.append(messages[1]["content"])
                    return "The derivation is unfinished."

            report = BoundedProbeRunner(config, output_dir=root).run(
                [
                    ProbeItem("i1", "Compute 2+2"),
                    ProbeItem("i2", "Compute 2+3"),
                    ProbeItem("i3", "Compute 2+4"),
                    ProbeItem("i4", "Compute 2+5"),
                ],
                client_factory=NoFormationClient,
                allow_real_model_calls=True,
            )
            self.assertTrue(report["first_three_formation_gate"]["triggered"])
            self.assertEqual("first_three_formed_zero", report["stop_reason"])
            self.assertEqual(3, report["dispatched_requests"])
            self.assertEqual(1, report["skipped_requests"])
            self.assertEqual(3, len(calls))
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_runner_restart_skips_durable_completed_task_without_retry(self):
        root = Path(self.id().replace(".", "_") + "-resume")
        try:
            config = make_config()
            items = [ProbeItem("i1", "Compute 2+2"), ProbeItem("i2", "Compute 2+2")]
            first = BoundedProbeRunner(config, output_dir=root).run(
                items,
                client_factory=ScriptedClient,
                allow_real_model_calls=True,
            )
            self.assertEqual(2, first["completed_requests"])

            def unexpected_factory():
                raise AssertionError("completed tasks must not be retried")

            second = BoundedProbeRunner(config, output_dir=root).run(
                items,
                client_factory=unexpected_factory,
                allow_real_model_calls=True,
            )
            self.assertEqual(2, second["resumed_completed"])
            self.assertEqual(2, second["dispatched_requests"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_persistence_failure_stops_followup_dispatch(self):
        root = Path(self.id().replace(".", "_") + "-persist-failure")
        try:
            config = make_config()
            store = ArtifactStore(root, max_response_chars=5)
            observer = BoundedCompletionObserver(store, run_id="persist-failure")
            calls = []

            class Client:
                def chat(self, messages, temperature, max_tokens):
                    calls.append(1)
                    return "Final answer: 4"

            report = BoundedProbeRunner(config, output_dir=root, observer=observer).run(
                [ProbeItem("i1", "Compute 2+2"), ProbeItem("i2", "Compute 2+2")],
                client_factory=Client,
                allow_real_model_calls=True,
            )
            self.assertEqual(1, len(calls))
            self.assertTrue(report["void"])
            self.assertIn("artifact_persistence_failure", report["void_reasons"])
            self.assertEqual(1, report["skipped_requests"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_reasoning_agent_observer_is_explicitly_default_off(self):
        self.assertFalse(AgentConfig().enable_bounded_completion_observation)
        client = ScriptedClient("答案是 4")
        result = ReasoningAgent(
            client,
            AgentConfig(enable_constraint_fit_harness=True),
        ).solve("计算 2+2", {"idx": 1})
        self.assertEqual("4", result["final_response"])

    def test_reasoning_agent_can_opt_in_to_the_same_observer_seam(self):
        root = Path(self.id().replace(".", "_") + "-agent")
        try:
            store = ArtifactStore(root)
            observer = BoundedCompletionObserver(store, run_id="agent-run")
            result = ReasoningAgent(
                ScriptedClient("答案是 4\nPRIVATE_RESPONSE"),
                AgentConfig(
                    enable_constraint_fit_harness=True,
                    enable_bounded_completion_observation=True,
                ),
                bounded_completion_observer=observer,
            ).solve("计算 2+2", {"idx": 9, "answer": "must_not_be_copied"})
            self.assertEqual("4", result["final_response"])
            self.assertNotIn("PRIVATE_RESPONSE", json.dumps(result, ensure_ascii=False))
            artifact = store.read("artifacts")[0]
            self.assertNotIn("must_not_be_copied", json.dumps(artifact, ensure_ascii=False))
            self.assertEqual("9", artifact["item_id"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()

    def test_assess_formation_does_not_turn_truncation_into_complete(self):
        assessment = assess_formation("Compute 2+2", "Final answer: 4", "length")
        self.assertFalse(assessment["complete_candidate"])
        self.assertTrue(assessment["candidate_formed"])

    def test_report_keeps_missing_usage_and_finish_metadata_unknown(self):
        root = Path(self.id().replace(".", "_") + "-unknown-usage")
        try:
            report = BoundedProbeRunner(make_config(), output_dir=root).run(
                [ProbeItem("i1", "Compute 2+2"), ProbeItem("i2", "Compute 2+2")],
                client_factory=lambda: ScriptedClient("Final answer: 4"),
                allow_real_model_calls=True,
            )
            self.assertEqual(64, report["requested_tokens"])
            self.assertIsNone(report["actual_completion_tokens"])
            self.assertEqual({"missing": 2}, report["finish_reason_counts"])
        finally:
            for path in root.glob("*") if root.exists() else []:
                path.unlink()
            if root.exists():
                root.rmdir()


if __name__ == "__main__":
    unittest.main()
