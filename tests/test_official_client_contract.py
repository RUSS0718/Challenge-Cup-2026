"""Smoke-test the promoted CFR profile against the official client seam."""

import unittest

from user_agent import ReasoningAgent, SUBMISSION_CONFIG, SUBMISSION_MODE


class StrictOfficialClient:
    """Implement exactly the three arguments guaranteed by the platform."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, temperature, max_tokens):
        """Return a deterministic answer while rejecting optional controls."""
        del messages, temperature, max_tokens
        self.calls += 1
        return "Final answer: 2"


class OfficialClientContractTest(unittest.TestCase):
    """Keep the official entry usable without local client extensions."""

    def test_cfr_submission_uses_public_three_argument_client(self):
        self.assertEqual("arm-v2.1.4-cfr", SUBMISSION_MODE)
        self.assertEqual("v2.1.4", SUBMISSION_CONFIG.arm_harness_version)
        client = StrictOfficialClient()

        result = ReasoningAgent(client).solve("Compute 1+1", {"idx": 1})

        self.assertEqual("2", result["final_response"])
        self.assertGreaterEqual(client.calls, 1)
        ledger = next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")
        self.assertTrue(ledger["calls"])
        self.assertTrue(all(call.get("request_controls_fallback") for call in ledger["calls"]))


if __name__ == "__main__":
    unittest.main()
