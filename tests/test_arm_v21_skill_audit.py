"""Acceptance tests for the reviewer-only Skill audit seam."""

import unittest

from reasoning_agent.math_harness import ConstraintFitOrchestrator, HarnessConfig
from reasoning_agent.skill_audit import SkillAuditResult


class ScriptedClient:
    """Return scripted candidates for skill state-machine tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, temperature, max_tokens, *, reasoning_mode="inherit", timeout_seconds=None):
        """Record calls and return the next response."""
        self.calls.append(reasoning_mode)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeAuditor:
    """Return one chosen audit status without creating any candidate."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def audit(self, *, problem, contract, candidate):
        """Inspect the existing candidate and return the configured status."""
        self.calls += 1
        return self.result


def _config():
    """Build a v2.1 skill-enabled config."""
    return HarnessConfig(
        enable_arm_harness=True,
        arm_harness_version="v2",
        arm_v2_mode="selective",
        enable_deep_lane=True,
        arm_enable_skill_audit=True,
        arm_max_skill_audits=1,
        arm_finalization_margin_seconds=0,
    )


class ARMV21SkillAuditTest(unittest.TestCase):
    """Check supported, refuted, and unknown reviewer outcomes."""

    def test_supported_audit_can_finalize_existing_candidate(self):
        client = ScriptedClient([{"content": "Final answer: 7", "finish_reason": "stop"}])
        auditor = FakeAuditor(SkillAuditResult("supported", "exact-evaluation", "checked"))
        result = ConstraintFitOrchestrator(client, config=_config(), skill_auditor=auditor).solve("计算一个复杂的函数极限", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual(1, auditor.calls)

    def test_refuted_audit_forces_second_solver(self):
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "stop"},
            {"content": "Final answer: 8", "finish_reason": "stop"},
        ])
        auditor = FakeAuditor(SkillAuditResult("refuted", "exact-evaluation", "counterexample"))
        result = ConstraintFitOrchestrator(client, config=_config(), skill_auditor=auditor).solve("计算一个复杂的函数极限", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual(3, len(client.calls))

    def test_unknown_audit_fails_open(self):
        client = ScriptedClient([
            {"content": "Final answer: 7", "finish_reason": "stop"},
            {"content": "Final answer: 7", "finish_reason": "stop"},
        ])
        auditor = FakeAuditor(SkillAuditResult("unknown", "exact-evaluation", "not_decisive"))
        result = ConstraintFitOrchestrator(client, config=_config(), skill_auditor=auditor).solve("计算一个复杂的函数极限", {})
        self.assertEqual("7", result["final_response"])
        self.assertEqual(2, len(client.calls))
        self.assertEqual(2, len(next(item for item in result["trace"] if item.get("stage") == "evidence_ledger")["candidates"]))


if __name__ == "__main__":
    unittest.main()
