# Intern-S2 思考模式对照实验汇总（2026-09-27）

## 结论摘要

- 可直接配对的证据来自 3 道相同题目的 smoke：默认模式重复运行 3 次，合计 9 次题目执行、36 次请求尝试，全部超时；关闭思考运行 1 次，13 次请求尝试中 12 次成功、1 次超时，题目结果为 2 correct、1 incorrect、0 invalid。关闭思考这一轮的 HLE 判分受 Math-Verify 子进程解码告警影响，需视为暂定结果。
- “默认模式”不是显式 `thinking=true`：默认 smoke 的 manifest 记录 `thinking_mode=null`，即未设置该开关；关闭模式记录 `false`。因此本报告描述的是“服务默认模式 vs 显式关闭”，而非严格的 true/false 参数实验。
- 两组 30 题结果不能用于估计思考开关的因果效果：题目 ID 完全不重合；默认模式来自较早的 runner，且缺少逐请求失败类别；关闭模式使用完整请求遥测。
- 当前证据显示关闭思考时请求成功率改善，但 30 题关闭模式仍有 14 incorrect、13 invalid。它支持继续诊断，不足以证明通用数学能力提升，也不能单凭 invalid 归因于题目太难。

## 实验边界与配置

比较对象均为模型 ID `intern-s2`、`submission` profile、本地 external-hard pools；配对 smoke 与关闭思考 30 题的 agent 配置哈希相同：`65b51903fbf62f941cd4325c078b0ec7cc6db1971040caf97a69f23a147e5bb2`。instrumented runs 使用 3 workers、30 秒单请求超时、1 次 retry；answer bank 为 off。凭证和原始 prompt/response 未写入诊断报告。

配对 smoke 中，默认模式开关未设置（`null`），关闭模式为 `false`。关闭开关通过该次运行的进程环境生效，没有写回 `.env`。默认 hard30 记录为 `default`。没有一组 manifest 证明以显式 `true` 参数运行，因此不得把“默认”表述为已验证的显式开启。

## 相同 3 道题的配对 smoke

四次 smoke 的 `input.jsonl` SHA-256 都是 `a38884a9e9539d82c56c13892cd37caf781a5e4df4d12c60c5e3703252ddd298`，题目 ID 相同：

- `OlymMATH-HARD-41-ZH`
- `aime-2024-II-10`
- `hle-6725716480b9caf2f8f62d01`

| 模式/运行 | 题目执行次数 | 结果 | 请求尝试 | 成功响应 | 超时 |
| --- | ---: | --- | ---: | ---: | ---: |
| 默认（v1） | 3 | 0 correct / 0 incorrect / 3 invalid | 12 | 0 | 12 |
| 默认（v2） | 3 | 0 / 0 / 3 | 12 | 0 | 12 |
| 默认（v3，阶段遥测最完整） | 3 | 0 / 0 / 3 | 12 | 0 | 12 |
| 显式关闭 | 3 | 2 correct / 1 incorrect / 0 invalid | 13 | 12 | 1 |

默认模式三次运行合计为 **0/9 correct、0/9 incorrect、9/9 invalid；36/36 次请求超时**。这是同一小题集重复调用，不是 9 道独立题。关闭模式仅一轮，且 HLE 的 incorrect 判分因 Math-Verify 在 Windows 子进程中出现两次 UTF-8 reader-thread `UnicodeDecodeError` 告警而暂定；请求遥测不受该评分告警影响。

v3 将默认模式 12 次超时归因到 `analyze` 2 次、`deep_primary` 1 次、`deep_review` 1 次、`deepen` 2 次、`finish` 2 次、`fork_b` 2 次、`fork_c` 2 次。关闭模式这一轮记录 12 次成功响应和 1 次 `deepen` 超时。

## 两组 30 题 hard run（非配对）

| 模式/运行 | 抽样 | 结果 | 请求遥测 |
| --- | --- | --- | --- |
| 默认 | 30 题，3 个来源各 10 题，seed 20260927 | 2 correct / 0 incorrect / 28 invalid | 旧 runner 只记录到 4 次成功 completion（涉及 3 道题）；失败请求类别没有完整记录，不能从 `model_error=0` 推断无超时 |
| 显式关闭 | 30 题，3 个来源各 10 题，seed 20260929；保留 3 道 smoke 题并排除默认 hard30 抽样 | 3 correct / 14 incorrect / 13 invalid | 102 次尝试、83 次成功、19 次超时；请求成功率 81.4% |

