"""Acceptance tests for the ARM-Harness v2.1.2 recovery and trust gates."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig


class ScriptedClient:
    """Return bounded envelopes while recording request-local controls."""

    def __init__(self, responses):
        """Initialize the response queue and request telemetry sink."""
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record the request mode and token budget for one scripted call."""
        self.calls.append(
            {
                "reasoning_mode": reasoning_mode,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.responses.pop(0)


class StringMetadataClient(ScriptedClient):
    """Model the local client contract: string content plus public metadata."""

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Return string content while exposing the response envelope separately."""
        content = super().chat(
            messages,
            temperature,
            max_tokens,
            reasoning_mode=reasoning_mode,
            timeout_seconds=timeout_seconds,
        )
        self.last_response_metadata = {
            "has_reasoning_content": False,
            "reasoning_content_chars": 0,
            "content_chars": len(content),
            "finish_reason": "stop",
            "completion_tokens": 5,
        }
        return content


def _config(**overrides):
    """Build the explicit v2.1.2 profile used by these state tests."""
    values = {
        "enable_arm_harness": True,
        "arm_harness_version": "v2",
        "arm_v2_mode": "selective",
        "enable_deep_lane": True,
        "arm_solver_reasoning_mode": "on",
        "arm_trust_policy": "evidence",
        "arm_finalization_margin_seconds": 0,
        "arm_off_finalizer_max_tokens": 1024,
    }
    values.update(overrides)
    return HarnessConfig(**values)


class ARMV212Test(unittest.TestCase):
    """Keep evidence-triggered selectivity and ON recovery independently observable."""

    def test_complete_candidate_stops_without_redundant_second_sample(self):
        """Retain a complete candidate when no negative evidence exists."""
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_solver_reasoning_mode="off"),
        ).solve("计算一个复杂的函数极限", {})
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("7", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertFalse(summary["second_sample_triggered"])
        self.assertEqual("complete_without_negative_evidence", summary["primary_candidate"]["trust_reason"])

    def test_incomplete_on_candidate_uses_off_finalizer(self):
        """Switch an incomplete ON response to one bounded OFF finalizer."""
        client = ScriptedClient([
            "I cannot finish the derivation.",
            {"content": "Final answer: 9", "finish_reason": "stop"},
        ])
        result = ConstraintFitOrchestrator(client, config=_config()).solve(
            "求一个复杂的函数极限", {}
        )
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("9", result["final_response"])
        self.assertEqual(["on", "off"], [call["reasoning_mode"] for call in client.calls])
        self.assertEqual(1024, client.calls[1]["max_tokens"])
        self.assertEqual("off_finalizer", summary["on_recovery_action"])
        self.assertEqual("arm_v2_off_finalizer", ledger["calls"][1]["stage"])

    def test_response_schema_metadata_stays_bounded(self):
        """Expose reasoning/content lengths in the solve-local ledger only."""
        client = ScriptedClient([
            {
                "message": {
                    "content": "Final answer: 7",
                    "reasoning_content": "abc",
                },
                "finish_reason": "stop",
            },
        ])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_solver_reasoning_mode="off"),
        ).solve("计算一个复杂的函数极限", {})
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        call = ledger["calls"][0]
        self.assertTrue(call["has_reasoning_content"])
        self.assertEqual(3, call["reasoning_content_chars"])
        self.assertEqual(len("Final answer: 7"), call["content_chars"])

    def test_string_client_metadata_preserves_normal_stop(self):
        """Do not trigger B when a string client reports finish_reason=stop separately."""
        client = StringMetadataClient(["Final answer: 7"])
        result = ConstraintFitOrchestrator(
            client,
            config=_config(arm_solver_reasoning_mode="off"),
        ).solve("计算一个复杂的函数极限", {})
        summary = next(item for item in result["trace"] if item.get("stage") == "arm_v2_summary")
        self.assertEqual("7", result["final_response"])
        self.assertEqual(1, len(client.calls))
        self.assertFalse(summary["second_sample_triggered"])
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        self.assertEqual("stop", ledger["calls"][0]["finish_reason"])
        self.assertEqual(
            "complete_without_negative_evidence",
            summary["primary_candidate"]["trust_reason"],
        )


if __name__ == "__main__":
    unittest.main()
