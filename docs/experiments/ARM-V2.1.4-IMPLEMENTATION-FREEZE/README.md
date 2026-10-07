# ARM v2.1.4 implementation freeze

This is the historical post-implementation freeze for the isolated `arm-v2.1.4-*` profiles.
The historical v2.1.2 and v2.1.3 selectors remain separate and are hashed in the
manifest for regression comparison. This document records code identity only; it
does not claim a capability result or authorize an official submission.

- Protocol: `ARM-v2.1.4-implementation-freeze`
- Profiles: `arm-v2.1.4-off`, `arm-v2.1.4-adaptive`
- Challenger: structured JSON contract with fail-closed `UNKNOWN`
- Replacement: targeted repair plus Fresh Review `PASS` only
- Runtime budget: four calls for the v2.1.4 adaptive path
- Evaluation artifacts: remain under `artifacts/<run_id>/`

The earlier P0 manifest remains a historical pre-implementation anchor. This
freeze is superseded as the formal submission by
`ARM-V2.1.4-CFR-20261004` in `docs/releases/arm-v2.1.4-cfr-20261004/`; it remains
available only for regression comparison and must not be described as the CFR
selector.
