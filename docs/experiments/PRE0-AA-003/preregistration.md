# PRE0-AA-003 预注册：A/A 噪声窗（amendment 后合规窗）

- 窗口 ID：`PRE0-AA-003`
- 类型：模型校准窗，不产生能力结论
- 预注册冻结时间：2026-08-30（amendment 批准后、重跑之前）
- 授权：上位 spec §6a Amendment（2026-08-30，用户批准）：gate5 latency 门
  改 mean latency ∈[0.90,1.10]（P95 记录项）；本窗为该 amendment 下的合规窗。
- 前序：AA-001（P95 口径 BLOCKED，门证据）、AA-002（mean 口径 6/6 但属事后
  改门，降为历史校准证据）。本窗在**修复后的基础设施**（首臂按
  schedule_position 记录、僵尸遥测护栏、manifest 强制字段）下重跑。

## 1. 协议（除下列外与 AA-001/002 完全一致）

- 臂：`aa_left` / `aa_right`，逐字段 = `baseline_hetero`（answer-first + hetero
  + adaptive k5/3 + 4096 + policy prompt，≤5 调用/solve）。
- 题集：`docs/experiments/PRE0-AA-001/aa24_dataset.jsonl` 冻结复用
  （SHA-256 `e242384a…cdd0`），不重选。
- 轮次：2 轮 same-item interleaved；R1 [left, right] seed **8501**；
  R2 [right, left] seed **8502**（新 seeds，与历史窗独立）。
- 资源：workers=3；timeout=180s；temperature=0.6；retry=1；熔断 8；
  `INTERN_REQUEST_DEADLINE_SECONDS=240`；预算 ≤96 solves / ≤480 调用；
  共享端点串行（EXT-002 在本窗关闭后执行）。
- 工件增强：compact answers 含 `final_response` 与 `schedule_position`
  （gate6 直接消费真实调度位置，不再依赖重构）。

## 2. 门（判定顺序）

1. 完整性：两轮各 24/24×2 臂、hash 一致、无熔断（formal gate 完整性模式校验）；
2. 健康：任一臂任一轮 error rate ≤10%；
3. 噪声：每轮 correct 差 ≤2 且 invalid+error 差 ≤2；
4. 显著性：每轮 McNemar p≥0.05；item-cluster sign test p≥0.05；
5. 成本（amendment 口径）：mean calls / mean tokens / **mean latency** 比值
   ∈ [0.90,1.10]（两轮合并）；P95 与先/后位次延迟记录不设门；
6. 顺序偏差：无臂两轮持续占优；首运行臂（**按工件 schedule_position**）×
   获胜臂 Fisher exact p≥0.05。

## 3. VOID / 复跑

- 健康 VOID（门 1/2、熔断、停摆）→ 恰好一次整窗复跑（新 run_id，seeds 不变）；
  再失败 → `ARCHIVED_VOID`，Pre-P0 停止。
- 健康但门 3/4/6 失败 → 正确率协议实质偏差 → BLOCKED 上报，不得进入 P0。
- 健康但门 5 失败 → amendment 被证伪 → BLOCKED 上报（P95/mean 双记录保留）。
- 本窗任何结果不得表述为能力差异。

## 4. 产物

`pre0_aa_reports_r{1,2}.json`、`pre0_aa_answers.jsonl`、`run_manifest.json`
（§4.1 全字段 + 工件 sha）、`analysis.json`（消费 schedule_position）、
`pre0_aa_result.md`。
