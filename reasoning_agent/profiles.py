"""Named local runtime profiles for switching groups of agent features.

The official platform still uses ``SUBMISSION_CONFIG`` through the no-argument
agent constructor.  These profiles only provide an explicit local selector.
"""

from dataclasses import replace
from typing import Final

from reasoning_agent.submission_config import SUBMISSION_FSDF
from user_agent import AgentConfig, SUBMISSION_CONFIG, SUBMISSION_MODE, build_submission_config


PROFILE_SUBMISSION: Final = "submission"
PROFILE_FSDF_BASELINE: Final = "fsdf"
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
PROFILE_ARM_V212_OFF: Final = "arm-v2.1.2-off"
PROFILE_ARM_V212_ON: Final = "arm-v2.1.2-on"
PROFILE_ARM_V212_ADAPTIVE: Final = "arm-v2.1.2-adaptive"
PROFILE_ARM_V212_OFF_SKILL: Final = "arm-v2.1.2-off-skill"
PROFILE_ARM_V213_OFF: Final = "arm-v2.1.3-off"
PROFILE_ARM_V213_ON: Final = "arm-v2.1.3-on"
PROFILE_ARM_V213_ADAPTIVE: Final = "arm-v2.1.3-adaptive"
PROFILE_ARM_V213_FORCED_AB: Final = "arm-v2.1.3-forced-ab"
PROFILE_ARM_V213_OFF_SKILL: Final = "arm-v2.1.3-off-skill"
PROFILE_ARM_V214_OFF: Final = "arm-v2.1.4-off"
PROFILE_ARM_V214_ADAPTIVE: Final = "arm-v2.1.4-adaptive"
PROFILE_ARM_V214_CFR: Final = "arm-v2.1.4-cfr"
PROFILE_ARM_V215_BOUNDED_TAIL: Final = "arm-v2.1.5-bounded-tail"
PROFILE_ARM_V216_MISSING_CANDIDATE: Final = "arm-v2.1.6-missing-candidate"
PROFILE_ARM_V217_STRUCTURED_CONFIRMATION: Final = "arm-v2.1.7-structured-confirmation"
PROFILE_ARM_V218_COMPACT_FINALIZER: Final = "arm-v2.1.8-compact-finalizer"
PROFILE_ARM_V219_INCUMBENT_GUARD: Final = "arm-v2.1.9-incumbent-guard"
PROFILE_ARM_V220_ANSWER_COMMIT: Final = "arm-v2.2-answer-commit"
PROFILE_ARM_V223_PRIMARY_TAIL: Final = "arm-v2.3-primary-tail"
PROFILE_ARM_V224_RISK_GATED: Final = "arm-v2.4-risk-gated"
PROFILE_ARM_V224_CFR_PRESSURE: Final = "cfr-v2.4-risk-pressure"
ARM_V21_REQUEST_TIMEOUT_SECONDS: Final = 600
PROFILE_NAMES: Final = (
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
    PROFILE_ARM_V217_STRUCTURED_CONFIRMATION,
    PROFILE_ARM_V218_COMPACT_FINALIZER,
    PROFILE_ARM_V219_INCUMBENT_GUARD,
    PROFILE_ARM_V220_ANSWER_COMMIT,
    PROFILE_ARM_V223_PRIMARY_TAIL,
    PROFILE_ARM_V224_RISK_GATED,
    PROFILE_ARM_V224_CFR_PRESSURE,
)


def _build_arm_v21_submission_config(
    solver_mode: str,
    *,
    enable_skill: bool = False,
    trust_policy: str = "legacy",
) -> AgentConfig:
    """Wrap the official submission profile with the v2.1 ARM overlay."""
    return replace(
        SUBMISSION_CONFIG,
        enable_arm_harness=True,
        arm_harness_version="v2",
        arm_v2_mode="selective",
        enable_constraint_fit_hybrid_router=True,
        arm_solver_reasoning_mode=solver_mode,
        arm_trust_policy=trust_policy,
        arm_allow_thinking_on=False,
        arm_primary_timeout_seconds=ARM_V21_REQUEST_TIMEOUT_SECONDS,
        arm_enable_skill_guidance=enable_skill,
        arm_enable_skill_for_second=False,
        arm_enable_skill_audit=enable_skill,
        arm_max_skill_audits=1,
        arm_timeout_recovery_mode="none",
        arm_default_lane="adaptive",
    )


def available_profiles() -> tuple[str, ...]:
    """Return the profile names accepted by local runners."""

    return PROFILE_NAMES


