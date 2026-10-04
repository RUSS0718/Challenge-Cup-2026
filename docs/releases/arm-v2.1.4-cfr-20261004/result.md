# ARM v2.1.4 CFR 发布记录

状态：`DEPLOYED_UNVALIDATED_CANARY`
发布日期：2026-10-04
目标 ref：`gitcode/main`

本记录对应 [发布协议](protocol.md)。CFR 已接入无参 `ReasoningAgent(client=...)` 入口，
并完成严格三参数 client、metadata/gold 隔离、trace 卫生、配置断言和相关回归测试。

官方隐藏集尚未重新评测，因此本文件不填写 correct / incorrect / invalid，也不声称相对
119 正确基线有提升。官方 runner 返回结果后，须在此追加不可变的评测 run ID、commit SHA、
题数、五数统计、model error 与时延/调用预算摘要。

## 回滚条件

- 官方 client 构造或三参数调用失败；
- CFR 造成可确认的 correct→invalid 损失；
- model error 超过官方健康门；
- 官方评测未能复现协议中的 selector 和配置断言。

回滚锚点：`43a02da`（GRH v1.1 / 119 正确基线发布树）。
