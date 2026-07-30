import unittest

from scripts.evaluate_dev import (
    EXPECTED_SUBJECT_COUNTS,
    evaluate,
    validate_regression_items,
)


class CapturingAgent:
    def __init__(self):
        self.calls = []

    def solve(self, problem, metadata):
        self.calls.append((problem, metadata))
        return {
            "final_response": "42",
            "extracted_answer": "42",
            "trace": [{"step": "finalize", "status": "selected", "model_calls": 2}],
        }


class PartiallyFailingAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "42",
            "extracted_answer": "42",
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
            "extracted_answer": "42",
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
            "extracted_answer": "42",
            "trace": [
                {"step": "route_budget", "status": "selected", "reason": "answer_conflict"},
                {"step": "finalize", "status": "selected", "model_calls": 2},
            ],
        }


class EmptyFinalResponseAgent:
    def solve(self, problem, metadata):
        return {
            "final_response": "",
            "extracted_answer": "",
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

    def test_subject_and_answer_stay_out_of_solve_and_feed_grouped_metrics(self):
        agent = CapturingAgent()
        items = [
            {"idx": 1, "problem": "求 6 * 7。", "answer": "42", "subject": "离散数学"},
            {"idx": 2, "problem": "证明该结论。", "answer": "not 42", "subject": "测度积分"},
            {"idx": 3, "problem": "求 6 * 7。", "answer": "42", "subject": "数值分析"},
            {"idx": 4, "problem": "求 6 * 7。", "answer": "42", "subject": "概率论"},
            {"idx": 5, "problem": "求 6 * 7。", "answer": "not 42", "subject": "非基础及进阶课程"},
        ]

        report = evaluate(agent, items)

        self.assertTrue(all(set(metadata) == {"idx"} for _, metadata in agent.calls))
        self.assertEqual(0.6, report["accuracy"])
        self.assertEqual(1.0, report["strategy_families"]["离散—代数—优化"]["accuracy"])
        self.assertEqual(0.0, report["strategy_families"]["连续纯数学"]["accuracy"])
        self.assertEqual(1.0, report["subjects"]["数值分析"]["accuracy"])
        self.assertEqual(0.75, report["problem_types"]["calculation"]["accuracy"])
        self.assertEqual(0.0, report["problem_types"]["proof"]["accuracy"])
        self.assertEqual(0.375, report["problem_type_macro_accuracy"])

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
            "extracted_answer": "42",
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
            "extracted_answer": "42",
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


class RegressionDatasetValidationTest(unittest.TestCase):
    def make_items(self):
        items = []
        idx = 0
        for subject, count in EXPECTED_SUBJECT_COUNTS.items():
            for offset in range(count):
                items.append({
                    "idx": idx,
                    "problem": f"{subject} public problem {offset}",
                    "answer": str(offset),
                    "subject": subject,
                    "source": "public_regression",
                    "source_url": "https://example.org/open-textbook",
                    "source_ref": "Chapter 1",
                    "adaptation": "original_parameterized",
                    "verification": "independent calculation",
                })
                idx += 1
        return items

    def test_accepts_complete_112_item_distribution(self):
        self.assertEqual([], validate_regression_items(self.make_items()))

    def test_rejects_duplicate_problem_and_missing_answer(self):
        items = self.make_items()
        items[1]["problem"] = items[0]["problem"]
        items[2]["answer"] = ""
        items[3]["source_url"] = "http://example.org/not-https"

        errors = validate_regression_items(items)

        self.assertIn("duplicate_problem", errors)
        self.assertIn("empty_answer:2", errors)
        self.assertIn("invalid_source_url:3", errors)


# ── P3.1: answer judge + evaluator correctness tests ────────────────────

class JudgeCorrectTest(unittest.TestCase):
    def test_exact_numeric_match(self):
        from scripts.evaluate_dev import judge_correct
        self.assertEqual("correct", judge_correct("42", "42"))
        self.assertEqual("correct", judge_correct(" 42 ", "42"))

    def test_rational_equivalence(self):
        from scripts.evaluate_dev import judge_correct
        self.assertEqual("correct", judge_correct("1/2", "0.5"))
        self.assertEqual("correct", judge_correct("0.5", "1/2"))

    def test_radical_returns_unknown_not_false_positive(self):
        from scripts.evaluate_dev import judge_correct
        self.assertEqual("unknown", judge_correct("sqrt(2)", "2"))
        self.assertEqual("unknown", judge_correct("sqrt(4)", "2"))
        self.assertEqual("unknown", judge_correct("sqrt(2)", "sqrt(3)"))

    def test_choice_letters_case_insensitive(self):
        from scripts.evaluate_dev import judge_correct
        self.assertEqual("correct", judge_correct("A", "a", "choice"))
        self.assertEqual("incorrect", judge_correct("A", "B", "choice"))

    def test_unknown_for_plain_text(self):
        from scripts.evaluate_dev import judge_correct
        self.assertEqual("unknown", judge_correct("hello", "world"))
        self.assertEqual("unknown", judge_correct("x=1", "x=2"))


class P3EvaluatorMetricsTest(unittest.TestCase):
    def test_report_includes_p3_fields(self):
        from scripts.evaluate_dev import evaluate
        agent = CapturingAgent()
        report = evaluate(agent, [{"idx": 0, "problem": "q", "answer": "42"}])
        self.assertIn("verdict_counts", report)
        self.assertIn("strict_accuracy", report)
        self.assertIn("decided_accuracy", report)
        self.assertIn("unknown_rate", report)
        self.assertIn("judge_coverage", report)
        self.assertIn("p95_model_calls", report)
        self.assertIn("p95_latency_seconds", report)

    def test_record_has_p3_fields(self):
        from scripts.evaluate_dev import evaluate
        agent = CapturingAgent()
        report = evaluate(agent, [{"idx": 0, "problem": "q", "answer": "42"}])
        record = report["records"][0]
        self.assertIn("verdict", record)
        self.assertIn("extracted_answer", record)
        self.assertIn("verify_calls", record)
        self.assertIn("revise_attempts", record)
        self.assertIn("revise_accepted", record)
        self.assertIn("revise_rejected", record)
        self.assertIn("revise_rolled_back", record)

    def test_verdict_counts_sum_correctly(self):
        from scripts.evaluate_dev import evaluate
        agent = CapturingAgent()  # always returns "42"
        items = [
            {"idx": 0, "problem": "q0", "answer": "42"},
            {"idx": 1, "problem": "q1", "answer": "999"},  # incorrect
            {"idx": 2, "problem": "q2", "answer": "sqrt(2)"},  # unknown
        ]
        report = evaluate(agent, items)
        vc = report["verdict_counts"]
        self.assertEqual(1, vc.get("correct", 0))
        self.assertEqual(1, vc.get("incorrect", 0))
        self.assertEqual(1, vc.get("unknown", 0))

    def test_budget_config_has_p2_p3_switches(self):
        from scripts.evaluate_dev import summarize_budget_config
        from user_agent import AgentConfig, ReasoningAgent
        config = AgentConfig(enable_step_verification=True, p3_call_boost=3)
        agent = ReasoningAgent.__new__(ReasoningAgent)
        agent.config = config
        bc = summarize_budget_config(agent)
        self.assertTrue(bc["enable_step_verification"])
        self.assertFalse(bc["enable_step_revision"])
        self.assertEqual(9, bc["effective_max_calls"])
        self.assertEqual(3, bc["p3_call_boost"])

    def test_l2_effective_calls_accounts_for_l2_max(self):
        from scripts.evaluate_dev import summarize_budget_config
        from user_agent import AgentConfig, ReasoningAgent
        config = AgentConfig(enable_l2_routing=True, l2_max_model_calls=8,
                             enable_step_verification=True, p3_call_boost=3)
        agent = ReasoningAgent.__new__(ReasoningAgent)
        agent.config = config
        bc = summarize_budget_config(agent)
        # max(6, 8) + 3 = 11
        self.assertEqual(11, bc["effective_max_calls"])

    def test_rolled_back_revision_not_counted_as_accepted(self):
        """Revision later rolled back → revise_accepted=0, revise_rolled_back=1."""
        from scripts.evaluate_dev import evaluate
        class RollbackAgent:
            def solve(self, problem, metadata):
                return {
                    "final_response": "3",
                    "extracted_answer": "3",
                    "trace": [
                        {"step": "finalize", "status": "selected", "model_calls": 3},
                        {"step": "verify", "status": "ok", "error_count": 1},
                        {"step": "revise", "status": "ok"},
                        {"step": "reverify", "status": "fail", "error_count": 1},
                    ],
                }
        report = evaluate(RollbackAgent(), [{"idx": 0, "problem": "q", "answer": "2"}])
        record = report["records"][0]
        self.assertEqual(0, record["revise_accepted"])
        self.assertEqual(1, record["revise_rolled_back"])
        self.assertEqual(0, report["revise_accepted_count"])
        self.assertEqual(1, report["revise_rolled_back_count"])

    def test_accepted_revision_has_no_rollback(self):
        """Revision survives re-verify → accepted=1, rolled_back=0."""
        from scripts.evaluate_dev import evaluate
        class OkAgent:
            def solve(self, problem, metadata):
                return {
                    "final_response": "2",
                    "extracted_answer": "2",
                    "trace": [
                        {"step": "finalize", "status": "selected", "model_calls": 3},
                        {"step": "verify", "status": "ok", "error_count": 1},
                        {"step": "revise", "status": "ok"},
                        {"step": "reverify", "status": "ok", "error_count": 0},
                    ],
                }
        report = evaluate(OkAgent(), [{"idx": 0, "problem": "q", "answer": "2"}])
        record = report["records"][0]
        self.assertEqual(1, record["revise_accepted"])
        self.assertEqual(0, record["revise_rolled_back"])


if __name__ == "__main__":
    unittest.main()
