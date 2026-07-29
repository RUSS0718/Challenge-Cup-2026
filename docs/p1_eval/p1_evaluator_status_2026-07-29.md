# 第三阶段 P1：评测器实现与数据源 Gate

日期：2026-07-29  
状态：**112 题数据构建与评测器完成；模型双轮评测待执行**

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

## 未完成与下一 Gate

1. 完整运行新 evaluator，至少独立复现两次。
2. 与旧 23 题链路完成迁移对照。
3. 上述结果通过后才进入 P1.5，缩减 smoke test、切换默认输入并清理旧评测资产。

Gate 未通过前，旧 23 题与现有评测产物保持不变。
