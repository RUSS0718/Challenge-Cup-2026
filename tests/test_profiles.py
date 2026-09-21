"""Tests for the local feature-profile selector."""

import sys
import unittest
from unittest.mock import patch

from main import parse_args
from reasoning_agent.profiles import (
    PROFILE_AGENT_DEFAULT,
    PROFILE_SUBMISSION,
    available_profiles,
    build_profile_config,
)
from user_agent import SUBMISSION_CONFIG


class ProfileConfigTest(unittest.TestCase):
    """Keep local profile selection explicit and side-effect free."""

    def test_available_profiles_are_stable(self):
        self.assertEqual((PROFILE_SUBMISSION, PROFILE_AGENT_DEFAULT), available_profiles())

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
