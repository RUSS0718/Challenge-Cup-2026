"""Competition-shaped facade for the experimental EACL control plane."""

from __future__ import annotations

from typing import Any

from reasoning_agent.eacl_contracts import EACLConfig
from reasoning_agent.eacl_pipeline import EACLControlPlane


class EACLReasoningAgent:
    """Expose the standard ``solve(problem, metadata)`` seam for EACL."""

    def __init__(self, client: Any, config: EACLConfig | None = None, **_: Any) -> None:
        """Bind the public client while keeping per-question state ephemeral."""

        self.pipeline = EACLControlPlane(client, config=config)

    def solve(self, problem: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a JSON-serialisable result with a non-empty final response."""

        return self.pipeline.solve(problem, metadata or {})


__all__ = ["EACLReasoningAgent"]
