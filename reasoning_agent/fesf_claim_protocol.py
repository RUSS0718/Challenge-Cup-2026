"""Narrow Claim DSL executor protocol for the FESF relay.

The relay depends only on this module.  The concrete parser/adapters live
behind a factory that is imported only when the opt-in switch is on.
"""

from __future__ import annotations

from typing import Any, Protocol

from .fesf_memory import SolveMemory


class ClaimExecutor(Protocol):
    """Host-owned verifier for one branch packet."""

    def verify(self, branch: str, packet_text: str, memory: SolveMemory) -> list[dict[str, Any]]:
        """Parse CLAIM_DSL/VERIFY_DSL lines, write evidence into *memory*, return trace extras."""


__all__ = ["ClaimExecutor"]
