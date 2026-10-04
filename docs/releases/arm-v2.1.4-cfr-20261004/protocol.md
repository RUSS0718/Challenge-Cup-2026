# ARM v2.1.4 CFR 发布协议

协议编号：`ARM-V2.1.4-CFR-20261004`
提交 selector：`arm-v2.1.4-cfr`
方法 ID：`arm_v2.1.4_cfr`

## 目的

CFR（Challenger → Targeted Repair → Fresh Review）面向 invalid rescue 的失败模式，
把“发现异议”和“允许替换答案”拆成两个独立门。Primary 先形成候选；Challenger 只有在
输出结构化、可定位且有证据的异议时才允许进入局部修复；Fresh Review 必须逐字对齐异议
位置并通过，修复结果才可替换 incumbent。任何解析失败、证据不足、异议不匹配或复核不通过
都保留安全候选或返回 `UNKNOWN`。

## 正式配置

| 配置项 | 值 |
| --- | --- |
| `SUBMISSION_MODE` | `arm-v2.1.4-cfr` |
| ARM harness | `v2.1.4` |
| `arm_v2_mode` | `selective` |
| solver reasoning | `off` |
| trust policy | `positive_evidence` |
| max calls | 4（adaptive/deep） |
| token budget | 16,384（adaptive/deep） |
| targeted repair | enabled |
| fresh review | enabled |
| hybrid router | disabled |
| answer bank / RAG / Skill | disabled |

官方 client 只保证 `client.chat(messages, temperature, max_tokens)`。本方案通过统一兼容
分发层适配本地可选的 `reasoning_mode`、`timeout_seconds`，不会把扩展参数泄露为官方契约
要求。

## 资格与验证边界

本协议只记录代码、接口、预算和隐私隔离门。官方 100 题聚合结果已经归档，发布状态应写为
`DEPLOYED_EVALUATED_NO_PROMOTION`。该结果不能与 112 题历史行或代理集的 119 正确基线
直接比较，也不能据此宣称 CFR 能力提升。
官方报告已由日期页记录 run commit、题数和完整五数；后续若出现 model error、invalid damage
或正确数门失败，按发布协议回滚到 `43a02da`。
