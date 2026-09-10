# Curated-100：私有难题库与错题经验沉淀计划

实验/开发计划 ID：`ERROR-NOTEBOOK-CURATED-100-SPEC`

状态：`PLANNED / SERVER_BLOCKED / DEFAULT_OFF / NO_MODEL_CONCLUSION`

## 0. 先纠正一个概念

“30 道高质量题 + 70 道本地难题”首先构成一个**私有挑战语料库**，不是 100 条已经验证的
错题经验。只有题目经过 agent 实际作答、观察到可归因错误、人工审核并在 held-out 同构题上
验证后，才可以生成 `error_notebook` 的程序性经验条目。

因此本计划分成两层：

```text
answer-bearing 私有挑战库（可含题面、gold、参考解法）
        ↓ 只用于离线评测和人工审计
结构化错误记录（错误模式、纠正规则、适用边界）
        ↓ held-out 验证
只读程序性记忆/新版 Skill（可选、默认关闭）
```

不能把题目答案、完整解法或题面副本直接注入在线 `solve()`。在线匹配只能返回结构性
检查提示，不能返回答案或“这道题的解法”。

## 1. 目标与非目标

### 目标

1. 从团队自建、仿官方格式的 `eval_112.json` 中确定性挑选 30 道高质量、结构多样的题；
2. 从仓库冻结的本地难题池中挑选 70 道，和前 30 道组成 100 道 challenge bank；
3. 用统一 manifest、去重、结构标签和 hash 管理两类来源；
4. 在服务恢复后运行 baseline，收集错误、invalid、截断和 correct→incorrect 反转；
5. 将经过人工审核和 held-out 验证的错误抽象为程序性经验；
6. 单独验收“结构相似匹配器”，并保持默认关闭。

### 非目标

- 不把 100 道题的 answer/gold/solution 作为在线检索库；
- 不按 `idx`、题面原文、答案、来源标签直接路由；
- 不复活已被否决的 method-card RAG 或相似例题答案 RAG；
- 不在服务端不稳定时启动真实模型实验；
- 不修改 `SUBMISSION_CONFIG`；
- 不把“题库已构建”表述为 agent 正确率提升。

## 2. 数据隔离与 Git 安全

### 2.1 私有源文件

团队维护的 answer-bearing 内部文件固定为：

```text
reasoning_agent/error_notebook/eval_112.json
```

它含有 `problem` 和 `answer`，属于 answer-bearing 原始数据，但不是官方或隐藏评测数据。
它只用于离线题集/审计和显式 submission answer-bank 构建；已在仓库 `.gitignore` 增加精确规则：

```text
/reasoning_agent/error_notebook/eval_112.json
```

验收时必须检查：

```powershell
git check-ignore -v reasoning_agent/error_notebook/eval_112.json
git status --short --ignored -- reasoning_agent/error_notebook/eval_112.json
git ls-files --error-unmatch reasoning_agent/error_notebook/eval_112.json
```

最后一条必须失败，且不能用 `git add -f`。如果该文件曾经被跟踪，必须先停止并由用户
明确授权后处理历史；本计划不自动改写 Git 历史。

### 2.2 三层存储

| 层 | 内容 | 位置 | 是否进 Git | 是否进在线 prompt |
|---|---|---|---|---|
| Raw private | 题面、gold、参考解法、原始作答 | 本地私有目录 | 否 | 否 |
| Audit manifest | source id、hash、结构标签、选择理由、split | `docs/experiments/ERROR-NOTEBOOK-CURATED-100/` | 可 | 否 |
| Reviewed memory | 抽象错误模式、纠正规则、边界、验证统计 | `reasoning_agent/error_notebook/reviewed_experience.jsonl` 或独立版本目录 | 可 | 仅 opt-in、只读提示 |

若审核工件必须保存原题或 gold，放在被 `.gitignore` 覆盖的私有路径，不放进 tracked
experiment report；公开报告只保存 hash、计数和聚合指标。

## 3. 100 道题的组成与选择

### 3.1 30 道：团队自建 `eval_112.json`

选择脚本读取 JSON，但不把题面或答案写入 tracked 文件。固定 seed：`20260907`。

先为 112 道题生成离线结构标签（不使用 answer）：

- 领域：Algebra / Combinatorics / Geometry / Number Theory / Other；
- 任务形态：calculation / proof / construction / counting / functional-equation /
  inequality / geometry-locus / sequence / game / mixed；
- 量词与义务：universal / existence / finite-coverage / domain / substitution；
- 输出形态：integer / rational / expression / set / multi-answer；
- 题面长度与语言。

30 道的预设配额：

