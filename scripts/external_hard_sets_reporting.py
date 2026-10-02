"""Compatibility exports for hard-set judgment, qualification, and reports.

New code should import the focused judging, qualification, or aggregation
module directly. This facade keeps existing runner and analysis imports stable.
"""

from scripts.external_hard_sets_aggregate import analyze, arm_v2_metrics, stage_health
from scripts.external_hard_sets_judging import (
    contract_check,
    extract_contract_answer,
    is_unknown_final,
    judge,
    math_verify_ok,
    normalize_answer,
)
from scripts.external_hard_sets_qualification import (
    analyze_claim_dsl_qualification,
    analyze_skill_qualification,
)

__all__ = [
    "analyze",
    "analyze_claim_dsl_qualification",
    "analyze_skill_qualification",
    "arm_v2_metrics",
    "contract_check",
    "extract_contract_answer",
    "is_unknown_final",
    "judge",
    "math_verify_ok",
    "normalize_answer",
    "stage_health",
]
