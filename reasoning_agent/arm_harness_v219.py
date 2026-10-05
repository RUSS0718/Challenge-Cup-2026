"""Opt-in incumbent-preserving gate for ARM v2.1.8 compact finalization.

The v2.1.9 candidate keeps the compact finalizer for missing or incomplete
answers, but returns to the original CFR Challenger whenever a complete
incumbent already exists.  This isolates the finalizer's recovery benefit from
unreviewed replacement of a usable answer.
"""

from __future__ import annotations

from typing import Any

from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214
from reasoning_agent.arm_harness_v218 import AdaptiveReliabilityHarnessV218
from reasoning_agent.harness_contracts import Candidate


class AdaptiveReliabilityHarnessV219(AdaptiveReliabilityHarnessV218):
    """Preserve complete incumbents before invoking the compact finalizer."""

    @staticmethod
    def _has_complete_incumbent(primary: Candidate | None) -> bool:
        """Return whether the primary candidate is safe to retain as incumbent."""
        return bool(
            primary is not None
            and getattr(primary, "structural_validity", "") == "valid"
            and getattr(primary, "answer_complete", False)
        )

    def _second_call_plan(
        self,
        problem: str,
        route: Any,
        primary: Candidate | None,
        trace: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> tuple[str, str, str, int]:
        """Use CFR Challenger for complete incumbents and finalizer otherwise."""
        if not self._has_complete_incumbent(primary):
            return super()._second_call_plan(problem, route, primary, trace, summary)

        stage, prompt, mode, tokens = AdaptiveReliabilityHarnessV214._second_call_plan(
            self,
            problem,
            route,
            primary,
            trace,
            summary,
        )
        generation = summary.get("candidate_generation_b")
        if isinstance(generation, dict):
            generation["incumbent_guard"] = True
            generation["replacement_policy"] = "cfr_review_required"
        trace.append(
            {
                "method": "arm_harness_v219",
                "stage": "incumbent_preserving_finalizer_gate",
                "status": "preserved",
                "reason": "complete_incumbent",
                "replacement_policy": "cfr_review_required",
            }
        )
        return stage, prompt, mode, tokens


__all__ = ["AdaptiveReliabilityHarnessV219"]
