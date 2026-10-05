# 2026-10-04 官方评测低分分析与 v2.2 试验入口

## 已确认事实

官方报告对应提交 `b63059ca9b64a5a49c4add4e1830f23e58a9bb79`，正式 selector 为
`arm-v2.1.4-cfr`。100 题中有 `21 correct`、`6 incorrect` 和 `73 invalid`；200 次请求中
70 次以 `finish_reason=length` 结束，基础设施错误和 deadline failure 都是 0，runner 正常
完成。机器版转录见 [`report.json`](../official_evaluations/2026-10-04/report.json)。

## 低分的证据约束

官方总分被 73 个 `invalid` 直接压低；可判定的 27 题中，`21/27 = 77.7778%`。这说明
当前最明确的工程损失是答案形成和输出收束，但不能把 77.8% 当作隐藏集整体准确率，
也不能由这份报告单独证明模型数学能力已经达到 77.8%。报告没有提供逐题 response、
prompt、答案转移表或每题错误原因，因此“73 个 invalid 全部由截断造成”仍然无法确认。

合理推断是：长输出在形成可判定最终答案之前耗尽预算，是需要优先验证的机制；基础设施
排障不是本轮首要方向，因为报告记录了零 infra error 和零 deadline failure。任何修复都
必须同时观察 `invalid`、`correct`、`correct → incorrect` 转移、截断和调用成本，不能只
追求更少的 `invalid`。

## 当前行动

已有 v2.1.8/2.1.9 试验表明“截断后再收束”可能降低截断，却出现答案反转或没有降低
invalid。因此 v2.2 采用不同的单变量假设：第一次请求先提交一行唯一 `Final answer`，
再允许最多四行核对；第二次请求继续使用原 CFR Challenger 和安全 incumbent 规则。候选
只作为显式 default-off profile，不修改正式 selector。

试验使用与 X/Y/Z 窗口不重叠的 OlymMATH、AIME 和 HLE Math 题目，并以 10 轮 Q01–Q10
配对窗口验证。若安全门出现任一 `correct → incorrect`，即使 invalid 或截断改善，也不
晋升；所有数字只属于 `local_replay`。

## 未知项

- 无逐题官方 raw log，不能把每个 invalid 映射到具体 parser、模型或服务原因。
- 官方报告只对应 100 题，不能与仓库 112 题历史实验直接做准确率排序。
- 本地外部题集只能筛选候选，不能替代下一次官方隐藏集评测。
