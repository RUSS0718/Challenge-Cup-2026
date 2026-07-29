import unittest

from scripts.evaluate_dev import evaluate


class CapturingAgent:
    def __init__(self):
        self.calls = []

    def solve(self, problem, metadata):
        self.calls.append((problem, metadata))
        return {
            "final_response": "42",
            "trace": [{"step": "finalize", "status": "selected", "model_calls": 2}],
        }


class PartiallyFailingAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "trace": [
                {
                    "step": "generate_candidate",
                    "status": "skipped",
                    "candidate_id": 1,
                    "reason": "empty_model_response",
                },
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class ObservableAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "trace": [
                {"step": "generate_candidate", "status": "rejected", "reason": "answer_not_extractable"},
                {"step": "controlled_tool", "status": "SUCCESS", "claim_status": "SUPPORTED"},
                {"step": "audit_answer_group", "status": "pass"},
                {"step": "route_budget", "level": "L2"},
                {"step": "repair_candidate", "status": "ok", "trigger": "uncertain_without_pass"},
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class RoutedAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "trace": [
                {"step": "route_budget", "status": "selected", "reason": "answer_conflict"},
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class EmptyFinalResponseAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "",
            "trace": [{"step": "finalize", "status": "selected", "model_calls": 1}],
        }


class EvaluateDevelopmentSetTest(unittest.TestCase):
    def test_answer_is_used_only_for_local_scoring(self):
        agent = CapturingAgent()
        report = evaluate(
            agent,
            [{"idx": 4, "problem": "What is the answer?", "answer": "42"}],
        )

        self.assertEqual(1.0, report["accuracy"])
        self.assertEqual([("What is the answer?", {"idx": 4})], agent.calls)
        self.assertEqual(0, report["timeout_count"])
        self.assertEqual([], report["failed_item_ids"])

    def test_total_timeout_skips_remaining_items(self):
        agent = CapturingAgent()
        report = evaluate(agent, [{"idx": 1, "problem": "a", "answer": "42"}], total_timeout_seconds=0)
        self.assertEqual([], agent.calls)
        self.assertEqual([1], report["failed_item_ids"])

    def test_report_tracks_empty_final_response_separately(self):
        report = evaluate(
            EmptyFinalResponseAgent(),
            [{"idx": 2, "problem": "a", "answer": "42"}],
        )
        self.assertEqual(1, report["empty_final_response_count"])
        self.assertEqual(0, report["empty_response_count"])

    def test_partial_candidate_failure_does_not_fail_successful_solution(self):
        report = evaluate(
            PartiallyFailingAgent(),
            [{"idx": 7, "problem": "a", "answer": "42"}],
        )

        self.assertEqual([], report["failed_item_ids"])
        self.assertTrue(report["records"][0]["empty_response"])

    def test_report_includes_experiment_and_truncation_observability(self):
        report = evaluate(ObservableAgent(), [{"idx": 8, "problem": "a", "answer": "42"}])

        self.assertEqual(1, report["answer_not_extractable_count"])
        self.assertEqual(1.0, report["answer_not_extractable_rate"])
        self.assertEqual(1, report["controlled_tool_call_count"])
        self.assertEqual(1, report["controlled_tool_supported_count"])
        self.assertEqual(0, report["controlled_tool_refuted_count"])
        self.assertEqual(1, report["grouped_audit_call_count"])
        self.assertEqual(1, report["repair_attempt_count"])
        self.assertEqual(1, report["l2_escalation_count"])
        self.assertEqual(1, report["uncertain_repair_attempt_count"])

    def test_normal_route_reason_is_not_reported_as_a_failure(self):
        report = evaluate(RoutedAgent(), [{"idx": 9, "problem": "a", "answer": "42"}])

        self.assertEqual([], report["records"][0]["failure_reasons"])

    def test_p0_2_1_candidate_extraction_counts(self):
        report = evaluate(ObservableAgent(), [{"idx": 8, "problem": "a", "answer": "42"}])

        record = report["records"][0]
        self.assertEqual(0, record["candidates_generated"])   # only rejected, no "ok"
        self.assertEqual(1, record["candidates_rejected"])
        self.assertTrue(record["all_candidates_rejected"])
        self.assertEqual(0, report["candidates_generated_total"])
        self.assertEqual(1, report["candidates_rejected_total"])
        self.assertEqual(1, report["items_with_all_candidates_rejected_count"])
        self.assertEqual([8], report["all_candidates_rejected_ids"])


class AgentWithMixedCandidates:
    """Two candidates: first accepted, second rejected."""
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "trace": [
                {"step": "generate_candidate", "status": "ok", "candidate_id": 0},
                {"step": "generate_candidate", "status": "rejected", "candidate_id": 1, "reason": "answer_not_extractable"},
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class AgentWithOnlyOkayCandidates:
    """Two candidates, both accepted."""
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "trace": [
                {"step": "generate_candidate", "status": "ok", "candidate_id": 0},
                {"step": "generate_candidate", "status": "ok", "candidate_id": 1},
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class MixedCandidateExtractionTest(unittest.TestCase):
    def test_partial_rejection_distinguishes_from_ok(self):
        report = evaluate(AgentWithMixedCandidates(), [{"idx": 3, "problem": "a", "answer": "42"}])
        record = report["records"][0]

        self.assertEqual(1, record["candidates_generated"])
        self.assertEqual(1, record["candidates_rejected"])
        self.assertFalse(record["all_candidates_rejected"])
        self.assertTrue(record["answer_not_extractable"])
        self.assertFalse(record["failed"])
        self.assertEqual(1, report["items_with_partial_rejection_count"])
        self.assertEqual(0, report["items_with_all_candidates_rejected_count"])

    def test_all_candidates_ok_counts_clean(self):
        report = evaluate(AgentWithOnlyOkayCandidates(), [
            {"idx": 0, "problem": "a", "answer": "42"},
            {"idx": 1, "problem": "b", "answer": "42"},
        ])
        self.assertEqual(4, report["candidates_generated_total"])
        self.assertEqual(0, report["candidates_rejected_total"])
        self.assertEqual(0, report["items_with_partial_rejection_count"])
        self.assertEqual(0, report["items_with_all_candidates_rejected_count"])
        self.assertEqual([], report["all_candidates_rejected_ids"])


if __name__ == "__main__":
    unittest.main()
