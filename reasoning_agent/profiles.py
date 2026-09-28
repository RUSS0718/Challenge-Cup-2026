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
PROFILE_NAMES: Final = (
    PROFILE_SUBMISSION,
    PROFILE_AGENT_DEFAULT,
    PROFILE_ARM_OFF,
    PROFILE_ARM_ON,
    PROFILE_ARM_STATIC,
    PROFILE_ARM_ADAPTIVE,
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
    choices = ", ".join(PROFILE_NAMES)
    raise ValueError(f"unknown_profile:{profile!r}; choose one of: {choices}")
