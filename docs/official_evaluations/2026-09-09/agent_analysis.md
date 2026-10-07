# 2026-09-09 Agent 分析

## 方法映射

`dbf3b74` 的提交说明是启用 50-question reference answer bank。源码中
`enable_fork_select_deepen_finish=True`、`enable_temporary_answer_bank=True`，
而 Harness/Deep/hybrid 开关不存在。因此归类为 **FSDF + temporary-50-bank**。

50-bank 是 answer-bank 机制的具体题库版本，不是另一种推理架构；命中时可绕过模型调用。

## 证据等级

- 方法代码：`EXACT`。
- 官方分数：`EXACT`，来自随附原始日志。
- 单变量收益：`UNKNOWN`，与前后日志存在 commit、题目窗口和配置变化。
