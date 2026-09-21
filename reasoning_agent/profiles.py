"""Named local runtime profiles for switching groups of agent features.

The official platform still uses ``SUBMISSION_CONFIG`` through the no-argument
agent constructor.  These profiles only provide an explicit local selector.
"""

from dataclasses import replace
from typing import Final

from user_agent import AgentConfig, SUBMISSION_CONFIG


PROFILE_SUBMISSION: Final = "submission"
PROFILE_AGENT_DEFAULT: Final = "agent-default"
PROFILE_NAMES: Final = (PROFILE_SUBMISSION, PROFILE_AGENT_DEFAULT)


def available_profiles() -> tuple[str, ...]:
    """Return the profile names accepted by local runners."""

    return PROFILE_NAMES


def build_profile_config(profile: str) -> AgentConfig:
    """Build an independent config for a named local profile.

    ``submission`` copies the official submission profile without mutating the
    module-level object. ``agent-default`` uses dataclass defaults and keeps
    experimental routes disabled.

    Raises:
        ValueError: If ``profile`` is not a supported profile name.
    """

    normalized = profile.strip().lower()
    if normalized == PROFILE_SUBMISSION:
        return replace(SUBMISSION_CONFIG)
    if normalized == PROFILE_AGENT_DEFAULT:
        return AgentConfig()
    choices = ", ".join(PROFILE_NAMES)
    raise ValueError(f"unknown_profile:{profile!r}; choose one of: {choices}")