默认模式分来源：OlymMATH 0/0/10，AIME 2/0/8，HLE 0/0/10（每组依次为 correct/incorrect/invalid）。失败请求遥测不可恢复。

关闭模式分来源：

| 来源 | 题数 | correct | incorrect | invalid | 请求成功 | 请求超时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OlymMATH HARD | 10 | 0 | 0 | 10 | 10 | 11 |
| AIME | 10 | 3 | 5 | 2 | 31 | 4 |
| HLE MATH | 10 | 0 | 9 | 1 | 42 | 4 |
| 合计 | 30 | 3 | 14 | 13 | 83 | 19 |

关闭模式的 19 次请求超时发生在 `deep_primary` 9 次、`deep_review` 4 次、`deepen` 3 次、`finish` 1 次、`fork_b` 1 次、`fork_c` 1 次。HLE 的 9 个 incorrect 表明“答案能完整输出”与“数学上正确”是两回事；OlymMATH 的 invalid 也不能仅凭题目难度解释，仍需逐题查看最终化状态和 trace。

两组 30 题的题目 ID **没有交集**。此外，默认 30 题来自较早的 runner（manifest 指向旧代码快照），关闭 30 题则使用带逐请求遥测的 instrumented runner。因此分数和 invalid 数的变化不能归因于 thinking mode。

## 解读与后续实验要求

1. **请求健康：** 3 题配对 smoke 中默认模式三次均无成功响应，关闭模式大部分请求成功。这个差异值得重测，但小样本且默认端未显式传 `true`。
2. **数学能力：** 关闭模式 30 题有 14 个明确错误；输出完整不代表答案正确。报告没有足够证据认定思考关闭提升了数学正确率。
3. **invalid 的来源：** 默认 30 题缺少失败请求细目；关闭 30 题虽有 83 次成功响应，却仍有 13 个 invalid。要判断是题目难度、路由/中间阶段失败、弃答策略还是最终答案协议问题，需结合每题 `answers.jsonl` 与阶段 trace 分层审查。
4. **可归因的下一轮比较：** 固定相同的 30 个 item ID、代码/runner、agent 配置、timeout、retry 和并发；只改变 thinking mode，显式记录开关值。保留 timeout/error 在分母中，并报告每题结果、最终化状态、各阶段请求、失败类别和评分器异常。

## 原始证据

以下运行目录位于被 `.gitignore` 忽略的本地 `sample_outputs/` 中，不随本次提交推送。此汇总报告保留了结论所需的指标；原始逐题答案和 trace 仍只在本机可用。

- 默认模式配对 smoke：`sample_outputs/intern-s2-instrumented-smoke-20260927/`、`sample_outputs/intern-s2-instrumented-smoke-20260927-v2/`、`sample_outputs/intern-s2-instrumented-smoke-20260927-v3/`。
- 关闭模式配对 smoke：`sample_outputs/intern-s2-thinking-off-smoke-20260927/`。
- 默认 30 题：`sample_outputs/intern-s2-hard30-20260927/`。
- 关闭 30 题：`sample_outputs/intern-s2-thinking-off-hard30-20260927/`。

## 重复文件核对

核对时，四个 3 题 smoke 目录中的 `input.jsonl` 内容完全相同；但 `answers.jsonl`、`report.json`、`run_manifest.json` 和 `selection.json` 均不完全相同，保存了不同运行的输出、耗时或运行标识，不能无损互换。默认 hard30 与关闭 hard30 的题集和结果也不同，不属于重复文件。

2026-09-28 按用户确认，已删除旧默认 smoke v1、v2 中重复的 `input.jsonl` 副本；v3 与关闭思考 smoke 中仍保留相同输入。v1、v2 的 manifest 仍记录原始 `dataset_path` 和数据集哈希，但对应本地输入文件现已不存在。其答案、报告、manifest 和 selection 文件均予保留，没有删除任何独立运行结果或整个 run 目录。
