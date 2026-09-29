"""Tests for the local feature-profile selector."""

import sys
import unittest
from unittest.mock import patch

from main import parse_args
from reasoning_agent.profiles import (
    PROFILE_AGENT_DEFAULT,
    PROFILE_ARM_ADAPTIVE,
    PROFILE_ARM_OFF,
    PROFILE_ARM_ON,
    PROFILE_ARM_STATIC,
    PROFILE_ARM_V2_LONG_TIMEOUT,
    PROFILE_ARM_V2_SALVAGE,
    PROFILE_ARM_V2_SELECTIVE,
    PROFILE_ARM_V2_SINGLE,
    PROFILE_ARM_V21_OFF,
    PROFILE_ARM_V21_ON,
    PROFILE_ARM_V21_OFF_SKILL,
    PROFILE_ARM_V212_OFF,
    PROFILE_ARM_V212_ON,
    PROFILE_ARM_V213_OFF,
    PROFILE_ARM_V213_ON,
    PROFILE_ARM_V213_ADAPTIVE,
    PROFILE_ARM_V213_FORCED_AB,
    PROFILE_ARM_V213_OFF_SKILL,
    PROFILE_ARM_V212_ADAPTIVE,
    PROFILE_ARM_V212_OFF_SKILL,
    PROFILE_SUBMISSION,
    available_profiles,
    build_profile_config,
)
from user_agent import SUBMISSION_CONFIG


class ProfileConfigTest(unittest.TestCase):
    """Keep local profile selection explicit and side-effect free."""

    def test_available_profiles_are_stable(self):
        self.assertEqual(
            (
                PROFILE_SUBMISSION,
                PROFILE_ARM_V213_OFF,
                PROFILE_ARM_V213_ON,
                PROFILE_ARM_V213_ADAPTIVE,
                PROFILE_ARM_V213_FORCED_AB,
                PROFILE_ARM_V213_OFF_SKILL,
                PROFILE_AGENT_DEFAULT,
                PROFILE_ARM_OFF,
                PROFILE_ARM_ON,
                PROFILE_ARM_STATIC,
                PROFILE_ARM_ADAPTIVE,
                PROFILE_ARM_V2_SINGLE,
                PROFILE_ARM_V2_SELECTIVE,
                PROFILE_ARM_V2_LONG_TIMEOUT,
                PROFILE_ARM_V2_SALVAGE,
                PROFILE_ARM_V21_OFF,
                PROFILE_ARM_V21_ON,
                PROFILE_ARM_V21_OFF_SKILL,
                PROFILE_ARM_V212_OFF,
                PROFILE_ARM_V212_ON,
                PROFILE_ARM_V212_ADAPTIVE,
                PROFILE_ARM_V212_OFF_SKILL,
            ),
            available_profiles(),
        )

    def test_submission_profile_is_an_independent_copy(self):
        config = build_profile_config(PROFILE_SUBMISSION)
        self.assertIsNot(config, SUBMISSION_CONFIG)
        self.assertEqual(config, SUBMISSION_CONFIG)
        config.enable_fork_select_deepen_finish = False
        self.assertTrue(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)

    def test_agent_default_disables_experimental_routes(self):
        config = build_profile_config(PROFILE_AGENT_DEFAULT)
        self.assertFalse(config.enable_fork_select_deepen_finish)
        self.assertFalse(config.enable_constraint_fit_harness)
        self.assertFalse(config.enable_reference_rag)
        self.assertFalse(config.enable_arm_harness)

    def test_arm_profiles_are_explicit_and_submission_stays_off(self):
        off = build_profile_config(PROFILE_ARM_OFF)
        on = build_profile_config(PROFILE_ARM_ON)
        static = build_profile_config(PROFILE_ARM_STATIC)
        adaptive = build_profile_config(PROFILE_ARM_ADAPTIVE)

        self.assertTrue(off.enable_arm_harness)
        self.assertFalse(off.arm_allow_thinking_on)
        self.assertEqual("adaptive", off.arm_default_lane)
        self.assertTrue(on.arm_allow_thinking_on)
        self.assertEqual("deep_on", on.arm_default_lane)
        self.assertEqual("static", static.arm_default_lane)
        self.assertEqual("adaptive", adaptive.arm_default_lane)
        self.assertFalse(SUBMISSION_CONFIG.enable_arm_harness)

    def test_arm_v2_profiles_are_experiment_only(self):
        single = build_profile_config(PROFILE_ARM_V2_SINGLE)
        selective = build_profile_config(PROFILE_ARM_V2_SELECTIVE)
        long_timeout = build_profile_config(PROFILE_ARM_V2_LONG_TIMEOUT)
        salvage = build_profile_config(PROFILE_ARM_V2_SALVAGE)

        self.assertTrue(single.enable_arm_harness)
        self.assertEqual("v2", single.arm_harness_version)
        self.assertEqual("single", single.arm_v2_mode)
        self.assertEqual("selective", selective.arm_v2_mode)
        self.assertEqual("long_timeout", long_timeout.arm_v2_mode)
        self.assertEqual("salvage", salvage.arm_v2_mode)
        self.assertEqual("compact_salvage", salvage.arm_timeout_recovery_mode)
        self.assertEqual("v1", SUBMISSION_CONFIG.arm_harness_version)

    def test_unknown_profile_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown_profile"):
            build_profile_config("not-a-profile")

    def test_main_parser_accepts_profile_switch(self):
        argv = [
            "main.py",
            "--input_file",
            "input.jsonl",
            "--output_dir",
            "output",
            "--profile",
            PROFILE_AGENT_DEFAULT,
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(PROFILE_AGENT_DEFAULT, args.profile)


if __name__ == "__main__":
    unittest.main()
