"""Risk-gated answer reservation for ARM experiments.

This module keeps the v2.1.4 CFR state machine and applies the v2.2
answer-first prompt only when the host route signals structured/deep reasoning
or low confidence.  Direct, high-confidence problems retain the established
primary prompt so the output-safety intervention does not rewrite every task.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v220 import (
    ARM_V220_ANSWER_COMMIT_PROMPT,
    AdaptiveReliabilityHarnessV220,
)
from reasoning_agent.arm_v214_support import ARM_V21_PRIMARY_PROMPT


class AdaptiveReliabilityHarnessV224(AdaptiveReliabilityHarnessV220):
    """Reserve an answer slot only for routes exposed to length risk."""

    def __init__(self, harness: Any) -> None:
        """Bind the route gate to one solve without changing global config."""
        super().__init__(harness)
        self._risk_gate_active = False

    @staticmethod
    def _should_reserve_answer(route: Any) -> tuple[bool, str, str]:
        """Return the bounded route decision used by the prompt selector."""
        contract = getattr(route, "contract", route)
        risk = str(getattr(contract, "reasoning_risk", "unknown") or "unknown")
        confidence = str(getattr(contract, "route_confidence", "unknown") or "unknown")
        active = risk in {"structured", "deep"} or confidence != "high"
        return active, risk, confidence if confidence else "unknown"

    def _primary_prompt(
        self,
        problem: str,
        route: Any,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Select answer-first only for the route classes covered by the hypothesis."""
        active, risk, confidence = self._should_reserve_answer(route)
        self._risk_gate_active = active
        prompt = super()._primary_prompt(problem, route, trace, summary)
        summary["primary_prompt_variant"] = (
            "risk_gated_answer_commit_v1" if active else "v21_preserved"
        )
        summary["risk_gate"] = {
            "active": active,
            "reason": "risk_or_low_confidence" if active else "direct_high_confidence",
            "reasoning_risk": risk,
            "route_confidence": confidence,
        }
        trace.append(
            {
                "method": "arm_harness_v224",
                "stage": "risk_gated_answer_commit",
                "status": "activated" if active else "bypassed",
                "reason": "risk_or_low_confidence" if active else "direct_high_confidence",
                "reasoning_risk": risk,
                "route_confidence": confidence,
            }
        )
        return prompt

    def _primary_base_prompt(self) -> str:
        """Return the selected first-call contract for the current solve."""
        if self._risk_gate_active:
            return ARM_V220_ANSWER_COMMIT_PROMPT
        return ARM_V21_PRIMARY_PROMPT


__all__ = ["AdaptiveReliabilityHarnessV224"]
