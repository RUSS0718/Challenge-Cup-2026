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

    def test_partial_candidate_failure_does_not_fail_successful_solution(self):
        report = evaluate(
            PartiallyFailingAgent(),
            [{"idx": 7, "problem": "a", "answer": "42"}],
        )

        self.assertEqual([], report["failed_item_ids"])
        self.assertTrue(report["records"][0]["empty_response"])


if __name__ == "__main__":
    unittest.main()
