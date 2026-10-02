# MATH-HARNESS-CODE-ACCEPTANCE-001

- source spec: `docs/experiments/MATH-HARNESS-V1-SPEC/spec.md`
- spec SHA-256: `594329F14DD283BB71E663DE040E08B27AF4B09EF37E78C43481AF171431AD48`
- candidate: `bounded_evidence_trajectory_selection_v1`
- base commit: `7da72874a0e3708958278c0f9f26c95bf5c03497`
- acceptance mode: zero-model structural and contract tests
- frozen test runtime: Python 3.12.14, requests 2.34.2, SymPy 1.14.0
- temporary answer bank: off for the capability-shaped solve tests

The checkout contains unrelated pre-existing changes. This acceptance records the Harness
scope only and does not represent a clean-tree release snapshot.

Hard assertions:

- no more than five logical calls and 16,384 requested tokens per solve;
- no hidden retry, no arbitrary code/tool path, and no model-visible answer from metadata;
- A/B mutual blindness, conflict retention, explicit critic repair, and one-shot truncation recovery;
- state and budget are discarded between solves;
- malformed, timed-out, or unresolved paths return non-empty `UNKNOWN` semantics;
- default `AgentConfig` and `SUBMISSION_CONFIG` keep the new Harness disabled.
