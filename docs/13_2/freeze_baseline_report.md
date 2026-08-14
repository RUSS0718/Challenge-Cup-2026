# 13.2 复杂能力冻结集 · 两轮纯基线报告

日期：2026-08-14
基线：当前默认配置（3072 单调用 + 至多一次条件重试，未改任何开关）
数据：`sample_data/complex_capability_freeze_48.jsonl`（48 题，冻结）

## 1. 执行摘要

两轮纯基线跑出**同一个跨题型系统性缺陷**：

- 可自动判的题型（choice / fill_blank / calculation）表现正常：**91.7% / 100% / 83.3%**。
- 复杂能力题型（derivation / proof / explanation，共 30 题）两轮**全部 0%**，
  且 60 题次全是 `unknown`——不是模型算错，是**答案抽取被 thinking process 泄漏
  彻底破坏**。
- 主调用 `finish_reason=length` 率 **47.9% / 50.0%**，远高于 112 题短计算集的
  10–18%。根因同一处：这些题型的 prompt 鼓励「完整推导/证明」，触发 InternLM
  内置 thinking 长篇输出，把 3072 token 吃光，答案标记在输出前即被截断。

**结论：模型能力不是瓶颈，瓶颈在「非数值题型的输出卫生」——thinking 泄漏 +
答案标记被截断 + 非数值题型用完整响应当答案。** 命中锁死的决策规则 #2。

## 2. 两轮结果

| 指标 | 第 1 轮 | 第 2 轮 |
|---|---:|---:|
| 整体准确率（judge 可判定口径） | 33.3% (16/48) | 35.4% (17/48) |
| 题型宏平均 | 45.8%（两轮合并） | 同左 |
| 主调用 length 率 | 47.9% | 50.0% |
| 答案标记覆盖率（1−条件重试率） | 100% | 100% |
| 非空 final_response | 100% | 100% |
| 平均 / P95 / 总调用数 | 1.00 / 1 / 48 | 1.00 / 1 / 48 |
| 平均延迟 | 26.0s | 26.5s |
| fallback | 0 | 0 |
| incorrect | 0 | 0 |

## 3. 题型宏平均（两轮合并，每题计 2 次）

| 题型 | 题次 | correct | 宏准确率 | verdict 分布 |
|---|---:|---:|---:|---|
| choice | 12 | 11 | 91.7% | correct 11, unknown 1 |
| fill_blank | 12 | 12 | 100.0% | correct 12 |
| calculation | 12 | 10 | 83.3% | correct 10, unknown 2 |
| derivation | 20 | 0 | 0.0% | unknown 20 |
| proof | 20 | 0 | 0.0% | unknown 20 |
| explanation | 20 | 0 | 0.0% | unknown 20 |

## 4. 根因诊断

### 现象（逐题明细）

derivation/proof/explanation 三题型的 `extracted_answer` 几乎全是响应**开头**的
thinking 片段，而不是「最终答案：」后的数值：

```
6000  derivation  'ThinkingProcess:1.Analyzethe...'      vs 期望 '3'
6002  derivation  "Here'sathinkingprocesstosolv..."      vs 期望 '9'
6017  explanation '握手引理的解释：在图G=(V,E)中...'       vs 期望 '20'
6013  proof       '命题：sqrt(2)是无理数。证明：采用反证法。假设sq'（被截断）
```

### 根因链

1. **prompt 触发 thinking**：`DERIVATION_PROMPT`/`PROOF_PROMPT`/`EXPLANATION_PROMPT`
   要求「给出完整推导/证明/解释」，但**缺少** calculation prompt 里的
   「优先收敛到答案、不要输出格式说明或无关说明」压制语。InternLM
   （intern-s2-preview）因此进入 thinking 模式，输出大段英文 thinking
   process。
2. **thinking 吃光 token**：长篇 thinking 使 3072 的 `length` 率冲到 47.9–50%，
   响应在输出到「最终答案：」之前就被截断（如 6013 截断在「假设sq」）。
3. **非数值题型用完整响应当答案**：`_generate_candidates` 对
   `_NON_NUMERIC_TASK_TYPES` 执行 `answer = response.strip()`；`extracted_answer =
   normalize_answer(完整响应)`。于是判分拿到的就是 thinking/推导文本开头，
   与数值标准答案永不匹配 → 全部 `unknown`。

### 为什么 choice/fill_blank/calculation 没事

它们的 prompt 是 answer-first（「直接给答案、不要 thinking」），模型压得住
thinking；且 `_format_task_final_response` 对这三类返回**紧凑规范化答案**，
`extracted_answer` 是干净的数值/字母。

## 5. 失败类别（两轮合并，共 63 题次非 correct）

| 类别 | 数量 |
|---|---:|
| unknown-表示不一致（实为 thinking 泄漏 + 截断） | 59 |
| unknown-纯命题（√2 / √3 无理，预期内） | 4 |
| incorrect | 0 |

## 6. 结论与方向（不改 Agent，待决策）

按锁死的决策规则 #2「主要失败集中在证明/推导完整性 → 讨论任务型 Prompt」，
本缺陷明确指向**任务型 Prompt 的输出卫生治理**，两条可分离、可单测的通用改动：

1. **压制 thinking**：给 derivation/proof/explanation 三个 prompt 补上与
   calculation 同款的「不要输出 Thinking Process/计划/格式说明」压制语。
2. **答案标记前置 + 非数值题型也走标记抽取**：让这三类 prompt 要求「先给出
   `最终答案：X`，再给推导/证明」，且 `extracted_answer` 改取答案标记而非完整
   响应（保留完整解答仍可进 `final_response`，但判分用标记后的答案）。

二者均为**跨任意样本成立的通用规则**，不绑定题号/题干，符合 AGENTS.md。是否
实施、以及是否配合 token 阶梯复测（3072 → 4096），留待决策。

## 7. 决策规则执行情况

- 规则 #1（表示问题跨 ≥3 样本 → 做通用规范化）：**未触发**——本缺陷不是
  `\pi`/变量名那类表示规范化，而是 thinking 泄漏，属输出卫生。
- 规则 #2（失败集中在证明/推导完整性 → 讨论任务型 Prompt）：**已触发**。
- 规则 #3（无明显缺陷 → 收口）：不适用，缺陷明确存在。
