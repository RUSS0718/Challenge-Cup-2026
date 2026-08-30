# PRE0-AA-003 结果：A/A 噪声窗（amendment 后合规窗）

- 窗口 ID：`PRE0-AA-003`，类型：模型校准窗（不产生能力结论）
- 运行：2026-08-30 14:15–16:05（两轮串行，96/96 solves，实际调用 380/480，
  两轮 **0 模型错误**——三个 AA 窗中最健康）
- 预注册：[`preregistration.md`](preregistration.md)（授权：spec §6a Amendment）
- 判定：**门 1–5 PASS；gate6（持续占优分支）失败 → 按预注册 §3 关窗并升级上报**
- 运行数据：`analysis.json`、`pre0_aa_reports_r{1,2}.json`、`pre0_aa_answers.jsonl`
  （含 `final_response` 与 `schedule_position` 工件字段）、`run_manifest.json`

## 1. 门 1–5（全过）

| 指标 | Round 1 | Round 2 |
| --- | --- | --- |
| correct（left/right） | 14 / 15 | 14 / 15 |
| invalid+error | 0 / 0 | 0 / 0 |
| model error | 0 / 0 | 0 / 0 |
| McNemar p | 1.0 | 1.0 |
| mean calls / tokens / **mean latency** 比值 | \multicolumn{2}{c}{0.939 / 0.918 / **0.915**}（均在 [0.90,1.10]；amendment 口径） |
| P95 latency（记录项） | 1.108 | 记录 ✓ |

完整性（96/96、hash 一致、无熔断）与工件 `schedule_position`/`final_response`
字段均验证可用；formal gate 完整性模式可在本窗工件上直接运行。

## 2. gate6 失败：持续占优分支（如实记录）

- aa_right 在两轮中均严格占优（+1/+1）→ `dominance=true` → 门 6 失败。
- Fisher（首运行臂 × 获胜臂，按工件 `schedule_position` 计算）p≈1.0：
  **首臂顺序与胜负无关联**。
- item-cluster：b=2, c=0, ties=22, p=0.5（两个分歧题均朝 aa_right 方向）。

## 3. 统计学解读（供决策，不改变门判定）

"同一臂两轮均严格占优"这一判据在公平 A/A 下的天然触发概率约为
**1/2 × P(两轮都有胜者)**——本次三个 AA 窗的实测恰为：AA-001 翻转（过）、
AA-002 双平局（过）、AA-003 同向 +1/+1（触发）。该判据对"名义臂标签"
（field-identical 配置下 left/right 只是标签）过于敏感，假警率与 P95 门
同量级但方向相反（过严而非过松）。

本窗的全部无偏指标——每轮 McNemar p=1.0、聚类 sign test p=0.5、
Fisher p≈1.0、零模型错误、成本比值带内——均与"协议无偏"一致；
唯一失败信号是名义标签层面的 +1/+1 持续性。

## 4. 处置（按预注册 §3 升级上报，等待用户决定）

- 本窗按预注册关窗：**不自动通过、不自动重试**。
- 可选路径（用户决定）：
  1. 批准 amendment：持续占优判据加最小边际（如同向两轮且**合计 correct 差 ≥3**），
     或以"聚类 sign test + Fisher"取代标签占优判据；然后以新 ID 再跑一窗；
  2. 接受 AA-003 为"判据过严"的实证、按 amendment 直接修订判据但不重跑
     （重演 AA-002 式争议，不建议）；
  3. 维持 BLOCKED，不再消耗调用。

## 5. 明确不做

- 本窗不产生能力结论；不改 SUBMISSION_CONFIG；不 push；不进入 P0/P1。
