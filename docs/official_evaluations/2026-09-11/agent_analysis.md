# 2026-09-11 Agent 分析

## 方法映射

`3ede125` 是 `dbf3b74` 与 Harness 分支合并后的快照。源码配置确认：

- Harness：开启
- Deep lane：开启
- FSDF hybrid：开启
- FSDF legacy：开启
- temporary answer bank：开启，`harness_bank_mode="on"`

因此准确标签是 **Harness + Deep + hybrid FSDF + bank-on**，不能写成“纯 Harness 得分”。

## 证据等级

- 方法代码：`EXACT`，commit 可回查。
- 官方分数：`EXACT`，来自随附原始日志。
- Harness 单独收益：`NOT_IDENTIFIABLE`，answer bank、Deep、hybrid 和 FSDF 同时变化。
