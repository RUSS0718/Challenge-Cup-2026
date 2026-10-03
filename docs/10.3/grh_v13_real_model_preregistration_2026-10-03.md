# GRH v1.3 real-model host replay preregistration

- Base: v1.1 release `43a02da` in the isolated v1.3 worktree.
- Dataset: frozen proxy221, expected 221 unique items; local gold is used only after `solve()`.
- Endpoint/model: the configured public client and resolved model; three `1+1` probes must pass first.
- Baseline: one v1.1 `ReasoningAgent.solve()` call per item, maximum three internal model calls and 16,384 requested tokens.
- Candidate: no additional model call; apply v1.3 host extraction, canonicalization, safe-incumbent and structural verification to the same response.
- Concurrency: three workers; one client per item; 600 second request timeout; six-hour hard stop.
- Primary metrics: `unknown → correct`, `unknown → incorrect`, `correct → incorrect`, `correct → unknown`, and net correct gain.
- Safety: stop/void on failed preflight, missing records, missing telemetry, runtime errors, or wall-clock breach. Do not modify `SUBMISSION_CONFIG`.
- Interpretation: this is a real-model host-replay experiment. It can test whether host recovery preserves or exposes existing answer evidence; it cannot establish a new mathematical capability claim without a later paired mechanism experiment.
