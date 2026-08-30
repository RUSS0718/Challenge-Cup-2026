# PRE0-AA-004 结果：A/A 噪声窗（最终校准窗）

- 窗口 ID：`PRE0-AA-004`，类型：模型校准窗（不产生能力结论）
- 运行：2026-08-30 16:24–17:30（两轮串行，96/96 solves，实际调用 375/480，
  两轮 0 模型错误、0 停摆触发）
- 授权：上位 spec §6c（AA-GATE6-2026-08-30）第 6-7 条；**本窗为该协议的最后
  校准窗，不再据其修改门槛**
- 判定：**PASS（6/6 门，§6c 口径）→ AA 链计入 Pre-P0 退出门**

## 1. 门 1–5（全过）

| 指标 | Round 1 | Round 2 |
| --- | --- | --- |
| correct（left/right） | 16 / 15 | 13 / 14（胜者**翻转**） |
| model error / invalid+error | 0；0/0 | 0；0/0 |
| McNemar p | 1.0 | 1.0 |
| 两轮合并 mean calls / tokens / **mean latency** 比值 | 0.953 / 1.034 / **1.029**（带内） | |
| P95 latency（记录项） | 0.971 | |
| item-cluster | b=1, c=1, ties=22, p=1.0；聚类正确总数 29 = 29 | |

## 2. gate6（§6c 三段口径，全过）

- **6a**：96/96 行记录 `schedule_position` 与 `first_arm`（缺失 0）✓
- **6b**：记录值与冻结 seed（8601/8602）+ shuffle 后位置 + 臂序的重算结果
  **100% 一致**（position 与 first_arm 双校验，0 错配）✓
- **6c**：first_arm × winner Fisher exact p = 1.0（两个决定性 item-round 方向
  完美反向：left_first→right 胜、right_first→left 胜）✓
- 描述字段：`descriptive_same_arm_led_both_rounds = false`（胜者跨轮翻转）。

## 3. formal gate 完整性模式

`evaluate_protocol_ab_gate.py --manifest --answers --dataset-sha256` 在本窗工件上：
integrity **PASS**（manifest 工件 sha 逐一核实、配对完整性 24/24×4、错误计数 0、
逐轮 McNemar 与聚类统计从工件复现）。比较侧的"accuracy_not_below_baseline"
为 A/A 语义下无意义的晋升比较（r1 候选 15 < 基线 16），不构成 A/A 判定。

## 4. 结论

- 评测协议（交错/轮转/配对/健康/成本/顺序全链）在 §6c 最终口径下通过同配置
  双臂校验；AA 链（AA-004 为合规窗）计入 Pre-P0 退出门。
- 三窗合并的校准结论（最终版）：正确率噪声带 = 每轮 correct 差 ≤1、聚类
  p=1.0；成本比值带 [0.90,1.10] 稳定可达；健康门 0 错误可达；schedule/first_arm
  工件可审计。
- 噪声带供后续候选效应量预期：**24 题/轮口径下 correct 差 >1 才开始有信号、
  ≥2 触及 AA 噪声上沿**；正式能力判定按规范走 core120_v2/confirm30_v2。
