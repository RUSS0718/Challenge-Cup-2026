"""Select an ARM harness implementation from one solve-local version.

The orchestrator owns budgets and client dispatch; this module owns only the
version-to-class boundary so adding an opt-in ARM experiment does not grow the
large orchestration module's dispatch cascade.
"""

from __future__ import annotations

from typing import Any


def build_arm_harness(harness: Any) -> Any:
    """Build the configured ARM harness using lazy imports.

    Lazy imports keep legacy profiles importable even when an experimental
    harness is not selected. Unknown versions fall back to the original ARM
    implementation, matching the pre-factory dispatch behavior.
    """
    version = str(getattr(harness.config, "arm_harness_version", "v1"))
    if version == "v2.1.5":
        from reasoning_agent.arm_harness_v215 import AdaptiveReliabilityHarnessV215

        return AdaptiveReliabilityHarnessV215(harness)
    if version == "v2.1.6":
        from reasoning_agent.arm_harness_v216 import AdaptiveReliabilityHarnessV216

        return AdaptiveReliabilityHarnessV216(harness)
    if version == "v2.1.7":
        from reasoning_agent.arm_harness_v217 import AdaptiveReliabilityHarnessV217

        return AdaptiveReliabilityHarnessV217(harness)
    if version == "v2.1.8":
        from reasoning_agent.arm_harness_v218 import AdaptiveReliabilityHarnessV218

        return AdaptiveReliabilityHarnessV218(harness)
    if version == "v2.1.9":
        from reasoning_agent.arm_harness_v219 import AdaptiveReliabilityHarnessV219

        return AdaptiveReliabilityHarnessV219(harness)
    if version == "v2.1.4":
        from reasoning_agent.arm_harness_v214 import AdaptiveReliabilityHarnessV214

        return AdaptiveReliabilityHarnessV214(harness)
    if version == "v2.1.3":
        from reasoning_agent.arm_harness_v213 import AdaptiveReliabilityHarnessV213

        return AdaptiveReliabilityHarnessV213(harness)
    if version == "v2":
        from reasoning_agent.arm_harness_v2 import AdaptiveReliabilityHarness

        return AdaptiveReliabilityHarness(harness)
    from reasoning_agent.arm_harness import AdaptiveReasoningHarness

    return AdaptiveReasoningHarness(harness)


__all__ = ["build_arm_harness"]
