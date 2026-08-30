# PRE0-STATIC-001 结果：配对、VOID 与数据完整性自测

- 窗口 ID：`PRE0-STATIC-001`，类型 `STRUCTURAL_ONLY`（零模型调用）
- 运行时间：2026-08-30；attempt = 1（一次通过）
- 预注册：[`preregistration.md`](preregistration.md)（含 amendment A1：修正
  item-cluster 手算的两个描述性总数 3/3 → baseline=2/treatment=3，门数字不变）
- 判定：**PASS**（24/24 自检项 + 21 项单元测试全部通过）

## 1. 实现变更（预注册范围内）

- `scripts/analyze_paired_ab.py` 重写：唯一配对键
  `(dataset_sha256, round, item_id, variant)`；重复键/缺题/partial/数据集 hash
  不可解析全部 fail-closed（`SystemExit`）；新增 9%/11% 健康门、熔断与预注册
  VOID 分字段、item-cluster sign test、规范化题面重叠检测、分类器标签审计。
  CLI 兼容旧调用（`--baseline/--treatment/--round`），新增
  `--expected-n/--sha-map/--cluster`。
- 新增 `scripts/pre0_static_selftest.py`（自检驱动）、
  `tests/test_paired_analysis.py`（21 用例）、`tests/test_analyze_paired_ab.py`
  更新到新配对契约（旧行为=idx-only 覆盖，即本次修掉的 bug，测试随契约更新）。
- 零 runtime 改动（`user_agent.py` 未触碰）、零判分阈值改动、零模型调用。

## 2. 正例（手算复现）

合成工件 2 数据集 × 2 rounds × 2 arms × 3 items（见 `synthetic_artifacts/`）：

| 项 | 预期（手算） | 实测 | 结论 |
| --- | --- | --- | --- |
| r1 McNemar | b=2, c=1, p=1.0 | b=2, c=1, p=1.0 | 一致 |
| r2 McNemar | b=1, c=1, p=1.0 | b=1, c=1, p=1.0 | 一致 |
| per-round 配对数 | 各 3（跨轮不坍缩） | 3 / 3 | 一致 |
| item-cluster | b=2, c=1, ties=0, p=1.0 | 同 | 一致 |
| 聚类正确总数 | baseline=2, treatment=3 | 2 / 3 | 一致（A1 口径） |
| delta 分布 | {+2, −2, +1} | 同 | 一致 |
| item-round 池化（描述性） | 6 对（b=3,c=2） | 同 | 一致 |

## 3. 健康门与 VOID 语义

- 100-item 工件：双臂各 9% error → `void=false`，error rate 精确 0.09；
  armX 11% → `void=true`，`void_reason="error_rate_above_threshold"`。
- 熔断注入（`consecutive_failures_max=8`）→ `breaker_tripped=true`、
  `breaker_reason="consecutive_model_errors"`，与错误率门分字段记录；
  两者可同时出现且语义可区分，熔断不替代正式 VOID。
- `paired_counts(..., expected_n)` 路径同样给出 error_rates 与 VOID 标记。

## 4. 反例（全部 fail-closed）

duplicate_pair_key、unpaired_items（缺题）、completed_n_mismatch（partial）、
dataset_sha256_unresolvable（无文件且无 sha-map）→ 均 `SystemExit` 非零退出，
无统计输出。真实 complex48+medium60 作为独立样本池化被
`dataset_overlap_blocks_pooling` 拒绝。

## 5. 真实数据集事实对齐（规范 §2 收敛项）

| 事实 | 预期（审计/规范） | 实测 | 结论 |
| --- | --- | --- | --- |
| complex48 ∩ medium60 规范化题面重叠 | 24 | 24 | 一致 |
| 去重唯一题数 | 84 | 84 | 一致 |
| public112 运行时分类 | 全部 calculation | 112×calculation | 一致 |
| medium60 存储标签失配 | 8 | 8 | 一致（清单见下） |
| complex48 存储标签失配 | —（未先验） | 0 | 记录 |

medium60 失配清单（stored → runtime，全部单向为 derivation/choice → calculation）：
idx 6103, 6108, 6109, 6206, 6216, 6217, 6218, 6219。
按预注册：仅记录、不修标签；后续任何按存储标签的宏平均在此之前被禁止。

public112 与两个 legacy 集的规范化题面零重叠（total_overlap_pairs 仅来自
complex48↔medium60 的 24 对）。

## 6. 结论与下游解锁

- 配对/完整性/健康门/聚类统计契约已按规范 §4.2/§4.4/§4.5 固化并可复现；
  PRE0-AA-001 的分析依赖（跨轮配对 + item-cluster）就此解除阻塞。
- 机器可读证据：`pre0_static_checks.json`；合成工件：`synthetic_artifacts/`。
- 本窗无能力结论、无模型调用、无 `SUBMISSION_CONFIG` 变更。
