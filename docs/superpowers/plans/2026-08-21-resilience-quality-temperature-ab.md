# Resilience, Quality, and Temperature A/B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure variance, then independently test failure backoff, explicit-answer conflict recovery, and main-call temperature.

**Architecture:** Keep F+4096 and the two-call ceiling. Two default-off `AgentConfig` toggles modify only the existing recovery branch; runner variants change exactly one dimension and persist safe aggregate metrics atomically.

**Tech Stack:** Python 3.10, `unittest`, dataclasses, existing local evaluator.

## Global Constraints

- Only public `client.chat(messages, temperature, max_tokens)` is used; no private client state.
- All experiment switches default off; normal submission behavior stays F+4096 at temperature 0.6.
- Workers are 1–3; per-item maximum calls is 2; reports hold no raw response text.
- Public candidates require paired R1/R2; only public-pass candidates run complex-freeze R1/R2.

---

### Task 1: Add resumable single-round runner invocation

**Files:** Modify `scripts/evaluate_protocol_ab.py`; modify `tests/test_evaluate_protocol_ab.py`.

**Produces:** `--variant NAME --round N --append-output`, which runs only the requested values and atomically appends one completed summary.

- [ ] Write a failing test:

```python
def test_parser_accepts_single_variant_round_and_append(self):
    args = parse_args(["--variant", "baseline86", "--round", "3", "--append-output"])
    self.assertEqual(["baseline86"], args.variants)
    self.assertEqual([3], args.rounds)
    self.assertTrue(args.append_output)
```

- [ ] Run `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m unittest tests.test_evaluate_protocol_ab.ProtocolRunnerTest.test_parser_accepts_single_variant_round_and_append`; expect failure because this parser API is absent.
- [ ] Implement `--variant`/`--round` with `action="append"`; retain current defaults if omitted. For append output: load existing JSON list, append after a successful round, write a sibling temporary file, then replace the target.
- [ ] Re-run `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m unittest tests.test_evaluate_protocol_ab`; expect pass.
- [ ] Commit: `git add scripts/evaluate_protocol_ab.py tests/test_evaluate_protocol_ab.py && git commit -m "feat: resume protocol experiment rounds"`.

### Task 2: Add failure-only delayed recovery

**Files:** Modify `user_agent.py`, `scripts/evaluate_protocol_ab.py`, `tests/test_user_agent.py`, `tests/test_evaluate_protocol_ab.py`.

**Produces:** `AgentConfig(enable_failure_retry_backoff=False, failure_retry_backoff_seconds=1.0)` and `failure_backoff` variant.

- [ ] Write a failing test:

```python
@patch("user_agent.time.sleep")
def test_failure_backoff_waits_only_after_model_error(self, sleep):
    client = FakeClient([RuntimeError("transient"), "最终答案：7"])
    result = ReasoningAgent(client, AgentConfig(enable_failure_retry_backoff=True)).solve("计算 3+4", {})
    sleep.assert_called_once_with(1.0)
    self.assertEqual("7", result["extracted_answer"])
```

- [ ] Run the focused test; expect failure from missing config/behavior.
- [ ] Immediately before the existing recovery call, add only:

```python
if self.config.enable_failure_retry_backoff and "model_error" in budget["diagnostic_reasons"]:
    time.sleep(self.config.failure_retry_backoff_seconds)
    trace.append({"step": "conditional_retry_backoff", "seconds": self.config.failure_retry_backoff_seconds})
```

  Do not wait after a marker-only failure. Add a test with `"没有答案标记"` then `"最终答案：7"` that asserts `sleep` was not called.
- [ ] Run `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m unittest tests.test_user_agent.P0StopBleedingTest tests.test_evaluate_protocol_ab`; expect pass.
- [ ] Commit: `git add user_agent.py scripts/evaluate_protocol_ab.py tests/test_user_agent.py tests/test_evaluate_protocol_ab.py && git commit -m "feat: add failure-only recovery backoff experiment"`.

### Task 3: Add explicit-answer conflict recovery

**Files:** Modify `user_agent.py`, `scripts/evaluate_protocol_ab.py`, `tests/test_user_agent.py`, `tests/test_evaluate_protocol_ab.py`.