| 维度 | 配额 |
|---|---:|
| Algebra | 8 |
| Combinatorics | 8 |
| Geometry | 6 |
| Number Theory | 6 |
| Other/mixed | 2 |

在每个领域内优先保证任务形态多样、长度层次多样和输出形态多样；同一结构近重复只留一
道。若自动标签无法稳定区分领域，进入 `manual_review`，不强行归类。选择记录只保存
`private_source_id` 的 hash、标签和入选理由，不保存题面或答案。

### 3.2 70 道：仓库本地难题池

来源只使用已冻结且与 V4-HARD20 去重的三套池：

- `set_a_olymmath_hard.jsonl`
- `set_b_aime.jsonl`
- `set_c_hle_math.jsonl`

推荐配额：

| 来源 | 数量 | 选择规则 |
|---|---:|---|
| OlymMATH HARD | 28 | 4 领域各 7 个 problem group；每组只取一种语言 |
| AIME | 20 | 4 领域各 5 道；整数答案优先保持 exact gate |
| HLE Math | 22 | 4 领域各 5 道，余 2 道按结构稀缺性补齐 |
| 合计 | 70 | 题目与既有 V4-HARD20 零重叠 |

所有选择必须记录 `source_id`、`problem_group_id`（如有）、domain、language、answer_type、
题面 hash；OlymMATH 双语同组不得同时进入同一 split。

### 3.3 去重与 split

- 100 道 challenge bank 内按规范化题面 hash 去重；
- OlymMATH 同组跨语言视为一题，不得泄露到 train/held-out 两侧；
- 30/70 来源比例固定，不因结果临时调整；
- 其中 20 道作为 calibration（仅用于生成候选经验），80 道作为 held-out/确认池；
- 具体哪些题属于 calibration 只在 manifest 中冻结，不能按 agent 结果临时挑选。

## 4. “混在错题本中”的正确实现

不能直接把 100 道题写入当前 `error_notebook` schema，因为该 schema 明确禁止
`problem/answer/gold/solution` 字段。推荐目录：

```text
reasoning_agent/error_notebook/
  eval_112.json                    # 私有、被 gitignore，原始 source
  private_raw/                     # 私有题面/gold/参考解法（若需要）
  challenge_index.jsonl            # 可追踪的 hash/标签索引，不含题面答案
  reviewed_experience.jsonl        # 只有审核通过的抽象经验
  README.md
```

`challenge_index.jsonl` 不是答案库，每条最多包含：

```json
{
  "case_id": "cb-0001",
  "source_family": "eval112|olymmath|aime|hle",
  "source_digest": "sha256:...",
  "domain": "combinatorics",
  "task_shape": "finite-counting",
  "obligation_tags": ["finite-coverage", "existence"],
  "answer_type": "integer",
  "split": "calibration|held_out",
  "status": "challenge_only"
}
```

`status=challenge_only` 的条目不能被运行时匹配器直接渲染成 prompt。只有生成了审核通过的
经验条目后，匹配器才可以看到经验的结构字段和纠正规则。

## 5. 离线错误审计流程

服务恢复后按以下顺序执行，所有模型窗口串行：

```text
冻结 100-case manifest
  ↓
baseline（不加载 challenge index、不加载 reviewed memory）
  ↓
记录 final_response、trace 摘要、耗时、调用数、gold 对比（只在 scorer）
  ↓
筛选 incorrect / invalid / truncation / correct→incorrect
  ↓
人工审核错误是否真实、是否可归因
  ↓
生成候选经验（可参考 gold/参考解法，但只在私有审计区）
  ↓
去除题面、答案、题号、source label、hash 指纹
  ↓
写 reviewed_experience draft
  ↓
held-out 验证
  ↓
通过后才升级为 Skill/程序性记忆
```

“按照答案生成解题思路”只允许出现在私有审计阶段，作为候选解释；必须再回答：

1. 该解释是否确实对应 agent 的错误原因，而非事后合理化；
2. 纠正规则能否改写成与具体答案无关的检查程序；
3. 在 held-out 同构题上是否有效；
4. 是否引入新的误触发或 correct→incorrect。

## 6. 相似题匹配器的安全接口

未来可以增加独立、默认关闭的模块：

```text
reasoning_agent/error_notebook/matcher.py
```

窄接口建议：

```text
match_structural_memory(problem, *, top_k=3) -> tuple[MemoryHint, ...]
```

匹配输入只能来自题面结构信号：长度桶、任务形态、量词、表达式/方程计数、有限域/证明/
反例等标签。禁止使用：

