"""Named local runtime profiles for switching groups of agent features.

The official platform still uses ``SUBMISSION_CONFIG`` through the no-argument
agent constructor.  These profiles only provide an explicit local selector.
"""

from dataclasses import replace
from typing import Final

from user_agent import AgentConfig, SUBMISSION_CONFIG


PROFILE_SUBMISSION: Final = "submission"
PROFILE_AGENT_DEFAULT: Final = "agent-default"
PROFILE_ARM_OFF: Final = "arm-off"
PROFILE_ARM_ON: Final = "arm-on"
PROFILE_ARM_STATIC: Final = "arm-static"
PROFILE_ARM_ADAPTIVE: Final = "arm-adaptive"
PROFILE_ARM_V2_SINGLE: Final = "arm-v2-single"
PROFILE_ARM_V2_SELECTIVE: Final = "arm-v2-selective"
PROFILE_ARM_V2_LONG_TIMEOUT: Final = "arm-v2-long-timeout"
PROFILE_ARM_V2_SALVAGE: Final = "arm-v2-salvage"
PROFILE_ARM_V21_OFF: Final = "arm-v2.1-off"
PROFILE_ARM_V21_ON: Final = "arm-v2.1-on"
PROFILE_ARM_V21_OFF_SKILL: Final = "arm-v2.1-off-skill"
PROFILE_NAMES: Final = (
    PROFILE_SUBMISSION,
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
)


def available_profiles() -> tuple[str, ...]:
    """Return the profile names accepted by local runners."""

    return PROFILE_NAMES


def build_profile_config(profile: str) -> AgentConfig:
    """Build an independent config for a named local profile.

    ``submission`` copies the official submission profile without mutating the
    module-level object. ``agent-default`` keeps experimental routes disabled;
    ``arm-*`` profiles explicitly enable one local reasoning-mode experiment.

    Raises:
        ValueError: If ``profile`` is not a supported profile name.
    """

    normalized = profile.strip().lower()
    if normalized == PROFILE_SUBMISSION:
        return replace(SUBMISSION_CONFIG)
    if normalized == PROFILE_AGENT_DEFAULT:
        return AgentConfig()
    arm_profiles = {
        PROFILE_ARM_OFF: ("adaptive", False),
        PROFILE_ARM_ON: ("deep_on", True),
        PROFILE_ARM_STATIC: ("static", True),
        PROFILE_ARM_ADAPTIVE: ("adaptive", True),
    }
    if normalized in arm_profiles:
        lane, allow_on = arm_profiles[normalized]
        return AgentConfig(
            enable_constraint_fit_harness=True,
            enable_constraint_fit_deep_lane=True,
            enable_constraint_fit_hybrid_router=False,
            enable_arm_harness=True,
            arm_allow_thinking_on=allow_on,
            arm_default_lane=lane,
        )
    arm_v2_profiles = {
        PROFILE_ARM_V2_SINGLE: ("single", "none", None),
        PROFILE_ARM_V2_SELECTIVE: ("selective", "none", None),
        PROFILE_ARM_V2_LONG_TIMEOUT: ("long_timeout", "none", 60),
        PROFILE_ARM_V2_SALVAGE: ("salvage", "compact_salvage", 30),
    }
    if normalized in arm_v2_profiles:
        mode, recovery_mode, primary_timeout = arm_v2_profiles[normalized]
        return AgentConfig(
            enable_constraint_fit_harness=True,
            enable_constraint_fit_deep_lane=True,
            enable_constraint_fit_hybrid_router=False,
            enable_arm_harness=True,
            arm_harness_version="v2",
            arm_v2_mode=mode,
            arm_timeout_recovery_mode=recovery_mode,
            arm_primary_timeout_seconds=primary_timeout,
            arm_allow_thinking_on=False,
            arm_default_lane="adaptive",
        )
    arm_v21_profiles = {
        PROFILE_ARM_V21_OFF: ("off", False),
        PROFILE_ARM_V21_ON: ("on", False),
        PROFILE_ARM_V21_OFF_SKILL: ("off", True),
    }
    if normalized in arm_v21_profiles:
        solver_mode, enable_skill = arm_v21_profiles[normalized]
        return AgentConfig(
            enable_constraint_fit_harness=True,
            enable_constraint_fit_deep_lane=True,
            enable_constraint_fit_hybrid_router=False,
            enable_arm_harness=True,
            arm_harness_version="v2",
            arm_v2_mode="selective",
            arm_solver_reasoning_mode=solver_mode,
            arm_allow_thinking_on=False,
            arm_enable_skill_audit=enable_skill,
            arm_max_skill_audits=1,
            arm_default_lane="adaptive",
        )
    choices = ", ".join(PROFILE_NAMES)
    raise ValueError(f"unknown_profile:{profile!r}; choose one of: {choices}")
