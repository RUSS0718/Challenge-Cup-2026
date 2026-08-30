# PRE0-AA-004 预注册：A/A 噪声窗（AA-GATE6 amendment 后最终校准窗）

- 窗口 ID：`PRE0-AA-004`
- 类型：模型校准窗，不产生能力结论
- 预注册冻结时间：2026-08-30（Amendment AA-GATE6-2026-08-30 批准后、启动前）
- 授权：上位 spec §6c（AA-GATE6-2026-08-30，用户批准冻结文本）第 6-7 条
- **本窗是该协议的最后校准窗**：健康 VOID 可按预注册复跑一次；健康但统计、
  成本或顺序门失败 → Pre-P0 保持 BLOCKED；**不再根据本窗结果修改门槛**。

## 1. 协议（冻结文本第 6 条 + 既有参数）

- 题集：`docs/experiments/PRE0-AA-001/aa24_dataset.jsonl` 冻结复用
  （SHA-256 `e242384a…cdd0`）。
- 两轮 same-item interleaved；R1 臂序 [aa_left, aa_right] seed **8601**；
  R2 反转名义臂顺序 [aa_right, aa_left] seed **8602**。
- 预算 ≤96 solves / ≤480 调用；其余门、配置、超时和资源参数与 AA-003 一致
  （workers=3、timeout=180s、temperature=0.6、retry=1、熔断 8、
  `INTERN_REQUEST_DEADLINE_SECONDS=240`）。
- 工件：compact answers 含 `final_response`、`schedule_position`、`first_arm`
  （gate6a 的记录载体）。

## 2. 门（amendment 后口径）

1. 完整性：两轮各 24/24×2 臂、hash 一致、无熔断；
2. 健康：任一臂任一轮 error rate ≤10%；
3. 噪声：每轮 correct 差 ≤2 且 invalid+error 差 ≤2；
4. 显著性：每轮 McNemar p≥0.05；item-cluster sign test p≥0.05；
5. 成本（§6a 口径）：mean calls / mean tokens / mean latency 比值
   ∈ [0.90,1.10]（两轮合并）；P95 记录项；
6. **顺序偏差（§6c 新口径）**：
   a. 每条工件记录真实 `schedule_position` 与 `first_arm`（缺失即 FAIL）；
   b. 记录值与冻结 seed、shuffle 后位置和臂序的重算结果 **100% 一致**
      （位置与首臂双校验，任一错配即 FAIL）；
   c. first_arm × winner Fisher exact p ≥ 0.05。
   "某臂连续两轮领先"仅作描述字段。

## 3. VOID / 终局

- 健康 VOID（门 1/2、熔断、停摆）→ 恰好一次整窗复跑（新 run_id，seeds 不变）；
  再失败 → `ARCHIVED_VOID`，Pre-P0 停止。
- 健康但门 3/4/5/6 任一失败 → Pre-P0 保持 BLOCKED，**不再修改门槛**。
- 全门通过 → AA 链计入 Pre-P0 退出门（连同 §6b 其余条件）。

## 4. 产物

`pre0_aa_reports_r{1,2}.json`、`pre0_aa_answers.jsonl`、`run_manifest.json`、
`analysis.json`（gate6a/6b/6c 三段结果 + 描述性占优字段）、`pre0_aa_result.md`。