- exact problem text 或 n-gram 近邻；
- answer/gold/solution；
- `idx`、source、domain 标签作为唯一触发条件；
- 题目 hash 反查；
- 返回历史题目的最终答案。

返回内容只能是：

```text
结构模式：有限域上的全覆盖计数
建议检查：先明确域大小和边界，再证明枚举没有遗漏
不要做：把有限样本测试当作全称证明
```

最多返回 3 条、每条有 `memory_id`、适用条件、禁止条件和置信等级；无可靠匹配时返回空。
匹配器不执行 verifier、不选择最终答案、不改变 D/E 候选闸门。

## 7. 分阶段计划与停止规则

### P0：现在（服务器故障期，零模型）

1. 验证 `eval_112.json` 已被精确 `.gitignore` 规则覆盖；
2. 写选择脚本和 manifest schema，但不生成 tracked 题面/答案副本；
3. 从本地三套池生成 70 道的候选 ID 清单；
4. 生成结构标签时禁止读取 answer 字段；
5. 只做 schema、hash、去重、配额和隐私测试。

通过条件：100/100 唯一、30/70 配额正确、V4-HARD20 零重叠、raw 文件不被 Git 跟踪、
manifest 可重算、零远程模型调用。

### P1：服务器恢复后的 baseline 审计

先运行 100 道 baseline，不加载 matcher、不加载 reviewed memory。若端点健康探针失败率
超过 10%，立即 VOID；不得用 retry 把坏窗口变成好结果。

记录每题的：correct/incorrect/invalid、阶段协议错误、截断、调用数、P95、source/domain/
task_shape 聚合。

### P2：错误经验生成

只从 calibration 题生成候选经验，人工审核后进入 `draft`；不得直接把 100 道全部变成经验。
每条经验必须有：

- structural trigger；
- observed mistake；
- corrective rule；
- use_when / do_not_use；
- source trace ids；
- held-out 设计；
- reviewer。

### P3：结构匹配器离线验收

使用 held-out 题和负样本，验证：

- 结构相似时能返回相关规则；
- 仅答案相同但结构不同不能匹配；
- 仅领域相同不能匹配；
- 无匹配时为空；
- 不返回题面、gold、solution、最终答案；
- top-k、长度、置信度均有上限；
- 默认关闭且不影响 FESF 调用预算。

### P4：单变量 opt-in A/B

只有 P0–P3 通过后，才设计真实模型 A/B：

| 臂 | 内容 |
|---|---|
| baseline | 当前 FESF，matcher 关闭 |
| candidate | 当前 FESF + 只读结构匹配器，其他配置完全相同 |

不同时加入新 Skill、verifier、错题本写入、预算变化或 thinking 参数变化。必须使用 fresh
题集，不能用生成经验的 calibration 题作为能力窗。

## 8. 能力与经验晋升门

结构匹配器不以“命中率”单独晋升。至少需要：

- 题面/答案/题号泄露：0；
- 错误答案检索或答案等价提示：0；
- matcher 返回越界 memory：0；
- 默认路径可观察变化：0；
- 经验条目 held-out 验证通过率达到预注册阈值；
- candidate 相对 baseline 的 correct→incorrect：0；
- 任何错误经验造成的错误 `SUPPORTED/REFUTED`：0；
- 成本和调用数不超过 baseline 预注册上限。

若任何经验无法确认真实错误原因，标记 `rejected`，不进入 matcher。若端点异常，标记
`VOID`，不据此修改经验。

## 9. 工件

计划目录：

```text
docs/experiments/ERROR-NOTEBOOK-CURATED-100/
  spec.md
  run_manifest.json
  challenge_index.jsonl
  selection_audit.json
  baseline_answers.jsonl       # 若含原题/答案则必须在私有 ignored 路径
  error_candidates.jsonl
  held_out_report.json
  matcher_acceptance_report.json
  result.md
```

公开 tracked 工件不得含 raw `problem`、`answer`、`gold`、完整 prompt 或完整模型响应；
只能含 hash、计数、标签、状态和聚合统计。每阶段结束先写 report，再更新
`docs/excluded_approaches.md`，最后才决定下一阶段。

## 10. 当前结论与下一步

当前服务器故障期间不启动 P1–P4，不生成在线经验，不打开 matcher。立即可做的只有：

1. 完成私有源文件的 Git 隔离；
2. 写 P0 选择/去重/manifest 工具；
3. 在不读取答案的前提下准备 30/70 候选索引；
4. 等端点健康后再做 baseline 错误审计。

本计划通过后仍不能直接提交 GitCode，也不能声称正确率提升。它只为后续长时间本地评测
建立可审计、不可泄露、可撤销的经验沉淀路径。
