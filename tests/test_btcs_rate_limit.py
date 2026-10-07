import unittest
from concurrent.futures import ThreadPoolExecutor

from user_agent import AgentConfig, ReasoningAgent
from tests.support.replay_client import ReplayClient


def make_agent(client):
    return ReasoningAgent(
        client,
        AgentConfig(
            protocol_mode="btcs_frame_v2",
            policy_temperature=0.0,
            enable_time_convergence=False,
            btcs_retry_base_delay_seconds=0.0,
        ),
    )


@unittest.skip(
    "BTCS archived (excluded_approaches 六.0/0a); baseline AgentConfig lacks "
    "protocol_mode / btcs_retry_base_delay_seconds, so these archived tests are "
    "explicitly skipped instead of reporting errors."
)
class BtcsRateLimitTest(unittest.TestCase):
    def test_one_rate_limit_is_retried_once_and_counts_separately(self):
        client = ReplayClient(
            [
                {"error": "rate_limit"},
                "FINAL: 7",
                "FINAL: 7",
            ]
        )
        result = make_agent(client).solve("计算 3+4。", {})
        self.assertEqual("7", result["extracted_answer"])
        self.assertEqual(3, len(client.calls))
        self.assertEqual(2, result["trace"][-1]["logical_calls"])
        self.assertEqual(3, result["trace"][-1]["http_attempts"])
        self.assertEqual(1, result["trace"][-1]["retry_count"])

    def test_second_rate_limit_halts_later_protocol_calls(self):
        client = ReplayClient([{"error": "503"}, {"error": "503"}, "FINAL: 7"])
        result = make_agent(client).solve("计算 3+4。", {})
        self.assertEqual(2, len(client.calls))
        self.assertEqual("", result["extracted_answer"])
        self.assertEqual(1, result["trace"][-1]["logical_calls"])
        self.assertEqual(2, result["trace"][-1]["http_attempts"])
        request_failures = [
            entry
            for entry in result["trace"]
            if entry.get("step") == "btcs_request" and entry.get("status") == "failed"
        ]
        self.assertEqual("service_unavailable", request_failures[-1]["error_category"])

    def test_three_agents_have_independent_budgets(self):
        def run_one(_):
            client = ReplayClient(
                [
                    "FINAL: 7",
                    "FINAL: 7",
                ]
            )
            result = make_agent(client).solve("计算 3+4。", {})
            return client, result

        with ThreadPoolExecutor(max_workers=3) as pool:
            outputs = list(pool.map(run_one, range(3)))
        for client, result in outputs:
            self.assertEqual(2, len(client.calls))
            self.assertEqual(2, result["trace"][-1]["logical_calls"])
            self.assertEqual(2, result["trace"][-1]["http_attempts"])
            self.assertEqual("7", result["extracted_answer"])


if __name__ == "__main__":
    unittest.main()
