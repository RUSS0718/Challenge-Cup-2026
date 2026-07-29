# P0.2 统一失败口径诊断报告

日期：2026-07-28
状态：完成

## P0.2.1：候选提取指标分化

评测报告新增三类指标，替代旧有的单一 `answer_not_extractable_rate` 表述：

### 新增指标

| 指标 | 说明 |
|------|------|
| `candidates_generated` (per item) | 单个题目中成功提取的候选数（status=ok） |
| `candidates_rejected` (per item) | 单个题目中被拒绝的候选数（status=rejected） |
| `all_candidates_rejected` (per item) | 所有尝试的候选均被拒绝 |
| `candidates_generated_total` (summary) | 全集中成功生成的候选总数 |
| `candidates_rejected_total` (summary) | 全集中被拒绝的候选总数 |
| `items_with_partial_rejection_count` | 至少一个候选被拒绝的题数（替代旧 answer_not_extractable_count） |
| `items_with_all_candidates_rejected_count` | 所有候选均被拒绝的题数 |
| `all_candidates_rejected_ids` | 全候选被拒绝的题号列表 |

### 修改文件
- `scripts/evaluate_dev.py`：新增 per-item 和 summary 候选计数
- `tests/test_evaluate_dev.py`：新增 3 项测试（MixedCandidateExtractionTest，AgentWithMixedCandidates，AgentWithOnlyOkayCandidates）
- 测试总数：73（+3，sympy 7 项依赖失败为已有问题）

## P0.2.2：idx 9-22 逐题归因

在默认 3 候选/256-token 路径下运行完整 agent solve()，并对每题做 1024-token 对照调用。

### 归因分类

| 分类 | 题数 | 说明 |
|------|------|------|
| `model_output_sufficient_but_agent_pipeline_lost_it` | 1 | idx 12：模型在 1024-token 可正确求解，256-token 3 候选全被拒绝 |
| `model_output_insufficient_under_256_tokens` | 2 | idx 14、22：即使 1024 token 仍输出格式占位符，非纯 token 不足问题 |
| `model_wrong_or_extraction_captured_noise` | 11 | 至少一个候选存活，但提取的答案为格式噪声或错误值 |

### 核心发现

1. **格式指令污染是首要失败模式**。idx 9-22 在 256-token 下的存活候选，其提取答案几乎全是格式噪声（如 `"."`、`"\\" followed by the answer."`）。模型在 token 预算紧张时优先输出 Prompt 中的格式说明文本，而非直接给出答案。

2. **4 题可通过增加 token 上限挽救**：idx 9（代数）、12（数列）、20（复数）、21（集合）在 1024-token 单次调用中获得正确答案。这为 P0.3 的 L1-token A/B 提供了明确证据。

3. **idx 22 特殊分析**：3/3 候选在 256-token 全被拒绝；1024-token 对照调用仍输出 2471 字符的格式占位符（`format_placeholder_echo`），**不是 token 不足问题**，而是当前 Prompt 的格式说明污染了模型输出。idx 22 的 GCD 题目(`84 和 126 的最大公约数`)本身计算量极小，说明是 Prompt 设计问题。

4. **2 题是真正的模型求解错误**：idx 16（点积）和 17（行列式）在 1024-token 下单次调用产生显式错误答案，不是截断或格式混淆。

5. **存在 API 异常**：idx 11、13、18 的 1024-token 对照调用仅返回 67-187 字符（远低于预期），疑似 API 提前截断，该部分数据不可靠。

### 诊断数据位置
- `docs/p0_2/p0_2_per_item_attribution_2026-07-28.json`

## P0.2.3：归档

- 诊断命令：`python scripts/diagnose_p0_2.py --output-file docs/p0_2/p0_2_per_item_attribution_2026-07-28.json`
- 配置：默认 6 调用/3 候选/256-token 非 L0/1024 L0
- 总调用：14 × 6 + 14 = 98 次 API 调用上限
- JSON 报告不包含原始 Prompt、模型长输出、凭证或样例答案泄漏路径
- 不覆盖 `docs/baselines/` 下的冻结基线
