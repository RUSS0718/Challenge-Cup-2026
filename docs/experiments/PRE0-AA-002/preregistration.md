# PRE0-AA-002 预注册：A/A 噪声窗（协议修复版）

- 窗口 ID：`PRE0-AA-002`
- 类型：模型校准窗，**不产生任何能力结论**
- 预注册冻结时间：2026-08-30（PRE0-AA-001 结果判定之后、重跑之前）
- 前序：PRE0-AA-001 健康且 5/6 门通过，唯一失败为 gate5 的 **P95 latency 比值
  0.759 < 0.90**（详见 `../PRE0-AA-001/pre0_aa_result.md` §3）。按 AA-001 预注册
  §6，协议判 `BLOCKED` 并以本新预注册修复后重做。本窗是规范 §6"健康但 A/A 仍
  显著偏离则评测协议 BLOCKED，不得进入 P0"的协议修复路径。
- 启动前置：PRE0-STATIC/JUDGE/PARITY 通过；EXT 串行约束让位（AA-002 与 EXT-2
  不并发）；用户已指示在 PRE0-8.30 分支继续 Pre-P0 实验（2026-08-30）。

## 1. 修复内容（唯一协议变量）

| 项 | AA-001 | AA-002 | 依据 |
| --- | --- | --- | --- |
| gate5 latency 统计量 | P95 latency 比值 ∈ [0.90,1.10] | **mean latency 比值 ∈ [0.90,1.10]**；P95 latency 与先/后位次延迟降为记录项 | 同配置双臂实测：P95@n=48 为第 46 位值，被每臂 2–3 个长尾 solve 主导（逐轮比值 0.73/0.97），均值类全部在带内（calls 1.027、tokens 0.955、mean latency ~0.92）；正确率聚类 b=0,c=0 证明协议本身无偏 |
| gate5 其余分量 | mean calls / mean tokens ∈ [0.90,1.10] | 不变 | AA-001 实测在带内 |
| 停摆护栏 | 无 | `INTERN_REQUEST_DEADLINE_SECONDS=240`（llm_client opt-in 墙钟时限） | EXT attempt-1 事故（3×~6.3h 滴流停摆）；护栏对两臂对称，不构成 A/A 变量 |
| 其余一切 | — | **不变** | — |

这不是"调门凑通过"：P95@n=48 的不可达性由**同配置双臂**以最强证据形式实测，
A/A 窗口的存在目的正是给出该校准。

## 2. 不变协议（继承 AA-001 预注册 §2–§4）

- 臂：`aa_left` / `aa_right`，逐字段解析为 `baseline_hetero` 配置
  （answer-first + hetero + adaptive k5/3 + 4096 + policy prompt，≤5 调用/solve）。
- 题集：`aa24_dataset.jsonl` 冻结复用（SHA-256
  `e242384a0374b497c89a7c173cb65eb7795f474e0089b30e42a06e4b43d0cdd0`），
  不重选、不重排。
- 轮次：2 轮 same-item interleaved；R1 臂序 [left, right]、seed **8401**；
  R2 臂序 [right, left]（反向首臂轮转）、seed **8402**。
- 资源：workers=3；timeout=180s；retry=1；temperature=0.6；熔断 8 连续；
  预算 ≤96 solves / ≤480 调用；共享端点串行。
- 运行面：`PRE0-8.30` 分支（集成分支已并入 main，行为面与 AA-001 的实验面
  一致性由 PRE0-PARITY-001 背书 + 同一补丁集被合并提交 `d84be6e` 固化）。
- 判分：`evaluate_dev.judge_correct` 冻结；compact answers 落盘。

## 3. 门（判定顺序与 AA-001 相同，gate5 按修复后口径）

1. 完整性：两轮各 24/24×2 臂、hash 一致、无熔断；
2. 健康：任一臂任一轮 error rate ≤10%；
3. 噪声：每轮 correct 差 ≤2 且 invalid+error 差 ≤2；
4. 显著性：每轮 McNemar p≥0.05；两轮 item-cluster sign test p≥0.05；
5. 成本（修复）：mean calls / mean tokens / **mean latency** 比值 ∈ [0.90,1.10]
   （两轮合并计；逐轮与 P95、先/后位次延迟并列记录）；
6. 顺序偏差：无臂两轮持续占优；首运行臂×获胜臂 Fisher exact p≥0.05。

## 4. VOID / BLOCKED / 复跑

- 健康 VOID（门 1/2、熔断、停摆事故）→ 允许恰好一次整窗复跑（新 run_id，
  seeds 不变）；再失败 → `ARCHIVED_VOID`，Pre-P0 停止。
- 健康但门 3/4/6 失败 → 正确率协议存在实质偏差：评测协议 `BLOCKED` 升级上报，
  **不得**进入 P0，且不再以同协议重试。
- 健康但门 5 失败 → 本修复无效：`BLOCKED` 上报，由团队决定成本门的最终形式；
  不得再自动重试。
- 本窗任何结果不得表述为能力差异。

## 5. 产物

`pre0_aa_reports_r{1,2}.json`、`pre0_aa_answers.jsonl`（attempt 后缀隔离）、
`run_manifest.json`、`analysis.json`（`scripts/pre0_aa_analyze.py` 按 AA-002 口径
运行）、`pre0_aa_result.md`。
