"""Tests for ARM v2 runtime-failure recovery decisions."""

from types import SimpleNamespace
import unittest

from reasoning_agent.runtime_policy import RuntimeRecoveryPolicy, classify_runtime_failure


class RuntimeRecoveryPolicyTest(unittest.TestCase):
    """Keep runtime recovery bounded and separate from candidate trust."""

    def test_compact_salvage_has_a_small_request_budget(self):
        decision = RuntimeRecoveryPolicy("compact_salvage").decide(
            "timeout",
            current_max_tokens=4096,
            current_timeout_seconds=30,
            remaining_calls=1,
            remaining_tokens=4096,
        )
        self.assertEqual("compact_salvage", decision.action)
        self.assertEqual(1024, decision.max_tokens)
        self.assertEqual(15, decision.timeout_seconds)

    def test_compact_salvage_timeout_is_independent_of_remaining_tokens(self):
        decision = RuntimeRecoveryPolicy("compact_salvage").decide(
            "timeout",
            current_max_tokens=4096,
            current_timeout_seconds=30,
            remaining_calls=1,
            remaining_tokens=512,
        )
        self.assertEqual(512, decision.max_tokens)
        self.assertEqual(15, decision.timeout_seconds)

    def test_disabled_recovery_abstains(self):
        decision = RuntimeRecoveryPolicy("none").decide(
            "request_error",
            current_max_tokens=4096,
            current_timeout_seconds=30,
            remaining_calls=1,
            remaining_tokens=4096,
        )
        self.assertEqual("abstain", decision.action)

    def test_budget_exhaustion_prevents_recovery(self):
        decision = RuntimeRecoveryPolicy("compact_salvage").decide(
            "empty_response",
            current_max_tokens=4096,
            current_timeout_seconds=30,
            remaining_calls=0,
            remaining_tokens=4096,
        )
        self.assertEqual("budget_exhausted", decision.reason)

    def test_runtime_failure_classification_does_not_enter_trust_policy(self):
        self.assertEqual("timeout", classify_runtime_failure(SimpleNamespace(error_category="timeout", content=None)))
        self.assertEqual("empty_response", classify_runtime_failure(SimpleNamespace(error_category=None, content=None)))
        self.assertEqual("request_error", classify_runtime_failure(SimpleNamespace(error_category="client_exception", content=None)))
        self.assertIsNone(classify_runtime_failure(SimpleNamespace(error_category=None, content="Final answer: 1")))


if __name__ == "__main__":
    unittest.main()
