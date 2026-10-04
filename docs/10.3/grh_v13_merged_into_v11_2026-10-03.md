# GRH v1.3 merged into the v1.1 formal workspace

Date: 2026-10-03

## Merge record

- Source worktree: `Challenge-Cup-2026-grh-v13`
- Source commit: `0995240`
- Target worktree: `Challenge-Cup-2026-v11-release`
- Target commit: `c1c02e8`
- Common v1.1 base: `43a02da`

The v1.3 host-recovery implementation is now present in the v1.1 formal
workspace. It adds a gold-free answer contract, deterministic candidate
canonicalization, fail-closed invalid classification, structural verification,
compact ledgers, replay tooling, and regression tests.

## Promotion boundary

The v1.3 modules remain opt-in. The formal v1.1 submission selector and ARM
runtime are unchanged because the v1.3 acceptance audit is `NOT READY / FAIL`:
the real-model replay did not satisfy the required telemetry, budget, holdout,
and paired capability gates. The six safe host replays in the offline audit are
evidence-preservation cases; they are not a measured mathematical accuracy
gain.

The v1.2 development workspace is retained at its existing path as read-only
evidence and is deprecated as a development entry point. It is not deleted or
reset because it contains uncommitted experiment history.

## Verification

The merged workspace passes:

```text
1066 passed, 4 skipped, 183 subtests passed
```

The v1.3 smoke contract also confirms that a closed integer candidate can be
recovered without a model call, while a conflicting candidate remains
fail-closed.

## Next promotion gate

Before changing the formal selector, repair the real-model runner's hard VOID
and telemetry handling, run two interleaved paired rounds, and require positive
`invalid -> correct` net gain with zero accepted `invalid -> incorrect` or
correct-answer damage under the frozen evaluator.
