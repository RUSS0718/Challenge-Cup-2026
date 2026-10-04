# 2026-10-04 代理分析

## EXACT

- 官方报告对应提交 `b63059ca9b64a5a49c4add4e1830f23e58a9bb79`。
- 100 题中 `21 correct / 6 incorrect / 73 invalid`。
- 200 次请求中 70 次 `finish_reason=length`。
- 基础设施错误和 deadline failure 均为 0，runner 已完成。
- 只在已判定的 27 题上计算时，accuracy 为 `21 / 27 = 77.78%`。

## TRACEABLE

提交代码中的正式 selector 是 `arm-v2.1.4-cfr`；提交运行时仍保持答案库、RAG 和
Skill 默认关闭。发布协议与运行时哈希见
[`docs/releases/arm-v2.1.4-cfr-20261004/`](../../releases/arm-v2.1.4-cfr-20261004/)。

## INFERRED

70/200 的长度结束与 73 个 invalid 同时出现，说明当前首要工程风险仍是答案形成和输出
收束，而不是基础设施崩溃。它支持有限、默认关闭的 incumbent confirmation 假设，但不能
证明数学能力已经提升，也不能把 invalid 下降等同于 correct 增长。

## UNKNOWN

- 报告没有提供逐题转移表、每题 prompt/response 或可复核的 raw 下载文件。
- 该报告的 100 题题集与仓库历史 112 题归档不是同一范围；无法从本次结果推导 112 题
  accuracy 或与历史 112 题结果作严格因果比较。
