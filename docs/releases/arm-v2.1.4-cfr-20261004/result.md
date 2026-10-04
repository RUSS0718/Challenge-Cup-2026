# ARM v2.1.4 CFR 发布记录

状态：`DEPLOYED_EVALUATED_NO_PROMOTION`
发布日期：2026-10-04
目标 ref：`gitcode/main`

本记录对应 [发布协议](protocol.md)。CFR 已接入无参 `ReasoningAgent(client=...)` 入口，
并完成严格三参数 client、metadata/gold 隔离、trace 卫生、配置断言和相关回归测试。

官方报告已返回并归档为
[`OFFICIAL-20261004-B63059`](../../official_evaluations/2026-10-04/record.md)：提交
`b63059ca9b64a5a49c4add4e1830f23e58a9bb79` 在 100 题范围内得到 `21 / 6 / 73`，200 次
请求中 70 次 `finish_reason=length`，基础设施错误和 deadline failure 均为 0。报告只在
27 个 valid records 上给出 77.7778% accuracy；它不是历史 112 题表格的同一范围，因此
不会被写成相对 119 正确基线的能力提升，也不触发 selector 晋升。

逐题转移、原始 response 和完整 latency 分布未随当前 checkout 保留；证据边界见日期页
的 `agent_analysis.md`。

## 回滚条件

- 官方 client 构造或三参数调用失败；
- CFR 造成可确认的 correct→invalid 损失；
- model error 超过官方健康门；
- 官方评测未能复现协议中的 selector 和配置断言。

回滚锚点：`43a02da`（GRH v1.1 / 119 正确基线发布树）。
