"""Build official-equivalent submission configurations from one base.

This module owns only submission configuration composition.  The public
``user_agent`` facade supplies ``AgentConfig`` as the factory so configuration
construction stays separate from the large solve implementation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Final


SUBMISSION_FSDF: Final = "fsdf"
SUBMISSION_ARM_V212_OFF: Final = "arm-v2.1.2-off"
SUBMISSION_ARM_V212_ON: Final = "arm-v2.1.2-on"
SUBMISSION_ARM_V212_ADAPTIVE: Final = "arm-v2.1.2-adaptive"
SUBMISSION_ARM_V213_OFF: Final = "arm-v2.1.3-off"
SUBMISSION_ARM_V213_ON: Final = "arm-v2.1.3-on"
SUBMISSION_ARM_V213_ADAPTIVE: Final = "arm-v2.1.3-adaptive"
SUBMISSION_MODES: Final = (
    SUBMISSION_FSDF,
    SUBMISSION_ARM_V212_OFF,
    SUBMISSION_ARM_V212_ON,
    SUBMISSION_ARM_V212_ADAPTIVE,
    SUBMISSION_ARM_V213_OFF,
    SUBMISSION_ARM_V213_ON,
    SUBMISSION_ARM_V213_ADAPTIVE,
)
ARM_V212_MODES: Final = ("off", "on", "adaptive")
ARM_V213_MODES: Final = ("off", "on", "adaptive")
ConfigFactory = Callable[..., Any]


def _build_fsdf_config(config_factory: ConfigFactory) -> Any:
    """Construct the unchanged FSDF official baseline."""
    return config_factory(
        policy_sample_times=1,
        policy_temperature=0.6,
        verifier_voting_times=0,
        enable_dynamic_budget=False,
        enable_l0_extended_tokens=True,
        enable_task_aware_prompt=True,
        enable_time_convergence=True,
        enable_adaptive_voting=True,
        vote_k_max=5,
        vote_agree_threshold=3,
        enable_verification_gated_retry=False,
        enable_truncation_recovery_prompt=False,
        max_model_calls=5,
        max_tokens=4096,
        l0_max_tokens=4096,
        enable_heterogeneous_reasoners=True,
        enable_step_verification=False,
        enable_step_revision=False,
        enable_method_rag=False,
        enable_reference_rag=False,
        enable_reference_skills=False,
        enable_deterministic_solver=False,
        enable_numeric_answer_first_prompt=True,
        enable_numeric_answer_only_prompt=False,
        enable_strict_numeric_salvage=False,
        enable_conditional_token_retry=False,
        enable_failure_retry_backoff=False,
        enable_explicit_answer_conflict_retry=False,
        enable_l2_routing=False,
        enable_local_repair=False,
        enable_uncertain_repair=False,
        enable_sympy_evidence=False,
        enable_temporary_answer_bank=False,
        enable_constraint_fit_harness=True,
        enable_constraint_fit_deep_lane=True,
        enable_constraint_fit_hybrid_router=True,
        harness_bank_mode="off",
        enable_stateful_tail_completion=False,
        enable_contextual_answer_reconstruction=False,
        reconstruction_max_tokens=4096,
        reconstruction_context_max_chars=12000,
        enable_fork_select_deepen_finish=True,
        enable_fsdf_diagnostics_v2=False,
        enable_fsdf_multiline_handoff_v2=False,
        enable_fsdf_final_confirmation_v2=False,
        enable_fsdf_finish_prompt_v2=False,
        enable_fsdf_handoff_first_d=False,
        enable_fsdf_d_result_to_e=False,
        enable_fesf_v1=False,
        enable_fesf_exact_eval=False,
        enable_fesf_claim_dsl=False,
    )


def build_arm_v212_base_config(config_factory: ConfigFactory) -> Any:
    """Build the shared ARM v2.1.2 base before selecting OFF/ON/adaptive."""
    return replace(
        _build_fsdf_config(config_factory),
        enable_arm_harness=True,
        arm_harness_version="v2",
        arm_v2_mode="selective",
        arm_solver_reasoning_mode="off",
        arm_trust_policy="evidence",
        arm_primary_prompt_variant="v21",
        arm_allow_thinking_on=False,
        arm_primary_timeout_seconds=600,
        arm_enable_skill_guidance=False,
        arm_enable_skill_for_second=False,
        arm_enable_skill_audit=False,
        arm_max_skill_audits=1,
        arm_timeout_recovery_mode="none",
        arm_default_lane="adaptive",
    )


def build_arm_v213_base_config(config_factory: ConfigFactory) -> Any:
    """Build the explicit v2.1.3 base used only by authorized modes."""
    return replace(
        build_arm_v212_base_config(config_factory),
        arm_harness_version="v2.1.3",
        arm_trust_policy="positive_evidence",
        arm_off_recovery_max_tokens=4096,
        arm_force_ab_diagnostic=False,
    )


def build_submission_config(
    mode: str,
    config_factory: ConfigFactory,
    *,
    arm_base: Any | None = None,
) -> Any:
    """Build one explicit official-equivalent submission mode.

    ``config_factory`` is injected by ``user_agent`` to avoid importing the
    facade back into this module.  ARM modes differ only in their request-local
    reasoning policy; all other fields come from the shared base.

    Raises:
        ValueError: If ``mode`` is not one of ``SUBMISSION_MODES``.
    """
    normalized = str(mode).strip().lower()
    if normalized == SUBMISSION_FSDF:
        return _build_fsdf_config(config_factory)
    if normalized not in SUBMISSION_MODES:
        choices = ", ".join(SUBMISSION_MODES)
        raise ValueError(f"unknown_submission_mode:{mode!r}; choose one of: {choices}")

    is_v213 = normalized in {
        SUBMISSION_ARM_V213_OFF,
        SUBMISSION_ARM_V213_ON,
        SUBMISSION_ARM_V213_ADAPTIVE,
    }
    base = (
        build_arm_v213_base_config(config_factory)
        if is_v213
        else arm_base if arm_base is not None else build_arm_v212_base_config(config_factory)
    )
    arm_mode = normalized.rsplit("-", 1)[-1]
    return replace(
        base,
        arm_solver_reasoning_mode=arm_mode,
        arm_allow_thinking_on=arm_mode == "adaptive",
    )


__all__ = [
    "ARM_V212_MODES",
    "ARM_V213_MODES",
    "SUBMISSION_ARM_V212_ADAPTIVE",
    "SUBMISSION_ARM_V212_OFF",
    "SUBMISSION_ARM_V212_ON",
    "SUBMISSION_ARM_V213_ADAPTIVE",
    "SUBMISSION_ARM_V213_OFF",
    "SUBMISSION_ARM_V213_ON",
    "SUBMISSION_FSDF",
    "SUBMISSION_MODES",
    "build_arm_v212_base_config",
    "build_arm_v213_base_config",
    "build_submission_config",
]
