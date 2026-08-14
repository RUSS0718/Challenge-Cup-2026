# 13.2 实验 F0：离线可行性验证（行级结构语法收紧）

## 目的

实验 E 失败后，F 从解析层收紧：答案标记/正文标题必须是**独立结构行**，而非嵌在
thinking 句子、约束说明、引号、列表里的伪标记。F0 先离线验证——在同一批原始响应
上比较 C2+D 解析 vs F 解析，**不花模型调用**，证明「能在相同模型输出上安全改善」
后再跑在线双轮。

## 方法

1. `evaluate_token_ladder.py` 加 `--save-raw-dir`，把每题主调用完整响应 dump 到
   Git 忽略目录 `docs/13_2/raw_dump/`。
2. 跑一次 C2+D 基线（48 题，3072/temp0.6/workers3），得到 48 份原始响应。
3. `scripts/compare_f_parser.py` 对非数值题型 30 题，分别跑 C2+D 解析与 F 解析。

## F 三状态行解析器（`parse_structure_f`）

- 状态机 `PREAMBLE → ANSWER → BODY`，逐行扫描。
- 答案标记必须是独立结构行（行首，允许 `**…**` 粗体包装）；嵌在句子、约束说明、
  引号、Markdown 列表里的「最终答案」不识别。
- `…`、`[Core Answer]`、`[Option Letter]`、`<…>` 一律视为占位符拒绝。
- 正文标题支持中英文 + 安全 Markdown 变体 + `Proof Block:` 等 block 后缀。
- 不在正文内部按 thinking/analysis 词删句；无可靠结构返回原始响应（不具备重建条件）。

16 项通用单测（不绑题号）全过，全量 213/213。

## 离线对照结果（非数值题型 30 题）

| 门槛 | 结果 |
| --- | --- |
| 1. 干净响应保持不变 | ✅ 4/4（C2+D clean+correct 的题，F 也 clean 且有答案） |
| 2. 不删除有效证明正文 | ✅ structured=29 全部 body 非空 |
| 3. 不把元分析识别成答案 | ✅ 0 题误判 |
| 4. 无可靠结构明确返回 | ✅ no_answer_block=1、no_body=0，重建返回原始响应 |

## 关键发现：F 安全、有局部收益，但污染集中在 length 截断

**F 修正了 C2+D 的 2 题 extracted_answer 误判**（把 thinking 复述当答案）：

| idx | C2+D extracted（误判） | F answer（正确） |
| --- | --- | --- |
| 6003 | `*The prompt asks to "derive…and f…` | `2` |
| 6016 | `*The prompt asks to "explain why…` | `该齐次方程组有非零解，答案为 1` |

**但 F 无法消除的 7 题 thinking 污染，全部是 `finish_reason=length`**：

- 6 题：正文内部的自我检查（`Wait, checking the instruction…`、`Wait, I should
  check…`）被 length 截断卡在正文里——F 规则明确「不在正文内部做关键词删除」，
  故保留；
- 1 题（6006）：length 截断导致答案块未输出，`no_answer_block`。

**这不是 F 的解析缺陷，而是 token 预算不足**：模型在 3072 内没写完正文，中途插入
self-check 后被截断。F 的行级收紧解决不了「截断导致正文未完成」。

## 结论与分流

- **F0 通过**：F 解析器是安全的（4 项门槛全过），且有局部收益（修正 2 题 extracted
  answer 误判），可以接入（无副作用）。
- **但 F 无法把 final_response 污染降到 5%**：剩余污染全部集中在
  `finish_reason=length` 的正文内部 self-check（6/30 = 20%）。
- 命中用户分流规则「**F 未通过，但失败集中于 length + 无真实答案块**」→ 可讨论一次
  受控的 3072 vs 4096。已满足的条件：
  1. 不可恢复污染 7/7 都以 finish_reason=length 结束 ✅
  2. 部分题两次调用仍无真实答案块（6006 no_answer_block）✅
  3. 不是 stop 状态下的格式复述（7 题全 length）✅

## 原始数据

- `docs/13_2/raw_dump/raw_token3072_temp0.6.jsonl`（48 题完整响应，Git 忽略）
- `docs/13_2/f0_baseline.json`（C2+D 基线汇总）