def build_submission_arm_config(mode: str) -> AgentConfig:
    """Build the submission-equivalent ARM v2.1.2 mode for local runs."""
    normalized = mode.strip().lower()
    if normalized.startswith("arm-v2.1.2-"):
        normalized = normalized.rsplit("-", 1)[-1]
    if normalized not in {"off", "on", "adaptive"}:
        raise ValueError(f"unknown_arm_v212_mode:{mode!r}")
    return build_submission_config(f"arm-v2.1.2-{normalized}")


def build_arm_v213_config(
    mode: str,
    *,
    force_ab: bool = False,
    enable_skill: bool = False,
) -> AgentConfig:
    """Build a default-off v2.1.3 experiment configuration."""
    config = build_submission_arm_config(mode)
    if mode.strip().lower().rsplit("-", 1)[-1] == "off":
        config = replace(config, enable_constraint_fit_hybrid_router=False)
    return replace(
        config,
        arm_harness_version="v2.1.3",
        arm_trust_policy="positive_evidence",
        arm_off_recovery_max_tokens=4096,
        arm_force_ab_diagnostic=force_ab,
        arm_enable_skill_guidance=enable_skill,
        arm_enable_skill_audit=enable_skill,
        arm_enable_skill_for_second=False,
    )


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
        return build_submission_config(SUBMISSION_MODE)
    if normalized == PROFILE_FSDF_BASELINE:
        return build_submission_config(SUBMISSION_FSDF)
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
        return _build_arm_v21_submission_config(solver_mode, enable_skill=enable_skill)
    arm_v212_profiles = {
        PROFILE_ARM_V212_OFF: ("off", False),
        PROFILE_ARM_V212_ON: ("on", False),
        PROFILE_ARM_V212_ADAPTIVE: ("adaptive", False),
        PROFILE_ARM_V212_OFF_SKILL: ("off", True),
    }
    if normalized in arm_v212_profiles:
        solver_mode, enable_skill = arm_v212_profiles[normalized]
        config = build_submission_arm_config(solver_mode)
        if enable_skill:
            return replace(
                config,
                arm_enable_skill_guidance=True,
                arm_enable_skill_audit=True,
            )
        return config
    arm_v213_profiles = {
        PROFILE_ARM_V213_OFF: ("off", False, False),
        PROFILE_ARM_V213_ON: ("on", False, False),
        PROFILE_ARM_V213_ADAPTIVE: ("adaptive", False, False),
        PROFILE_ARM_V213_FORCED_AB: ("off", True, False),
        PROFILE_ARM_V213_OFF_SKILL: ("off", False, True),
    }
    if normalized in arm_v213_profiles:
        mode, force_ab, enable_skill = arm_v213_profiles[normalized]
        return build_arm_v213_config(mode, force_ab=force_ab, enable_skill=enable_skill)
    arm_v214_profiles = {
        PROFILE_ARM_V214_OFF: "off",
        PROFILE_ARM_V214_ADAPTIVE: "adaptive",
        PROFILE_ARM_V214_CFR: "cfr",
    }
    if normalized in arm_v214_profiles:
        return build_submission_config(f"arm-v2.1.4-{arm_v214_profiles[normalized]}")
    if normalized == PROFILE_ARM_V215_BOUNDED_TAIL:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.1.5",
        )
    if normalized == PROFILE_ARM_V216_MISSING_CANDIDATE:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.1.6",
        )
    if normalized == PROFILE_ARM_V217_STRUCTURED_CONFIRMATION:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.1.7",
        )
    if normalized == PROFILE_ARM_V218_COMPACT_FINALIZER:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.1.8",
        )
    if normalized == PROFILE_ARM_V219_INCUMBENT_GUARD:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.1.9",
        )
    if normalized == PROFILE_ARM_V220_ANSWER_COMMIT:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.2",
        )
    if normalized == PROFILE_ARM_V223_PRIMARY_TAIL:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.3",
        )
    if normalized == PROFILE_ARM_V224_RISK_GATED:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            arm_harness_version="v2.4",
            harness_attempt_a_max_tokens=2_048,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    if normalized == PROFILE_ARM_V224_CFR_PRESSURE:
        return replace(
            build_submission_config("arm-v2.1.4-cfr"),
            harness_attempt_a_max_tokens=2_048,
            harness_attempt_b_max_tokens=4_096,
            harness_total_token_budget=16_384,
        )
    choices = ", ".join(PROFILE_NAMES)
    raise ValueError(f"unknown_profile:{profile!r}; choose one of: {choices}")
