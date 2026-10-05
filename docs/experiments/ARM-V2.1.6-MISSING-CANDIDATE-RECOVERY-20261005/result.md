---
status: no-go
last_verified: 2026-10-05
supersedes: preregistration.md
source_ref: codex/arm-v215-bounded-tail-recovery
---

# ARM v2.1.6 missing-candidate recovery — result

## Window summary

The ten paired rounds completed with 50 records, 90 model calls, and 0 model
errors. The candidate and baseline used the same five paired subsets:

| Arm | Correct | Incorrect | Invalid | Average calls |
| --- | ---: | ---: | ---: | ---: |
| `arm-v2.1.6-missing-candidate` | 20 | 4 | 1 | 1.80 |
| `arm-v2.1.4-cfr` | 19 | 5 | 1 | 1.80 |

The only paired transition was one `incorrect → correct`; there was no invalid
reduction, no correct-to-incorrect damage, and no model error. The candidate
triggered `missing_candidate_recovery` **once out of 25 candidate records**.

## Decision

`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`.

The invalid-reduction gate failed, and the mechanism was nearly inactive. The
single positive transition is therefore compatible with sampling variance and
cannot be attributed to the new prompt. The v2.1.6 profile remains explicit and
default-off; `SUBMISSION_CONFIG` remains `arm-v2.1.4-cfr`.

## Evidence boundary

All records are `local_replay`, not an official hidden-set result. The run was
created while the checkout contained unrelated untracked historical audit files,
so it is diagnostic evidence rather than a clean promotion window. Complete
answers, manifests, and traces remain under the ignored
`artifacts/arm-v216-missing-candidate-recovery-20261005/` directory.
