"""Default-off, deterministic verification adapters for the Host Loop.

Claim DSL lives in ``claim_dsl`` and is imported only by opt-in tests.  The
package export list stays limited to adapters so the default solve path cannot
pick up the DSL by importing this package.
"""

from .adapters import (
    CounterexampleAdapter,
    FiniteDomainAdapter,
    FiniteVerifierConfig,
    SymbolicConstraintAdapter,
    SymbolicVerifierConfig,
    VerificationResult,
)

__all__ = [
    "CounterexampleAdapter",
    "FiniteDomainAdapter",
    "FiniteVerifierConfig",
    "SymbolicConstraintAdapter",
    "SymbolicVerifierConfig",
    "VerificationResult",
]
