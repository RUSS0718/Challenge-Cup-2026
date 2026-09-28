# ARM-Harness v1

ARM-Harness controls Intern-S2 reasoning mode per request. It is an experimental
Agent/Harness path; the official submission profile remains unchanged.

## Scope and activation

The path requires both `enable_constraint_fit_harness=True` and
`enable_arm_harness=True`. `AgentConfig` defaults ARM off, and
`SUBMISSION_CONFIG` does not enable it. Local profiles are available through
`main.py --profile`:

| Profile | Behavior |
| --- | --- |
| `arm-off` | Always sends explicit OFF requests. |
| `arm-on` | Starts with an explicit ON solve; any follow-up review uses OFF. |
| `arm-static` | Direct, high-confidence scalar/choice tasks use OFF; other tasks use ON. |
| `arm-adaptive` | Starts OFF and escalates to ON only when the first result is unresolved. |

The profiles are local experiment arms. They do not change the no-argument
`ReasoningAgent(client=official_client)` path.

## Request mode contract

`InternChatClient.chat()` accepts the keyword-only `reasoning_mode` values:

- `inherit`: use the client default, preserving existing callers;
- `off`: send `thinking_mode=false`;
- `on`: send `thinking_mode=true`.

Each request resolves its own mode. The client default is never mutated, so
concurrent OFF and ON calls cannot overwrite one another. Request diagnostics,
budget records, and candidate ledger entries record the selected mode without
storing prompts, responses, or credentials.

## Policy and budgets

The policy reuses `HostRouter`'s existing `ProblemContract` and answer type.
Direct, high-confidence scalar and choice tasks enter `fast_off`; other
contracts enter `adaptive`. `static` and `deep_on` are explicit local arms and
are never selected by the default adaptive policy.

| Lane | Initial mode | Follow-up | Maximum calls | Token budget |
| --- | --- | --- | ---: | ---: |
| `fast_off` | OFF | OFF recovery | 2 | 8,192 |
| `adaptive` | OFF | ON escalation when enabled, otherwise OFF recovery | 3 | 16,384 |
| `deep_on` | ON | OFF review only when unresolved | 3 | 16,384 |

All calls still pass through the existing per-solve wall-clock, call, and token
ledger. Stable candidates stop further solving. Adaptive escalation is based on
request failure, missing or rejected candidates, typed incompleteness,
truncation, or conflict. It does not use problem length, domain, or keywords as
an automatic ON trigger. The ON prompt independently solves from the original
problem and does not include the prior raw response. Conflicting candidates are
checked for deterministic equivalence, then may receive one bounded OFF critic
call; the critic can select an existing candidate but cannot create a third
answer.

## Evidence boundary

The trace records the selected lane, initial and escalation modes, hard budget,
per-call mode, candidate source mode, and escalation reason. This establishes
code-path behavior only. It does not establish endpoint health, answer accuracy,
or a submission promotion case. Those require separately frozen and paired
experiments; this implementation leaves `SUBMISSION_CONFIG` unchanged.