**Produces:** `has_conflicting_explicit_answers(response: str) -> bool`, `AgentConfig(enable_explicit_answer_conflict_retry=False)`, and `answer_conflict_retry` variant.

- [ ] Write a failing test:

```python
def test_conflict_requires_two_inequivalent_explicit_answers(self):
    self.assertTrue(has_conflicting_explicit_answers("最终答案：2\n最终答案：3"))
    self.assertFalse(has_conflicting_explicit_answers("最终答案：1/2\n答案：0.5"))
    self.assertFalse(has_conflicting_explicit_answers("最终答案：2"))
```

- [ ] Run the focused test; expect import/NameError for the missing helper.
- [ ] Implement a regex matching only `最终答案：`/`答案：` line values. Return true only if at least one pair is nonempty and `answer_equivalence` is not `EQUIVALENT`. Record `explicit_answer_conflict` on candidates. With the opt-in flag, use the existing second-call slot when no-clear-answer **or** this flag is present.
- [ ] Add an integration test: conflicting output then a clean answer makes exactly two calls; a single clean answer makes exactly one.
- [ ] Run focused tests and commit: `git add user_agent.py scripts/evaluate_protocol_ab.py tests/test_user_agent.py tests/test_evaluate_protocol_ab.py && git commit -m "feat: add explicit-answer conflict retry experiment"`.

### Task 4: Add main-call temperature variants and gates

**Files:** Modify `scripts/evaluate_protocol_ab.py`, `scripts/evaluate_protocol_ab_gate.py`, `tests/test_evaluate_protocol_ab.py`, `tests/test_evaluate_protocol_ab_gate.py`.

**Produces:** variants `temperature04` and `temperature08`, with temperature applied to both main and ordinary recovery calls; gate outcomes for Correct-oriented and Invalid-oriented candidates.

- [ ] Write a failing test:

```python
def test_temperature_variants_change_only_policy_temperature(self):
    baseline = make_config(VARIANTS["baseline86"])
    self.assertEqual(0.4, make_config(VARIANTS["temperature04"]).policy_temperature)
    self.assertEqual(0.8, make_config(VARIANTS["temperature08"]).policy_temperature)
    self.assertEqual(baseline.max_tokens, make_config(VARIANTS["temperature04"]).max_tokens)
```

- [ ] Run focused test; expect absent variant keys.
- [ ] Implement `temperature04`/`temperature08` as sole temperature changes. Implement gate rejection for a paired Correct regression, increased Invalid/Incorrect, nonempty rate below 1, average calls above 1.5, or maximum calls above 2. Require mean Correct +2 for conflict/temperature and mean Invalid −2 for failure backoff.
- [ ] Run `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m unittest tests.test_evaluate_protocol_ab tests.test_evaluate_protocol_ab_gate`; expect pass.
- [ ] Commit: `git add scripts/evaluate_protocol_ab.py scripts/evaluate_protocol_ab_gate.py tests/test_evaluate_protocol_ab.py tests/test_evaluate_protocol_ab_gate.py && git commit -m "feat: add resilience and temperature gates"`.

### Task 5: Run staged experiments and publish decisions

**Files:** Create `docs/resilience_quality_temperature_ab_2026-08-21.json`; create `docs/resilience_quality_temperature_ab_2026-08-21.md`.

- [ ] Before API calls run `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'`, `D:\project\challenge_cup_2026\Challenge-Cup-2026\.venv\Scripts\python.exe -m py_compile user_agent.py scripts\evaluate_protocol_ab.py scripts\evaluate_protocol_ab_gate.py`, and `git diff --check`; expect all pass.
- [ ] Run baseline86 rounds 3–6 with workers 3, timeout 60, retry count 1, individual `--round`, and `--append-output` to establish variance.
- [ ] Run two public rounds each for `failure_backoff`, `answer_conflict_retry`, `temperature04`, and `temperature08`; evaluate each pair immediately using the gate.
- [ ] Run complex-freeze R1/R2 only for public-pass candidates. Write the report with configurations, baseline min/max/mean, all safe metrics, gate evidence, costs, and default-path decision; never include raw model messages.
- [ ] Re-run full tests, `py_compile`, and `git diff --check`. Commit only experiment code, tests, JSON and Markdown report: `git commit -m "docs: record resilience and quality experiments"`.
