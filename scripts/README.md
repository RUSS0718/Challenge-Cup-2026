# scripts/ 索引

> 2026-08-30 归类。历史一次性工具移入 `archive/`（保留可运行，引用路径已同步更新）；
> 活动入口与被冻结实验文档引用的路径保持在顶层不变。

## 评测基础设施（活动，勿随意移动）

| 文件 | 角色 |
| --- | --- |
| `evaluate_protocol_ab.py` | 同窗交错 A/B runner（臂/轮次/熔断/answer_rows；`--interleave-items`/`--schedule-seed`） |
| `evaluate_dev.py` | 判分与单题记录 schema（`judge_correct` 三态保守判分 = 全仓契约口径） |
| `analyze_paired_ab.py` | 配对键统计库（`(dataset_sha,round,idx,variant)`、健康门、item-cluster sign test） |
| `evaluate_protocol_ab_gate.py` | 晋升门 + 完整性模式（`--manifest/--answers/--dataset-sha256`） |

## Pre-P0 窗口工具（路径被冻结预注册引用，保持原位）

| 文件 | 窗口 |
| --- | --- |
| `pre0_static_selftest.py` | PRE0-STATIC-001 自测驱动 |
| `pre0_judge_calibration.py` | PRE0-JUDGE-001 三判分器校准 |
| `pre0_parity_harness.py` / `pre0_parity_runner.py` | PRE0-PARITY-001 双面签名 |
| `pre0_aa24_build.py` / `pre0_aa_analyze.py` | PRE0-AA 题集构建与六门分析（AA-001..004） |
| `pre0_ext_select.py` / `pre0_ext_native_judge.py` | PRE0-EXT 选题与双口径判分 |

## P1 工具（活动）

| 文件 | 角色 |
| --- | --- |
| `p1_build_core_static.py` | MATH-500 50 / AIME24 30 / AIME25 30 构建与静态门 |
| `p1_build_robust_olymp.py` | OlymMATH 40 / robust180（20 seeds）构建与静态门 |
| `p1_baseline_analysis.py` | 基线双口径分析与 run-to-run 方差 |

## archive/（历史一次性工具，2026-08-2x 时代）

freeze-set/length-pressure/medium-set 构建+校验、确定性求解器评估族
（deterministic 三件套）、method_rag/token-ladder/RAG 门、independent 审计、
scan_budget、diagnose_dev_failures/diagnose_p0_2。仍可运行（repo-root anchor
已更新为 `parents[2]`）；对应测试在 `tests/archive/`。历史文档中的引用路径
已同步（如 `local_evaluation_benchmark_audit_2026-08-29.md`）。

需要移除 `docs/13_2` 产物的助手位于 `experiments/legacy/scripts/`。

## 运行约定

- 一律从仓库根执行：`python -m unittest discover -s tests`、
  `python scripts/evaluate_protocol_ab.py ...`。
- 共享端点实验串行；`--workers` 上限 3。
- 运行任何 default-off 实验前先查 `docs/excluded_approaches.md`。
