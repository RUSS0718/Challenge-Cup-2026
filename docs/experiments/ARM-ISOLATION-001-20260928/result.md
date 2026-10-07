# ARM-ISOLATION-001 隔离实验报告

- run_id：`ARM-ISOLATION-001-20260928`

**实验无效（未测到模型）。** 54/54 个请求均在客户端连接阶段以 `connectivity` 失败，耗时约 0–0.05 秒；没有任何请求收到端点响应。因此不能据此判断 endpoint timeout、Agent 架构、token 或并发影响。`report.json` 中的 `complete: true` 仅表示计划记录数已尝试并写入。

- 开始时间（UTC）：2026-09-28T05:10:44.549794+00:00
- 完成时间（UTC）：2026-09-28T05:10:46.862115+00:00
- Git HEAD：188d9c064c8351b3565dfd40249bbe6afefc07a7
- 题目：OlymMATH-HARD-13-EN（题面以 SHA-256 标识，178 字符）
- 已尝试：54/54 条求解记录；成功到达端点：0/54
- 请求 timeout / 每题总预算：180s / 180s
- 每条件重复 3 次；不将题面、响应正文或答案写入工件。

|路径|每次调用 max_tokens|workers|n|非空 Agent 结果（含失败兜底）|correct / incorrect / invalid|请求超时数|平均单题耗时|P95单题耗时|平均请求耗时|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|bare_endpoint|2048|1|3|0/3|0 / 0 / 3|0|0.005s|0.016s|0.002s|
|bare_endpoint|2048|3|3|0/3|0 / 0 / 3|0|0.0s|0.0s|0.003s|
|bare_endpoint|4096|1|3|0/3|0 / 0 / 3|0|0.016s|0.031s|0.015s|
|bare_endpoint|4096|3|3|0/3|0 / 0 / 3|0|0.01s|0.031s|0.011s|
|bare_endpoint|8192|1|3|0/3|0 / 0 / 3|0|0.015s|0.046s|0.014s|
|bare_endpoint|8192|3|3|0/3|0 / 0 / 3|0|0.0s|0.0s|0.005s|
|current_arm_on|2048|1|3|0/3|0 / 0 / 3|0|0.016s|0.032s|0.01s|
|current_arm_on|2048|3|3|0/3|0 / 0 / 3|0|0.016s|0.016s|0.004s|
|current_arm_on|4096|1|3|0/3|0 / 0 / 3|0|0.016s|0.047s|0.007s|
|current_arm_on|4096|3|3|0/3|0 / 0 / 3|0|0.015s|0.015s|0.005s|
|current_arm_on|8192|1|3|0/3|0 / 0 / 3|0|0.016s|0.031s|0.009s|
|current_arm_on|8192|3|3|0/3|0 / 0 / 3|0|0.02s|0.031s|0.01s|
|minimal_agent|2048|1|3|3/3|0 / 0 / 3|0|0.01s|0.016s|0.007s|
|minimal_agent|2048|3|3|3/3|0 / 0 / 3|0|0.0s|0.0s|0.004s|
|minimal_agent|4096|1|3|3/3|0 / 0 / 3|0|0.01s|0.031s|0.009s|
|minimal_agent|4096|3|3|3/3|0 / 0 / 3|0|0.016s|0.016s|0.004s|
|minimal_agent|8192|1|3|3/3|0 / 0 / 3|0|0.011s|0.016s|0.005s|
|minimal_agent|8192|3|3|3/3|0 / 0 / 3|0|0.0s|0.0s|0.004s|

## 判读结论

本轮三条路径都未到达模型，不能比较耗时或能力，也不能判断是不是 Agent 架构导致超时。失败发生得很快，符合连接阶段错误；但仅凭客户端记录不能确认是沙箱出口策略、DNS/网络故障还是端点当时不可达。各配置的 connectivity 错误计数见 `report.json`，合计 54。

## 限制

- One fixed problem; conclusions diagnose this workload, not general benchmark accuracy.
- A three-worker batch may interact with external server load; only client-side concurrency was controlled.
- Token budget means per-call max_tokens. Current ARM-ON review/critic stages used the same cap; total solve tokens were capped at three times the per-call cap.
- Three repeats per condition are diagnostic, not a statistical capability gate.

raw 请求明细、机器汇总和 manifest 留在本地忽略目录
`docs/experiments/ARM-ISOLATION-001-20260928/`，不进入 Git。
