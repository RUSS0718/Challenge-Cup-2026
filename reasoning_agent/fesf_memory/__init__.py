"""Runtime-only memory for one FESF solve.

The package deliberately contains no persistence or retrieval layer.  A new
``SolveMemory`` is constructed for every call to ``solve`` and is rendered
back into the next model message explicitly by the harness.
"""

from .solve_state import ClaimRecord, EvidenceRecord, CandidateRecord, SolveMemory

__all__ = ["ClaimRecord", "EvidenceRecord", "CandidateRecord", "SolveMemory"]
