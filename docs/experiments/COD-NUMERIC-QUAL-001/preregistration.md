# COD-NUMERIC-QUAL-001

**Status:** `PREREGISTERED / DEFAULT_OFF / NO_CAPABILITY_CONCLUSION`

**Method ID:** `current_cod_numeric`

## 1. Hypothesis and boundary

On the C0/legacy answering path, a compact Chain-of-Draft prompt may reduce
completion tokens and wall-clock time without changing the call budget,
temperature, answer extraction, candidate selection, or non-numeric behavior.
This experiment does not integrate CoD into FSDF and does not change
`SUBMISSION_CONFIG`.

The prompt is universal and contains no item id, answer, or dataset-specific
instruction. It applies only when the text classifier returns
`calculation`, `fill_blank`, or `choice`.

## 2. Arms

| Arm | Path | Difference |
|---|---|---|
| `current_c0` | C0/legacy | baseline prompt and legacy pipeline |
| `current_cod_numeric` | C0/legacy | `enable_current_cod_numeric=True` for numeric/choice tasks only |

Both arms pin: `enable_fork_select_deepen_finish=False`, all FSDF/FESF/CAR
paths off, `enable_heterogeneous_reasoners=False`, adaptive voting on with
`vote_k_max=5` and threshold 3, `max_model_calls=5`, `max_tokens=4096`,
`l0_max_tokens=4096`, temperature `0.6`, official default thinking, and
`enable_temporary_answer_bank=False`.

The candidate prompt hash is:

```text
COD_NUMERIC_PROMPT_SHA256=5e4fdaf4dade16f609be49b876ada8791fadd99be5c9209c525a6409930a9121
```

The baseline policy prompt hash is:

```text
POLICY_PROMPT_SHA256=42e05bb09bdb46fde6b191ef1f2d6e251041cb54260bac8dd245cea08daadbe2
```

## 3. Frozen data

The complete selection is in `frozen_selection.json`.

- Numeric smoke: 10 previously unused `set_a_olymmath_hard` items, one per
  problem group, with four domains and ZH/EN balanced 5/5. The set is used for
  paired local diagnostics, not as a claim about the hidden evaluation set.
- Non-numeric parity: the three rows in
  `sample_data/cod_numeric_parity.jsonl` are synthetic, public, and used only
  to verify that proof/derivation/explanation routes remain unchanged.
- Gold answers are scorer/manifest data only; they are never passed to
  `ReasoningAgent.solve()` or model messages. Both arms have the answer bank
  disabled.

## 4. Gates

### P0 code gate

Before model requests, all of the following must pass:

1. CoD is off by default and absent from `SUBMISSION_CONFIG`.
2. Numeric/choice requests use the CoD prompt only in the candidate arm.
3. Proof, derivation, and explanation requests have identical requests and
   `final_response` under a scripted client.
4. Candidate and baseline have identical call count, temperature, token
   limits, extraction, and selection behavior on the scripted numeric case.
5. CoD combined with FSDF fails closed before a model request.
6. The fixture and frozen selection parse, all selected numeric rows classify as
   `calculation`, and all parity rows classify as their declared non-numeric
   type.
7. Targeted and full zero-model tests, `py_compile`, and `git diff --check`
   pass.

### P1 resource preflight

Three sequential independent requests, `max_tokens=2048`, timeout 240 seconds,
official default thinking. Require 3/3 non-empty responses, 0 timeout, 0 client
error, and 0 invalid response.

### P2 health window

Run the two arms same-question paired/interleaved with 3 workers, one window,
240-second request timeout, and 120-minute hard stop. Require per arm:

- 26/26 durable records and 0 skipped tasks;
- 0 top-level runner errors and all records JSON-serializable;
- at most 2 legacy timeout/client-error events in total, with timeout and
  non-timeout client error reported separately;
- 0 context-overflow events and no answer-bank hit.

Any health failure is `VOID / HEALTH_UNHEALTHY / NO_CAPABILITY_CONCLUSION`.
Preserve all records and do not rerun, tune, or start another phase.

### P3 numeric smoke

Use only the 10 numeric paired items for these gates:

- candidate native correct count is no more than 1 below baseline;
- candidate `invalid + error` is no greater than baseline;
- candidate mean completion tokens are at most 60% of baseline;
- candidate nearest-rank P95 wall-clock is at most 70% of baseline;
- report native/contract mismatch and all stage/request diagnostics separately.

The three parity rows are checked for route/prompt parity and are not included
in numeric capability or token gates. A smoke failure archives the candidate;
the two-round independent A/B window is not started.

No result from this window, including a zero or positive local correct count,
authorizes a default change or an official capability claim. Only a separately
registered two-round A/B pass could make the candidate eligible for review.

## 5. Execution and stop rules

Execution order is `P0 → P1 → P2/P3 → finalize`. The run must use the clean
implementation snapshot recorded in `run_manifest.json`, and the answer bank
must remain off in both arms. Do not run CoD and Re2/PS+ in the same window.

If CoD fails the token/wall-clock target or causes a correct-answer reversal,
archive it and register Re2 separately; do not automatically start Re2.

## 6. Implementation snapshot

```text
implementation_commit: e2bb296
worktree: clean temporary worktree required for execution
```
