"""Acceptance tests for the official-equivalent submission entry."""

from dataclasses import asdict
from unittest.mock import patch
import unittest

import user_agent
from reasoning_agent.profiles import (
    PROFILE_ARM_V212_ADAPTIVE,
    PROFILE_ARM_V212_OFF,
    PROFILE_ARM_V212_ON,
    PROFILE_FSDF_BASELINE,
    build_profile_config,
    build_submission_arm_config,
)
from user_agent import (
    ARM_V212_BASE_CONFIG,
    ReasoningAgent,
    SUBMISSION_CONFIG,
    SUBMISSION_MODE,
    build_submission_config,
)


class EntryClient:
    """Return bounded answers while recording request-local reasoning modes."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Record public request controls and return a parseable answer."""
        del messages, temperature, max_tokens
        self.calls.append(str(kwargs.get("reasoning_mode", "inherit")))
        return "Final answer: 2"


class SubmissionEntryTest(unittest.TestCase):
    """Verify mode selection through ``ReasoningAgent(config=None)``."""

    def _solve_as_official(self, mode: str, problem: str):
        client = EntryClient()
        with patch.object(user_agent, "SUBMISSION_CONFIG", build_submission_config(mode)):
            result = ReasoningAgent(client).solve(problem, {})
        return client, result

    def test_default_submission_uses_fsdf_without_arm_policy(self):
        client, result = self._solve_as_official("fsdf", "请证明：若 x=1，则 x=1")
        route = next(item for item in result["trace"] if item.get("stage") == "route")
        legacy = next(item for item in result["trace"] if item.get("stage") == "legacy_backend")
        self.assertEqual("legacy_fsdf", route["target"])
        self.assertEqual("fsdf_v1", legacy["backend"])
        self.assertFalse(any(item.get("stage") == "arm_v2_policy" for item in result["trace"]))
        self.assertTrue(client.calls)

    def test_arm_modes_are_selected_from_the_official_entry(self):
        for mode, expected in (
            ("arm-v2.1.2-off", "off"),
            ("arm-v2.1.2-on", "on"),
        ):
            with self.subTest(mode=mode):
                client, result = self._solve_as_official(mode, "计算 1+1")
                policy = next(item for item in result["trace"] if item.get("stage") == "arm_v2_policy")
                self.assertEqual("arm_harness_v2", policy["method"])
                self.assertEqual(expected, policy["solver_reasoning_mode"])
                self.assertEqual(expected, client.calls[0])

    def test_adaptive_entry_uses_route_risk_to_select_mode(self):
        fast_client, fast_result = self._solve_as_official("arm-v2.1.2-adaptive", "计算 1+1")
        fast_policy = next(item for item in fast_result["trace"] if item.get("stage") == "arm_v2_policy")
        self.assertEqual("adaptive", fast_policy["configured_solver_reasoning_mode"])
        self.assertEqual("off", fast_policy["solver_reasoning_mode"])
        self.assertEqual("off", fast_client.calls[0])

        deep_client, deep_result = self._solve_as_official(
            "arm-v2.1.2-adaptive",
            "请证明：若 x=1，则 x=1，并说明边界条件。",
        )
        deep_policy = next(item for item in deep_result["trace"] if item.get("stage") == "arm_v2_policy")
        self.assertEqual("on", deep_policy["solver_reasoning_mode"])
        self.assertEqual("on", deep_client.calls[0])

    def test_local_and_submission_arm_configs_have_no_hidden_differences(self):
        profiles = {
            "off": PROFILE_ARM_V212_OFF,
            "on": PROFILE_ARM_V212_ON,
            "adaptive": PROFILE_ARM_V212_ADAPTIVE,
        }
        for mode, profile in profiles.items():
            with self.subTest(mode=mode):
                local = asdict(build_profile_config(profile))
                submission = asdict(build_submission_arm_config(mode))
                self.assertEqual(local, submission)

        base = asdict(ARM_V212_BASE_CONFIG)
        off = asdict(build_submission_arm_config("off"))
        allowed = {"arm_solver_reasoning_mode", "arm_allow_thinking_on"}
        self.assertEqual(
            {key: value for key, value in base.items() if key not in allowed},
            {key: value for key, value in off.items() if key not in allowed},
        )

    def test_official_config_is_derived_from_one_mode_selector(self):
        self.assertIn(
            SUBMISSION_MODE,
            {
                "fsdf",
                "arm-v2.1.2-off",
                "arm-v2.1.2-on",
                "arm-v2.1.2-adaptive",
                "arm-v2.1.3-off",
                "arm-v2.1.3-on",
                "arm-v2.1.3-adaptive",
            },
        )
        self.assertEqual(SUBMISSION_CONFIG, build_submission_config(SUBMISSION_MODE))
        self.assertEqual(
            build_submission_config("fsdf"),
            build_profile_config(PROFILE_FSDF_BASELINE),
        )


if __name__ == "__main__":
    unittest.main()
