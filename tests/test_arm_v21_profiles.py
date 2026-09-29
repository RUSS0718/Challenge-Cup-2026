"""Acceptance tests for the v2.1 profile contract."""

from dataclasses import asdict
import unittest

from reasoning_agent.profiles import (
    PROFILE_ARM_V21_OFF,
    PROFILE_ARM_V21_OFF_SKILL,
    PROFILE_ARM_V21_ON,
    build_profile_config,
)
from user_agent import AgentConfig, SUBMISSION_CONFIG


class ARMV21ProfilesTest(unittest.TestCase):
    """Ensure ON/OFF profiles differ only in the solver mode."""

    def test_off_profile_contract(self):
        config = build_profile_config(PROFILE_ARM_V21_OFF)
        self.assertEqual("v2", config.arm_harness_version)
        self.assertEqual("selective", config.arm_v2_mode)
        self.assertEqual("off", config.arm_solver_reasoning_mode)
        self.assertFalse(config.arm_allow_thinking_on)
        self.assertFalse(config.arm_enable_skill_audit)
        self.assertEqual(600, config.arm_primary_timeout_seconds)
        self.assertTrue(config.enable_constraint_fit_harness)
        self.assertTrue(config.enable_constraint_fit_deep_lane)
        self.assertTrue(config.enable_constraint_fit_hybrid_router)
        self.assertTrue(config.enable_fork_select_deepen_finish)
        self.assertEqual(SUBMISSION_CONFIG.max_tokens, config.max_tokens)
        self.assertEqual(SUBMISSION_CONFIG.enable_adaptive_voting, config.enable_adaptive_voting)

    def test_on_profile_is_single_variable(self):
        off = asdict(build_profile_config(PROFILE_ARM_V21_OFF))
        on = asdict(build_profile_config(PROFILE_ARM_V21_ON))
        self.assertEqual("off", off.pop("arm_solver_reasoning_mode"))
        self.assertEqual("on", on.pop("arm_solver_reasoning_mode"))
        self.assertEqual(off, on)

    def test_skill_profile_only_enables_audit(self):
        skill = build_profile_config(PROFILE_ARM_V21_OFF_SKILL)
        off = build_profile_config(PROFILE_ARM_V21_OFF)
        self.assertTrue(skill.arm_enable_skill_audit)
        self.assertTrue(skill.arm_enable_skill_guidance)
        self.assertFalse(skill.arm_enable_skill_for_second)
        self.assertFalse(off.arm_enable_skill_guidance)
        self.assertEqual(off.arm_solver_reasoning_mode, skill.arm_solver_reasoning_mode)
        self.assertEqual(off.arm_v2_mode, skill.arm_v2_mode)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            AgentConfig(arm_solver_reasoning_mode="invalid")
        with self.assertRaises(ValueError):
            AgentConfig(arm_finalization_margin_seconds=-1)
        with self.assertRaises(ValueError):
            AgentConfig(arm_max_skill_audits=-1)


if __name__ == "__main__":
    unittest.main()
