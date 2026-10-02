"""Runtime-only recovery decisions for the ARM v2 solve path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


RuntimeFailure = Literal["timeout", "request_error", "empty_response"]
RuntimeRecoveryAction = Literal["retry_longer", "compact_salvage", "abstain"]
RECOVERY_MODES = frozenset({"repeat", "longer_first", "compact_salvage", "none"})


@dataclass(frozen=True)
class RuntimeRecoveryDecision:
    """Bounded action taken after a transport or response failure."""

    action: RuntimeRecoveryAction
    max_tokens: int
    timeout_seconds: int
    reason: str


class RuntimeRecoveryPolicy:
    """Map runtime failures to a profile-controlled, finite recovery call."""

    def __init__(
        self,
        mode: str = "compact_salvage",
        *,
        salvage_max_tokens: int = 1_024,
        salvage_timeout_seconds: int = 15,
        longer_timeout_seconds: int = 60,
        default_timeout_seconds: int = 30,
    ) -> None:
        """Freeze recovery parameters without mutating a shared client."""
        if mode not in RECOVERY_MODES:
            raise ValueError("invalid_arm_timeout_recovery_mode")
        if any(int(value) <= 0 for value in (
            salvage_max_tokens,
            salvage_timeout_seconds,
            longer_timeout_seconds,
            default_timeout_seconds,
        )):
            raise ValueError("runtime_recovery_limits_must_be_positive")
        self.mode = mode
        self.salvage_max_tokens = int(salvage_max_tokens)
        self.salvage_timeout_seconds = int(salvage_timeout_seconds)
        self.longer_timeout_seconds = int(longer_timeout_seconds)
        self.default_timeout_seconds = int(default_timeout_seconds)

    def decide(
        self,
        failure: RuntimeFailure,
        *,
        current_max_tokens: int,
        current_timeout_seconds: int | None,
        remaining_calls: int,
        remaining_tokens: int,
    ) -> RuntimeRecoveryDecision:
        """Choose one recovery action, or abstain when it cannot fit the budget."""
        if failure not in {"timeout", "request_error", "empty_response"}:
            raise ValueError("invalid_runtime_failure")
        if remaining_calls <= 0 or remaining_tokens <= 0:
            return RuntimeRecoveryDecision("abstain", 0, 0, "budget_exhausted")
        if self.mode == "none":
            return RuntimeRecoveryDecision("abstain", 0, 0, "runtime_recovery_disabled")

        if self.mode == "compact_salvage":
            tokens = min(self.salvage_max_tokens, int(remaining_tokens))
            if tokens <= 0:
                return RuntimeRecoveryDecision("abstain", 0, 0, "budget_exhausted")
            return RuntimeRecoveryDecision(
                "compact_salvage",
                tokens,
                self.salvage_timeout_seconds,
                f"{failure}_compact_salvage",
            )

        tokens = min(max(1, int(current_max_tokens)), int(remaining_tokens))
        if tokens <= 0:
            return RuntimeRecoveryDecision("abstain", 0, 0, "budget_exhausted")
        if self.mode == "longer_first":
            timeout = max(self.longer_timeout_seconds, int(current_timeout_seconds or 0))
        else:
            timeout = int(current_timeout_seconds or self.default_timeout_seconds)
        return RuntimeRecoveryDecision("retry_longer", tokens, timeout, f"{failure}_{self.mode}")


def classify_runtime_failure(call_result: Any) -> RuntimeFailure | None:
    """Convert a call result into a runtime category before trust is evaluated."""
    category = getattr(call_result, "error_category", None)
    if category == "timeout":
        return "timeout"
    if category is not None:
        return "request_error"
    if getattr(call_result, "content", None) is None:
        return "empty_response"
    return None


__all__ = [
    "RECOVERY_MODES",
    "RuntimeFailure",
    "RuntimeRecoveryDecision",
    "RuntimeRecoveryPolicy",
    "classify_runtime_failure",
]
