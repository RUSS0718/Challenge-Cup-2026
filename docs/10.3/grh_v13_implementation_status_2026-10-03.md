# GRH v1.3 implementation status (2026-10-03)

This checkout is based on the v1.1 release commit `43a02da`. The existing v1.2
workspace remains untouched and is used only as an evidence and patch reference.
No submission selector, default profile, remote branch, or official candidate was
changed.

## Completed in this checkout

P0 and P1 are implemented as gold-free host tooling:

- `reasoning_agent/answer_contract.py` defines `TaskContract`, `Candidate`,
  completeness, and verification states.
- `reasoning_agent/candidate_canonicalizer.py` implements the fixed parser order,
  source tracking, raw-span hashes, bounded surface normalization, and conflict
  rejection.
- `reasoning_agent/invalid_recovery.py` implements R1–R6, S1–S6, and fail-closed
  recovery decisions.
- `reasoning_agent/invalid_ledger.py` and `scripts/audit_invalid_ledger.py`
  create compact ledgers without copying full responses or gold answers.
- `scripts/replay_invalid_rescue.py` replays parser and incumbent decisions without
  model calls and without changing source artifacts.
- `reasoning_agent/finalizer.py` provides a single OFF finalizer contract that can
  only return the existing canonical value or `UNKNOWN`.
- `reasoning_agent/verification_gates.py` provides structural deterministic checks;
  unsupported mathematics remains `UNKNOWN`.
- `reasoning_agent/grh_v13.py` composes the opt-in host pipeline while keeping
  model dispatch outside the module and outside the v1.1 default facade.
- `docs/10.3/fixtures/invalid_ledger.schema.json` freezes the ledger shape.

## Offline evidence

The v1.1 R3 artifact was replayed from:

`GRH-V11-PROXY221-THINKING-ON-20261003-R3/answers.jsonl`

The run produced 221/221 ledger records and 221/221 replay records with zero
remote model calls. The saved v1.1 verdict distribution was 106 correct, 10
incorrect, and 105 unknown/invalid. Within the 105 invalid pool, the host-only
classification was:

| failure class | count |
| --- | ---: |
| R1 reasoning failure | 6 |
| R2 decision failure | 10 |
| R4 parser/contract failure | 19 |
| R6 timeout/truncation/health | 70 |
| unresolved/unknown | 19 |

The replay marked 86 invalid rows as eligible for a host action: 68 safe
incumbent preservations and 18 serialization-only replays. It did not claim any
new correct answer because no gold or evaluator was supplied to the recovery
path. The run directories are local ignored artifacts:

- `artifacts/GRH-V13-P0-LEDGER-20261003-run4`
- `artifacts/GRH-V13-P1-REPLAY-20261003-run1`

## Intentionally not claimed

P2–P5 are not promoted by this change. There was no new model call, no OFF
finalizer experiment, no deterministic mathematical correctness claim, no
adaptive router, and no change to `SUBMISSION_CONFIG`. A host replay can show
that a candidate is structurally recoverable; it cannot prove that the candidate
is mathematically correct.

## Validation

The sixteen new contract/recovery/finalizer/verification tests pass, and the
repository suite reaches 1,069 tests with four archived skips. Two pre-existing
v1.1 dataset tests cannot run from this clean v1.1 checkout because the ignored
local `reasoning_agent/error_notebook/eval_112.json` fixture is absent; this is a
fixture availability issue, not a v1.3 implementation failure.
