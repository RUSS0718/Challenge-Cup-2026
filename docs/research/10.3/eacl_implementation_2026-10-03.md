# EACL 实现与真实 API 验收记录

日期：2026-10-03
状态：实验入口已实现；默认 `ReasoningAgent` 与 `SUBMISSION_CONFIG` 未切换。

## 实现内容

新增 `reasoning_agent/eacl_pipeline.py`，把 ARM 的职责收敛为控制平面，并将一次答题拆成：

```text
Host Intake → ARM Route → Route A/B Solver → Candidate Ledger
→ deterministic PASS/FAIL/UNKNOWN → conservative decision → ARH serializer
```

实现约束：

- 每题最多 3 次 logical model call；
- requested token 有总预算；
- Route B 不接收 Route A 的完整响应，只接收题面和合同；
- 确定性求解器只作为已知安全题型的 verifier；
- `UNKNOWN` 不被当作 `PASS`；
- 冲突且没有确定性证据时返回 `UNKNOWN`；
- OFF finalizer 只能复述已有 canonical candidate，不能改变数学值；
- trace 只保留候选摘要、hash、调用、token、finish reason 和决策，不保存完整思维链。

独立运行入口：

```powershell
$env:PYTHONPATH = "."
.\.release-venv\Scripts\python.exe scripts\run_eacl.py `
  --input_file sample_data\dev.jsonl `
  --output_root artifacts `
  --max_model_calls 3 `
  --total_token_budget 12288 `
  --thinking_on
```

该入口刻意不修改 `main.py` 的官方 profile，避免实验代码未经 paired gate 进入提交路径。

## 零模型回归

`tests/test_eacl_pipeline.py` 覆盖：

- 确定性 PASS 的单调用早停；
- 首轮无候选时的独立 Route B；
- 确定性反例阻止错误候选覆盖；
- 冲突且无证据时 fail-closed；
- 调用上限和异常分类；
- 带负号 `\\dfrac` 的表达式规范化。

当前正式工作区的完整 unittest 回归为 `1078 tests OK, 4 skipped`。

## 真实 API smoke

使用授权的 Intern-S2 endpoint，在三道不含 gold 的本地 smoke 题上运行：

| 题型 | 结果 | 调用 |
|---|---:|---:|
| `5!` | `120`，确定性 verifier `PASS` | 1 |
| 直接数值 `7` | `7`，Route A/B canonical agreement | 2 |
| 复分析留数 | `-1/8`，Route A/B canonical agreement | 2 |

最终 3 题复测使用显式 `--timeout_seconds 180 --retry_count 1 --off_finalizer`，工件为
`artifacts/20261003-122535444106-grh-eacl-v1/`。本地 evaluator 逐题判定为 `3/3 correct`：
`72`、`-1`、`-1/8`。该目录属于运行产物，不进入 Git。

先前使用默认 30 秒客户端超时的运行在第一道长题上出现两次 timeout，EACL 第三次 recovery
保持 `UNKNOWN`。这被记录为 endpoint 健康差异，不计入能力结论；显式 180 秒后同题得到 `72`。

这轮只证明端到端连接、候选抽取、ARH 输出和预算遥测可运行，不能证明官方 hidden set correct 提升。

## 当前边界

- 真实 smoke 中长题 ON 请求在 30 秒 client timeout 下出现过 endpoint timeout；这被记录为运行健康问题，不能归因给数学架构。
- 确定性 verifier 对未覆盖题型返回 `UNKNOWN`，不会用模型自评替代。
- EACL 仍是实验 profile；必须完成同题交错的 ARH、Route B、组合栈双轮 paired gate 后，才考虑接入默认提交配置。
