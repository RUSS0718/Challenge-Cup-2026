# 第三阶段 P1：评测器实现与数据源 Gate

日期：2026-07-29（评测器与数据集完成）；2026-07-30（完整模型评测执行中）
状态：**短题知识覆盖链路可用；复杂能力与 P2/P3 效果 Gate 待补**

## 已完成

- `answer` 与 `subject` 仅供本地 evaluator 评分和统计；`ReasoningAgent.solve` 只接收题面与 `{"idx": ...}`。
- 18 个方向映射到 5 个策略家族：离散—代数—优化、连续纯数学、数值—微分方程、概率—统计、通用高级。
- 评测报告输出总体准确率、家族/方向/题型分组，以及家族、方向和题型宏平均准确率。
- `validate_regression_items` 校验 112 条规模、18 方向计数、追溯字段、HTTPS 来源、idx 类型、重复 idx 和重复题面；CLI 可用 `--validate-regression-dataset` 强制执行该 Gate。
- 求解路径没有新增按题号、题面、`subject` 或 `answer` 的特判。

## 冻结数据集

- 文件：`sample_data/public_regression_112.jsonl`。
- SHA-256：`1B001975AB3CCFC8538191E96A53E3B6737423C0409A5B02358AE487D73C1CF0`。
- 规模：112 行；idx 连续为 5000–5111；严格匹配公开的 18 方向计数。
- 题目性质：依据公开定义/定理重新选择对象、参数和问法的原创参数化题，不是官方题库，也未复制第三方 112 题集合。
- 逐题字段：`source`、`source_url`、`source_ref`、`adaptation`、`verification`。
- 来源目录：`docs/p1_eval/public_regression_sources_2026-07-29.md`。

## 能力边界（2026-07-30 审计）

- 使用当前 `classify_problem_type` 实测：`calculation=112`，其余五类均为 0。
- 题面长度中位数约 30、P95 约 48、最长 63。
- 因此本集定位为“18 方向短题知识覆盖集”，适合检查知识面、答案抽取、基础
  输出和 evaluator 链路；不能单独证明证明/推导/解释、长题面、跨方向混合题、
  多解/反例/存在性问题或 P3 修正的收益。
- 官方隐藏题型分布未公开，本集合不得称为“正式评测风格回归集”。

## 数据源审计

赛事规则页与官方 baseline：

- https://aicarrier.feishu.cn/wiki/L90FwD9gJiqdg0k33RCcHTdcnrb
- https://github.com/InternLM/Challenge-Cup-2026

截至本次核对，两处都只提供 3 道样例，没有 112 道可直接冻结的官方题面与答案。因此本回归集明确标记为本项目原创参数化集合。

曾核对公开 fork 的提交 `6a81793e29ac77e802123d051f555113649968ab`：

- https://github.com/FoldedDesk/Shusheng_ChallengeCup_2026/commit/6a81793e29ac77e802123d051f555113649968ab

其仓库设计文档明确说明该集合是按分布编写的“112 道原创中文题”，并非官方 samples；仓库 API 也未声明许可证。因此本项目不复制、不误标该数据。

## 验证

- `tests/test_public_regression_dataset.py` 直接加载冻结文件，并验证分布与逐题追溯字段。
- `scripts/evaluate_dev.py --input-file sample_data/public_regression_112.jsonl --validate-regression-dataset --total-timeout-seconds 0`：数据 Gate 通过；0 秒参数仅阻止模型调用，不作为准确率结果。
- `D:\Anaconda\envs\CA-py310\python.exe -m unittest discover -s tests -v`：**121/121 通过**。
- `py_compile`：`scripts/evaluate_dev.py`、`user_agent.py`、`llm_client.py`、`sympy_adapter.py`、`main.py` 通过。
- `git diff --check`：通过。
- 禁止特判扫描：未发现 `metadata.subject`、`metadata.answer` 或按 idx 求解分支。

## 执行状态（2026-07-30 更新）

1. ✅ 评测正确性 Bug 已修复：`solve()` 新增 `extracted_answer` 字段，evaluator 改用其做正确性比对（此前用完整 `final_response` 文本比对纯数值答案，导致全 0%）。
2. ✅ 修正后的单轮参考结果 `docs/p1_5/eval_run1_2026-07-30.json` 已生成：按当前近似字符串 Judge 为 59/112（52.68%），0 超时、0 空响应、平均 5.107 次调用、平均 31.178 秒。它只代表短题集单轮观测，不替代双轮 A/B 或官方成绩。
3. 🔄 当前后台运行 `eval_p3_default_2026-07-30.json`：工作区配置为异构 Reasoner 开启、P3 验证开启、P3 修正关闭。
4. ⚠️ 该配置的验证发生在候选选择后且不改变答案；现有 evaluator 也未汇总 verify/revise/reverify 状态，因此本轮只能作调用/延迟参考，不能作为 P3 正确率收益证据。
5. ✅ P1.5 的数据/接口/迁移 Gate 已完成；它不是模型双轮效果 Gate。详见 `docs/p1_5/p1_5_migration_summary.md`。

## evaluator 待修项（P3 后高优先级）

1. 增加异构、P3 验证和 P3 修正显式 CLI 开关，避免修改默认值区分实验组。
2. 报告记录实际开关、Prompt/配置版本与有效调用上限；P3 开启时上限应包含 `p3_call_boost`。
3. 修复 `budget_config` 重复 `max_tokens`；`within_call_cap` 使用有效上限而不是固定基础 6 次。
4. 增加平均/P95 调用与延迟、P3 状态计数、修正接受/回滚率，并保留紧凑预测答案供离线重判。
5. 将评分升级为规范化精确一致、结构化数学一致、受控 SymPy 三层；无法证明时记录 `UNKNOWN` 和覆盖率。
6. 建立独立复杂能力冻结集，再对同 Prompt、异构、异构+验证、异构+验证+修正执行至少双轮 A/B。
