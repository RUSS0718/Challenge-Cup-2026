"""Verify that the public no-config entrypoint selects the active EACL path."""

from __future__ import annotations

import unittest

from user_agent import EACL_SUBMISSION_MODE, ReasoningAgent


class RecordingClient:
    """Minimal public client used to inspect one bounded EACL solve."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Record request controls and return a closed candidate."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        return "FINAL_CANDIDATE: 2"


class EACLEntryPointTests(unittest.TestCase):
    """Keep the official no-config seam on the new control plane."""

    def test_no_config_uses_eacl_and_reasoning_mode(self):
        client = RecordingClient()
        result = ReasoningAgent(client).solve("计算 1+1", {})

        self.assertEqual(EACL_SUBMISSION_MODE, "grh-eacl-v1")
        self.assertEqual("2", result["extracted_answer"])
        self.assertEqual("grh_eacl_v1", result["trace"][0]["method"])
        self.assertTrue(client.calls)


if __name__ == "__main__":
    unittest.main()
