"""Acceptance tests for the v2.1 internal deadline guard."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class FakeClock:
    """Deterministic clock advanced by the scripted client."""

    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class AdvancingClient:
    """Advance past the finalization margin after the first request."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Return one candidate and move the fake clock forward."""
        self.calls.append(reasoning_mode)
        self.clock.value += 6
        return {"content": "Final answer: 7", "finish_reason": "stop"}


class ARMV21DeadlineTest(unittest.TestCase):
    """Ensure a candidate is finalized before starting optional work."""

    def test_deadline_returns_safe_candidate_without_second_call(self):
        clock = FakeClock()
        client = AdvancingClient(clock)
        config = HarnessConfig(
            enable_arm_harness=True,
            arm_harness_version="v2",
            arm_v2_mode="selective",
            enable_deep_lane=True,
            max_wall_seconds=10,
            arm_finalization_margin_seconds=5,
        )
        result = ConstraintFitOrchestrator(client, config=config, clock=clock).solve("计算一个复杂的函数极限", {})
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("7", result["final_response"])
        self.assertEqual(["off"], client.calls)
        self.assertTrue(summary["deadline_finalized"])


if __name__ == "__main__":
    unittest.main()
