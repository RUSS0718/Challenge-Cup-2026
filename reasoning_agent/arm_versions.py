"""Version registry for opt-in ARM harness implementations.

The registry keeps version validation separate from the large math-harness
orchestrator.  New experimental harnesses must remain explicit and default
off; adding a version here does not select it for the official submission.
"""

from __future__ import annotations


SUPPORTED_ARM_HARNESS_VERSIONS = frozenset(
    {
        "v1",
        "v2",
        "v2.1.3",
        "v2.1.4",
        "v2.1.5",
        "v2.1.6",
        "v2.1.7",
        "v2.1.8",
        "v2.1.9",
    }
)


def is_supported_arm_harness_version(version: str) -> bool:
    """Return whether ``version`` is an explicitly registered ARM variant."""
    return version in SUPPORTED_ARM_HARNESS_VERSIONS


__all__ = ["SUPPORTED_ARM_HARNESS_VERSIONS", "is_supported_arm_harness_version"]
