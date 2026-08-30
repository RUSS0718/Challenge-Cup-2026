# PRE0-AA-002 结果：A/A 噪声窗（协议修复版）

- 窗口 ID：`PRE0-AA-002`，类型：模型校准窗（不产生能力结论）
- 运行：2026-08-30 12:12–13:31（两轮串行，96/96 solves，实际模型调用 385 / 上限 480）
- 预注册：[`preregistration.md`](preregistration.md)（协议修复：gate5 latency 由 P95
  改为 mean；停摆护栏启用；新 seeds 8401/8402）
- 判定：**PASS（6/6 门）** —— 评测协议修复有效，Pre-P0 的 A/A 门槛达成

## 1. 完整性与健康（门 1、2 — PASS）

- 两轮各 24/24 × 2 臂齐全；dataset SHA-256 一致；无熔断。
- model error：r1 aa_left 1/24（4.2%），r2 全零；均 ≤10%。
- 停摆护栏（`INTERN_REQUEST_DEADLINE_SECONDS=240`）全程无触发（对比 EXT-1 的
  3×6.3h 事故），端点本窗健康。

## 2. 噪声与显著性（门 3、4 — PASS）

| 指标 | Round 1 | Round 2 | 门 |
| --- | --- | --- | --- |
| correct（left/right） | **16 / 16** | **15 / 15** | 差 ≤2 ✓（两轮均恰为 0） |
| invalid+error | 1 / 0 | 0 / 0 | 差 ≤2 ✓ |
| exact McNemar p | 1.0 | 1.0 | ≥0.05 ✓ |
| 首臂占优 | 无 | 无 | ✓ |

- item-cluster（24 题 × 2 轮）：b=1, c=1, ties=22, p=1.0；聚类正确总数 31 = 31。
  唯一两个分歧 item-round 方向恰好相反（left-first 题 right 胜、right-first 题
  left 胜），与顺序无关联（Fisher p=1.0）。
- 正确率层面的 A/A 一致性达到本轮可测的上限：两轮合并后两臂逐题正确次数
  几乎完全相同。

## 3. 成本门（门 5 — PASS，修复后口径）

两轮合并（每臂 48 solves），gated = mean calls / mean tokens / **mean latency**：

| 指标 | aa_left | aa_right | 比值 | 门 [0.90,1.10] |
| --- | --- | --- | --- | --- |
| mean model_calls | 3.9583 | 4.0208 | 1.016 | ✓ |
| mean completion tokens | ~对称 | ~对称 | 0.995 | ✓ |
| **mean latency (s)** | ~对称 | ~对称 | **0.988** | ✓ |
| P95 latency（记录项，不设门） | — | — | 0.920 | 记录 ✓（本窗端点尾部亦收敛） |

AA-001 的 P95 失败（0.759）在本窗未复现（P95 比值回到 0.920），进一步支持
"该统计量在 n=48 下由个别长尾 solve 主导、不适合作为 ±10% 门"的诊断；
修复后的 mean latency 门在两个独立窗口均落在带内。

## 4. 顺序偏差（门 6 — PASS）

无臂两轮持续占优；首运行臂 × 获胜臂 Fisher exact p=1.0。

## 5. 结论与解锁

- 评测协议（轮次、交错、首臂轮转、配对/聚类统计、修复后的成本门、健康门、
  熔断语义）在共享端点上通过了同配置双臂校验：**正确率协议无偏、噪声带
  已标定**（correct 差 ≤2/24、聚类 p=1.0）。
- 按规范 §6，A/A 通过后 Pre-P0 退出门的模型窗部分全部达成；后续能力实验
  （P0 判读、P1 基线锚、P2 GSA 重证等）可引用本噪声带做效应量预期。
- 运行数据：`analysis.json`、`pre0_aa_reports_r{1,2}.json`、
  `pre0_aa_answers.jsonl`、`run_manifest.json`。
