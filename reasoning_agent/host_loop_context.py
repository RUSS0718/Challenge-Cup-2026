"""Opt-in bridge from bounded intake to the FESF host loop.

The context exposes only coarse complexity hints and bounded obligation
records.  Metadata values and the problem hash stay out of model prompts; the
current default configuration does not construct this context at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .fesf_obligations import ObligationExtraction, extract_bounded_obligations
from .host_intake import HostIntake, build_host_intake


@dataclass(frozen=True)
class HostLoopContext:
    intake: HostIntake
    obligations: ObligationExtraction

    def prompt_hints(self, max_chars: int = 1_800) -> str:
        """Render non-authoritative hints for a model routing prompt."""

        complexity = self.intake.complexity
        lines = [
            "HOST_HINTS (非答案证据，仅用于选择检查路径):",
            f"profile={complexity.profile}; equations={complexity.equation_count}; variables={complexity.variable_count}; "
            f"proof={str(complexity.has_proof_language).lower()}; universal={str(complexity.has_universal_language).lower()}; "
            f"parts={str(complexity.has_multiple_parts).lower()}",
        ]
        if self.obligations.obligations:
            lines.append("OBLIGATIONS:")
            for item in self.obligations.obligations:
                lines.append(f"{item.id} [{item.kind}; {item.state}]: {item.text}")
        else:
            lines.append("OBLIGATIONS: none (bounded extractor disabled or no supported signal)")
        text = "\n".join(lines)
        return text[: max(0, int(max_chars))]

    def trace_event(self) -> dict[str, Any]:
        """Return safe diagnostics without raw metadata or problem text."""

        return {
            "stage": "host_intake",
            "status": "ok",
            "profile": self.intake.complexity.profile,
            "obligation_count": len(self.obligations.obligations),
            "obligation_truncated": self.obligations.truncated,
            "metadata_rejections": len(self.intake.metadata_rejections),
        }


def prepare_host_loop_context(
    problem: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    answer_type: str = "",
    extract_obligations: bool = False,
) -> HostLoopContext:
    """Build an opt-in context; no model call or persistence occurs."""

    intake = build_host_intake(problem, metadata, answer_type=answer_type)
    obligations = (
        extract_bounded_obligations(intake.problem, source="host-intake")
        if extract_obligations
        else ObligationExtraction(())
    )
    return HostLoopContext(intake=intake, obligations=obligations)


__all__ = ["HostLoopContext", "prepare_host_loop_context"]
