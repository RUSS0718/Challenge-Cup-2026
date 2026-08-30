# PRE0-STATIC-001 预注册：配对、VOID 与数据完整性自测

- 窗口 ID：`PRE0-STATIC-001`
- 类型：`STRUCTURAL_ONLY`，**零模型调用**
- 预注册冻结时间：2026-08-30（实现与运行之前）
- 上位规范：`math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6
- 状态：本文件写毕即冻结；任何修订必须以 amendment 小节显式记录，不得就地改写。

## 1. 假设与动机

`docs/research/local_evaluation_benchmark_audit_2026-08-29.md` §2.3 已确认
`scripts/analyze_paired_ab.py` 的 `paired_counts()` 只按 `idx` 建字典：跨轮、跨数据集
同 `idx` 记录会静默覆盖，`n_paired/b/c/p` 不可作为正式池化证据。规范 §2 同样把它列为
"任一事实未收敛前不启动新能力方法窗"的起始缺陷之一。本窗口验证修复后的配对与
统计实现，使后续所有窗口（含 PRE0-AA-001）能消费可信工件。

## 2. 单变量与实现范围

- 唯一改动：`scripts/analyze_paired_ab.py` 的配对与统计实现（保持 CLI 兼容），
  新增自测脚本 `scripts/pre0_static_selftest.py` 与单元测试
  `tests/test_paired_analysis.py`。
- 不改任何 runtime（`user_agent.py` / `reasoning_agent/`）、不改判分器阈值、
  不跑任何模型调用。

## 3. 冻结的配对与分析契约

1. 唯一配对键：`(dataset_sha256, round, item_id, variant)`。`dataset_sha256` 为
   `input_file` 内容的 SHA-256（文件存在时现算；缺文件时必须由 manifest 显式提供，
   不得退化为路径字符串）。
2. 同一完整键重复出现 → 直接 fail-closed（异常退出），禁止覆盖。
3. 任一臂在任一 `(dataset, round)` 缺题、或 `completed_n != expected_n`、
   或 partial report → fail-closed，不产出统计。
4. 跨轮结果不得覆盖：同一 `idx` 的 round1/round2 是两个独立配对。
5. 健康门（预注册口径，与规范 §4.4 一致）：任一臂
   `model_error_count / expected_n > 10%` → 整窗 `VOID`。行级 error 判定：
   `result_status == "error"` 或 `"model_error" ∈ diagnostic_reasons`。
6. 熔断与 VOID 分字段记录：`void_reason = "consecutive_model_errors"`（runner 熔断）
   与 `"error_rate_above_threshold"`（预注册健康门）是两个独立字段值，不得混用；
   熔断只是 `aborted_resource_guard` 类信号，不能替代正式 VOID 判定。
7. item-cluster 统计（规范 §4.5）：以题目为聚类单位，
   `delta_i = 候选在各轮正确次数 − 对照在各轮正确次数`；`b = #(delta_i>0)`、
   `c = #(delta_i<0)`、`delta_i=0` 不计；对 `b/c` 做双侧 exact sign test
   （即 exact McNemar 公式复用）。item-round 池化只作描述输出。
8. 重合集检测：对任意两个数据集按规范化题面 hash（NFKC → 去全部空白 → lower）
   求交集；交集非空时报告重叠题并拒绝独立池化。

## 4. 自测工件与预期（正例）

合成正例：2 数据集（shaA≠shaB）× 2 rounds × 2 arms（`ctl`/`treat`）× 3 items，
每臂每轮 3 行、共 24 行。构造结果（C=correct，I=非 correct）：

| item | r1 ctl | r1 treat | r2 ctl | r2 treat |
| --- | --- | --- | --- | --- |
| 1 | I | C | I | C |
| 2 | C | I | C | I |
| 3 | I | C | I | I |

手算预期（实现必须逐一复现）：

- 每轮 per-round McNemar：r1 `b=2,c=1,p=1.0`；r2 `b=1,c=1,p=1.0`。
- item-cluster（3 题）：delta = (+2, −2, +1) → `b=2,c=1,ties=0,p=1.0`；
  `baseline_cluster_correct=2`、`treatment_cluster_correct=3`（amendment A1：
  原文误写为 3/3，2026-08-30 运行前修正，仅改描述性总数，门数字 b/c/p 不变）。
- 配对总数：per-round 各 3；item-round 池化描述 6；cluster 3。
- 错误率门：构造 100-item 附加工件，armX 9 error、armY 9 error → 健康；
  另一工件 armX 11 error → `VOID` 且 `void_reason="error_rate_above_threshold"`。
- 熔断字段：构造 `consecutive_failures_max≥8` 工件 → `void_reason=
  "consecutive_model_errors"`，与 6 的值可区分。
- 重合集：合成 dsB 含 1 条与 dsA 规范化后相同的题 → 检出重叠并拒绝池化；
  真实 `complex48`+`medium60` → 恰 24 道重叠、去重后 84 道唯一题。
- 分类器审计：对 `public112`（预期 112×calculation）、`complex48`、`medium60`
  运行 `classify_problem_type`，记录实际分布与 stored `task_type` 失配清单
  （审计先验：medium60 8 条失配；以实测为准记录，不以此设门）。

## 5. 反例（必须全部 fail-closed）

| 反例 | 期望行为 |
| --- | --- |
| duplicate：同键两行 | 报错退出，非零 exit code |
| missing：某臂缺 1 题 | 报错退出并列出缺失 item |
| partial：某臂仅 2/3 题（completed≠expected） | 报错退出 |
| 11% error（≥阈值） | `VOID=true`，`void_reason="error_rate_above_threshold"` |
| 9% error（<阈值） | `VOID=false`，正常统计 |
| dataset hash 缺失且文件不可得 | 报错退出（不得用路径串冒充 hash） |

## 6. 门与停止条件

- 通过门：第 4 节全部正例数字与手算一致，第 5 节全部反例 fail-closed，
  真实集重叠=24/唯一=84 复现，分类器分布与失配清单落盘。
- 任一失败 → **Pre-P0 整体停止**：不写 `pre0_static_result.md` 通过结论、
  不启动 PRE0-JUDGE/AA/EXT/PARITY 模型相关步骤，先修复再整窗重测（重测计入
  result 文档的 attempt 记录）。
- 完成产物：`pre0_static_result.md`（本目录）、自测脚本、单元测试。

## 7. 明确不做

- 不据此改判分器、不改 runtime、不改 `SUBMISSION_CONFIG`、不 commit/push。
- 不对 public112/complex48/medium60 的分类失配做"修标签"动作（只记录）。
- 本窗口不产生任何能力结论。
