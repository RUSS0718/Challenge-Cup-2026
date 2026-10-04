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
    PROFILE_ARM_V212_ADAPTIVE,
    PROFILE_ARM_V212_OFF_SKILL,
    PROFILE_ARM_V213_OFF,
    PROFILE_ARM_V213_ON,
    PROFILE_ARM_V213_ADAPTIVE,
    PROFILE_ARM_V213_FORCED_AB,
    PROFILE_ARM_V213_OFF_SKILL,
    PROFILE_ARM_V214_OFF,
    PROFILE_ARM_V214_ADAPTIVE,
    PROFILE_ARM_V214_CFR,
    PROFILE_ARM_V215_BOUNDED_TAIL,
    PROFILE_ARM_V216_MISSING_CANDIDATE,
    PROFILE_FSDF_BASELINE,
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
                PROFILE_FSDF_BASELINE,
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
                PROFILE_ARM_V213_OFF,
                PROFILE_ARM_V213_ON,
                PROFILE_ARM_V213_ADAPTIVE,
                PROFILE_ARM_V213_FORCED_AB,
                PROFILE_ARM_V213_OFF_SKILL,
                PROFILE_ARM_V214_OFF,
                PROFILE_ARM_V214_ADAPTIVE,
                PROFILE_ARM_V214_CFR,
                PROFILE_ARM_V215_BOUNDED_TAIL,
                PROFILE_ARM_V216_MISSING_CANDIDATE,
            ),
            available_profiles(),
        )

    def test_submission_profile_is_an_independent_copy(self):
        config = build_profile_config(PROFILE_SUBMISSION)
        self.assertIsNot(config, SUBMISSION_CONFIG)
        self.assertEqual(config, SUBMISSION_CONFIG)
        config.enable_fork_select_deepen_finish = False
        self.assertTrue(SUBMISSION_CONFIG.enable_fork_select_deepen_finish)

    def test_fsdf_baseline_profile_is_independent_from_submission_mode(self):
        config = build_profile_config(PROFILE_FSDF_BASELINE)
        self.assertIsNot(config, SUBMISSION_CONFIG)
        self.assertEqual("v1", config.arm_harness_version)
        self.assertTrue(config.enable_fork_select_deepen_finish)

    def test_agent_default_disables_experimental_routes(self):
        config = build_profile_config(PROFILE_AGENT_DEFAULT)
        self.assertFalse(config.enable_fork_select_deepen_finish)
        self.assertFalse(config.enable_constraint_fit_harness)
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
        self.assertEqual(build_profile_config(PROFILE_SUBMISSION), SUBMISSION_CONFIG)

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
        self.assertEqual(build_profile_config(PROFILE_SUBMISSION), SUBMISSION_CONFIG)

    def test_unknown_profile_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown_profile"):
            build_profile_config("not-a-profile")

    def test_v213_profiles_match_the_authorized_submission_off_mode(self):
        off = build_profile_config(PROFILE_ARM_V213_OFF)
        on = build_profile_config(PROFILE_ARM_V213_ON)
        adaptive = build_profile_config(PROFILE_ARM_V213_ADAPTIVE)
        forced = build_profile_config(PROFILE_ARM_V213_FORCED_AB)
        self.assertEqual("v2.1.3", off.arm_harness_version)
        self.assertEqual("positive_evidence", off.arm_trust_policy)
        self.assertEqual("positive_evidence", on.arm_trust_policy)
        self.assertEqual("adaptive", adaptive.arm_solver_reasoning_mode)
        self.assertTrue(forced.arm_force_ab_diagnostic)
        self.assertTrue(SUBMISSION_CONFIG.enable_arm_harness)

    def test_v214_cfr_profile_matches_the_new_submission_selector(self):
        cfr = build_profile_config(PROFILE_ARM_V214_CFR)
        self.assertEqual("v2.1.4", cfr.arm_harness_version)
        self.assertEqual("selective", cfr.arm_v2_mode)
        self.assertEqual("off", cfr.arm_solver_reasoning_mode)
        self.assertEqual("positive_evidence", cfr.arm_trust_policy)
        self.assertFalse(cfr.enable_constraint_fit_hybrid_router)
        self.assertTrue(cfr.arm_enable_targeted_repair)
        self.assertTrue(cfr.arm_enable_fresh_review)
        self.assertEqual(4, cfr.arm_adaptive_max_calls)
        self.assertEqual(4, cfr.arm_deep_max_calls)
        self.assertEqual(16_384, cfr.arm_adaptive_token_budget)
        self.assertEqual(16_384, cfr.arm_deep_token_budget)
        self.assertEqual(build_profile_config(PROFILE_SUBMISSION), SUBMISSION_CONFIG)
        self.assertEqual(cfr, SUBMISSION_CONFIG)

    def test_v215_bounded_tail_profile_is_explicit_and_default_off(self):
        bounded_tail = build_profile_config(PROFILE_ARM_V215_BOUNDED_TAIL)
        self.assertEqual("v2.1.5", bounded_tail.arm_harness_version)
        self.assertTrue(bounded_tail.enable_arm_harness)
        self.assertEqual("positive_evidence", bounded_tail.arm_trust_policy)
        self.assertEqual(build_profile_config(PROFILE_ARM_V214_CFR), SUBMISSION_CONFIG)

    def test_v216_missing_candidate_profile_is_explicit_and_default_off(self):
        missing_candidate = build_profile_config(PROFILE_ARM_V216_MISSING_CANDIDATE)
        self.assertEqual("v2.1.6", missing_candidate.arm_harness_version)
        self.assertTrue(missing_candidate.enable_arm_harness)
        self.assertEqual("positive_evidence", missing_candidate.arm_trust_policy)
        self.assertEqual(build_profile_config(PROFILE_ARM_V214_CFR), SUBMISSION_CONFIG)

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
