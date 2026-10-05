---
status: preregistered
last_verified: 2026-10-05
supersedes: none
source_ref: codex/arm-v215-bounded-tail-recovery
---

# ARM v2.1.6 missing-candidate recovery

## Hypothesis

In the current CFR path, a primary response with no parseable candidate still
uses the Challenger prompt for the second call. That prompt asks the model to
review an empty candidate, so it cannot reliably form a fresh answer. A single
independent, bounded answer-formation call may reduce this control-plane
failure without changing the treatment of existing candidates.

## Single variable

- Candidate: `arm-v2.1.6-missing-candidate`.
- Baseline: `arm-v2.1.4-cfr`.
- The candidate changes only the second-call prompt when `primary is None`.
- Existing candidate, truncated-tail, conflict, trust, repair, and fresh-review
  paths delegate to v2.1.4 unchanged.
- The candidate remains opt-in; `SUBMISSION_CONFIG` stays `arm-v2.1.4-cfr`.

## Paired window

Run `C01`–`C10` with the shared matrix runner. Each candidate round is paired
with the baseline on the same five records and uses a separate endpoint
window. The window covers two complex subsets, two medium subsets, and one
official-like hard subset. `evaluation_scope=local_replay`; gold stays in the
host-side scorer.

```powershell
python scripts/run_robustness_matrix.py `
  --rounds C01,C02,C03,C04,C05,C06,C07,C08,C09,C10 `
  --matrix-id ARM-V2.1.6-MISSING-CANDIDATE-RECOVERY-20261005 `
  --output-dir artifacts/arm-v216-missing-candidate-recovery-20261005
```

## Gates

1. Void the window if a manifest is incomplete or either arm has a model-error
   rate above 10%.
2. The candidate must trigger `missing_candidate_recovery` at least once. If
   it never triggers, record `ENGINEERING_NOT_ACTIVATED` and draw no ability
   conclusion.
3. The candidate must not increase incorrect by more than two, average calls
   by more than 0.5, or exceed the v2.1.4 per-item call cap.
4. Continue only if invalid decreases by at least two without a net
   correct-to-incorrect reversal. Passing this exploratory gate does not
   authorize a default switch or an official claim.

## Evidence boundary

The result must record trigger count, primary/second parse states, final source,
finish reasons, paired transitions, and the exact manifest and dataset hashes.
It must not copy answers or raw model content into the committed report.
