# 2026-09-08 Agent 分析

## 方法映射

`fc1b671` 的 `user_agent.py` 可回查到 `enable_fork_select_deepen_finish=True`、
`enable_temporary_answer_bank=True`；没有 Constraint-Fit Harness/Deep/hybrid 三个开关。
因此归类为 **FSDF + answer-bank-on**，不是纯 FSDF。

## 证据等级

- 方法代码：`EXACT`，commit 可在当前 Git 历史中检出。
- 官方分数：`EXACT`，来自随附原始日志。
- 单变量收益：`UNKNOWN`，该记录没有 matched control。
