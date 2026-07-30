# P1.5 旧评测资产退役 — 迁移摘要

完成日期：2026-07-30

> 2026-07-30 审计更正：本次 Gate 是数据完整性、接口隔离、evaluator 冒烟和
> 资产迁移 Gate，不是模型双轮效果 Gate。112 题当前全部属于分类器意义上的
> `calculation`，应定位为 18 方向短题知识覆盖集，而不是正式评测风格或复杂
> 能力回归集。

## Gate 验证

| 条件 | 状态 | 证据 |
|------|------|------|
| 112 题数据完整性与答案校验 | ✅ | 13/13 测试通过（`tests/test_public_regression_dataset.py` + `test_evaluate_dev.py` 的 RegressionDatasetValidationTest） |
| subject/answer 未传入 solve | ✅ | `test_subject_and_answer_stay_out_of_solve_and_feed_grouped_metrics` 通过 |
| 新 evaluator 端到端冒烟 | ✅ | 3 项 smoke 样本（idx 5000-5002）正常处理：status=ok，0 超时，0 空响应；不代表完整模型双轮 |
| 121/121 全量测试 | ✅ | `unittest discover tests -v` 全部通过 |

## 删除清单

### 数据集
- `sample_data/basic_arithmetic_dev.jsonl` — 6 道受控算术题（已包含在旧 dev.jsonl 中）
- `sample_data/dev.jsonl` idx 3-22 — 20 道 `local_handcrafted_2026-07-26` 手工题（缩减为 idx 0-2 官方 3 题）

### 实验产物（docs/）

| 目录/文件 | 数量 | 说明 |
|-----------|------|------|
| `docs/baselines/` | 25 JSON | 全部 23 题实验基线（2026-07-25 ~ 2026-07-27） |
| `docs/diagnosis/` | 1 JSON | 2026-07-27 失败诊断 |
| `docs/budget_scan/` | 25 文件 | P0.1 预算扫描全部产物（summaries/logs/per_tier） |
| `docs/p0_2/` | 2 文件 | P0.2 逐题归因 JSON + summary |
| `docs/p0_3/*.json` | 4 JSON | P0.3 token 对照实验数据（保留 summary.md） |
| `docs/p1/*.json` | 3 JSON | P1 answer-first 实验数据（保留 reclassification.md + summary.md） |
| `docs/p1_1/*.json` | 2 JSON | P1.1 多根规范化实验数据（保留 diagnosis + summary.md） |
| `docs/p1_5/_gate_output.json` | 1 JSON | Gate 验证临时输出 |

### 运行产物
- `sample_outputs/0.json, 1.json, 2.json` — 旧运行输出（已清理）

### 保留文件
- All `*_summary_report.md` — ADOPT 决策记录
- `docs/p1/p1_error_reclassification_2026-07-29.md` — 错误分类历史
- `docs/p1_1/p1_1_diagnosis_and_design.md` — 多根规范化设计
- `docs/p1_eval/` — 112 题评估相关文档
- `docs/开发记录.md`, `docs/系统方案文档(2).md`, `docs/技术文档(2).md` — 项目核心文档

## 新基线

- **短题知识覆盖集**: `sample_data/public_regression_112.jsonl`（112 题冻结集合，idx 5000-5111，18 方向分布）
- **冒烟测试**: `sample_data/dev.jsonl`（3 题官方样例）
- **默认评测脚本**: `scripts/evaluate_dev.py` 默认运行 112 题回归集
- **配置**: answer-first Prompt, max_tokens=1024, policy_sample_times=3, max_model_calls=6, task_aware + time_convergence 启用
- **测试**: 121/121 全量通过

## 脚本默认路径变更

| 脚本 | 旧默认 | 新默认 |
|------|--------|--------|
| `scripts/evaluate_dev.py` | `sample_data/dev.jsonl` | `sample_data/public_regression_112.jsonl` |
| `scripts/scan_budget.py` | `sample_data/dev.jsonl` | `sample_data/public_regression_112.jsonl` |
| `scripts/diagnose_dev_failures.py` | `sample_data/dev.jsonl` | `sample_data/dev.jsonl`（不变，诊断工具） |
| `scripts/diagnose_p0_2.py` | `sample_data/dev.jsonl` | `sample_data/dev.jsonl`（不变，诊断工具） |

## 替代路径

- 历史实验数据：通过 `git log -- docs/baselines/` 等命令从 Git 历史恢复
- 旧 23 题实验结论：见各 `*_summary_report.md` 决策记录
- 手工题：不再使用；112 题仅确认 18 个数学方向的短题知识覆盖，复杂题型能力需由独立冻结集补充
