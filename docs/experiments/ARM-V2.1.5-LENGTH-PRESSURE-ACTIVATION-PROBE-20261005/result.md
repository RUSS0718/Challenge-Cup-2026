---
status: engineering-only
last_verified: 2026-10-05
supersedes: none
source_ref: codex/arm-v215-bounded-tail-recovery
---

# ARM v2.1.5 length-pressure activation probe

## Result

The deterministic fixture probe passed: **7 fixture cases**, **6 bounded-tail
confirmation triggers**, **0 budget violations**, and all relevant regression
tests passed. Triggered confirmations were capped at **1,024 tokens**. UNKNOWN,
conflict, timeout, incomplete, and missing metadata paths stayed fail-closed.

Validation command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_arm_v215_bounded_tail.py -q
```

## Interpretation

This establishes that the v2.1.5 mechanism is wired and bounded. It does not
establish a mathematical capability gain and does not upgrade the ten-round
real-endpoint window, whose activation count remained zero. The formal
submission selector remains `arm-v2.1.4-cfr`.
