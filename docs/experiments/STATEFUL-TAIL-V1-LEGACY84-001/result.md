# STATEFUL-TAIL-V1-LEGACY84-001 实验结果报告

实验 ID：`STATEFUL-TAIL-V1-LEGACY84-001`
方法 ID：`stateful_tail_completion_v1`
对照基线：`baseline_hetero`（`hetero_k5 @ 25f99b5`）
执行时间：2026-09-03 07:44:12 UTC – 09:56:27 UTC（耗时 7934.9s ≈ 2.2 小时）
代码分支：`codex/stateful-tail-v1` @ `ee84c48`
题集：`sample_data/legacy84.jsonl`（84 题，SHA-256 `80f7cbd178b8415a0cb805f8261693ae5133342f40883954cc9bc17ca7645f8c`）
调度参数：双轮同题交错（Round 1 seed 4201, Round 2 seed 4202），8 workers 并发，timeout=300s

---

## 一、核心指标与统计汇总

| 指标 | 对照臂（`baseline_hetero`） | 候选臂（`stateful_tail_completion_v1`） | 差异（Candidate − Baseline） | 门控判定 |
| :--- | :--- | :--- | :--- | :--- |
| **Round 1 正确数** | 47 / 84 (55.95%) | 45 / 84 (53.57%) | −2 | — |
| **Round 2 正确数** | 47 / 84 (55.95%) | 48 / 84 (57.14%) | +1 | — |
| **双轮合计正确数** | **94 / 168 (55.95%)** | **93 / 168 (55.36%)** | **−1** | **FAIL（未达净增益）** |
| **独胜对数 ($b / c$)** | — | — | $b = 4, c = 5$ (McNemar $p = 1.0000$) | **FAIL** |
| **题目聚类配对 ($b / c$)**| — | — | **$b = 3, c = 5$ (Exact Sign Test $p = 0.7266$)** | **FAIL（$p \ge 0.05$）** |
| **模型错误数 / 错误率** | 0 / 0.0% | 0 / 0.0% | 0.0% | **PASS（健康门达标）** |
| **平均模型调用数** | 3.92 次/题 | 4.04 次/题 | +3.0% (≤ +10%) | **PASS（成本门达标）** |
| **完成度与配对完整率** | 168 / 168 (100%) | 168 / 168 (100%) | 0 丢题 | **PASS（完整性达标）** |

---

## 二、统计检验与深度归因分析

1. **统计显著性判定**：
   - 聚类题目 sign test：3 题候选胜、5 题对照胜（双侧精确 $p = 0.7266 \gg 0.05$）；
   - 双轮配对 McNemar 检验：$b=4, c=5$（双侧精确 $p = 1.0000$）；
   - 结论：**未能证明尾段续推在 legacy84 题集上具有可泛化的能力增益**。
2. **机制归因**：
   - 在已触发续推的长题上，虽然 Fidelity 探针证明了尾段能促成显式答案收束（75%），但在整体正确率上，续推补全的答案大部分仍受限于模型底层数学推理能力（如算错或推导偏差），未能显著转化为正向得分增益（即 invalid 转化为 incorrect 为主，契合历史 32k 与 GSA 实验的共性规律）。
3. **健康与成本验证**：
   - 8 workers 全量 336 次 solve() 0 runner error，0 进程泄漏，证明了单体状态管理与并发隔离代码的极高工程鲁棒性。

---

## 三、最终实验处置与裁决

根据总规范 §4.4、§14 与排除表规则：
- **定级**：**`EXPLORATORY_NO_SIGNIFICANT_GAIN / NO_PROMOTION`**。
- **处置**：
  - `stateful_tail_completion_v1` **不予晋升为官方默认路径**；
  - `user_agent.py` 中的 `SUBMISSION_CONFIG.enable_stateful_tail_completion` **严格保持 `False`（默认关闭）**；
  - 官方发布面继续锁定唯一健康基线 **`hetero_k5 @ 25f99b5`（commit `34bc353`）**。
