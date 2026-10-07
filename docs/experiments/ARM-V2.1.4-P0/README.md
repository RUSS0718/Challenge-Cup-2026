# ARM v2.1.4 Correctness-First — P0 Protocol Freeze (historical)

This freeze records the implementation anchor for the v2.1.4 workstream. It is a protocol artifact, not a capability result.

- **Protocol:** `ARM-v2.1.4-correctness-first-P0`
- **Method:** `ARM-v2.1.4`
- **Frozen commit:** see `manifest.json`
- **Submission selector at freeze:** `arm-v2.1.3-off` (historical; superseded by `arm-v2.1.4-cfr`)
- **Dataset:** no new evaluation dataset is introduced by P0. Existing local fixtures remain subject to the repository rules.
- **Answer bank:** `reasoning_agent/error_notebook/eval_112.json` is local and untracked; runtime reads remain disabled by default.
- **Artifact rule:** new run outputs belong under `artifacts/<run_id>/`; this freeze does not copy or overwrite prior raw outputs.

The manifest hashes the current parser, candidate, state, verification, diagnostics, harness, entrypoint, smoke fixture, and exclusion registry inputs. Any change to those inputs requires a new protocol or method identifier.

Pre-existing working-tree modifications were present when this freeze was created. They are intentionally not included in the freeze and are not modified by this workstream.
