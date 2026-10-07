# Error Notebook Audit：合规离线错题审计计划

状态：`PREREGISTERED / TEAM-DATA-ALLOWED / DEFAULT_OFF`

## 0. 重要边界

`reasoning_agent/error_notebook/eval_112.json` 是团队自行编写/整理的、仿官方格式的
answer-bearing 内部题集，不是官方评测原题或隐藏题目。它可以被指定的离线评测、人工审计
和显式 submission answer-bank 构建脚本使用，但不自动成为在线错题记忆或 capability 证据。
真正的官方评测题、隐藏题目及其答案仍不得读取、解析、导入、检索或用于生成运行时记忆。
该文件继续保持本地受控并不得进入 Git tracked files。

本计划只允许使用：

1. 赛事规则明确允许的公开题集；
2. 团队自建的 `eval_112.json` 或其他有审核记录的本地题集；
3. 有来源、许可证和标准答案的本地自建难题；
4. 评测后人工抽象出的、删除题号/原文/答案/来源指纹的经验条目。

如果无法证明一份题目材料是公开且允许使用的，默认按受限评测数据处理，不纳入本实验。

## 1. 实验目标

建立“评测后离线错题审计 → 通用错误模式 → held-out 验证 → 版本化 Skill”的流程，
而不是建立一个隐藏题答案检索库。

本实验不做：

- 根据官方原题或答案生成运行时提示；
- 按题号、题面指纹、数据来源或答案检索相似题；
- 在一次评测过程中在线写入或读取错题记忆；
- 将完整解题过程直接复制进 `error_notebook` 运行时目录；
- 通过改名、混淆或 `.gitignore` 绕过数据约束。

## 2. 数据组成

总量固定为 100 题，来源互斥、一次冻结：

### A30：公开外部难题

- 30 题；
- 每题记录公开来源、许可证、题目组 ID 和 gold hash；
- 不得与历史 FSDF/FESF 实验题目重叠；
- 不得来自官方隐藏评测或未授权导出的评测文件。

### B70：本地自建难题

- 70 题；
- 由项目成员独立编写或从允许使用的公开材料重新构造；
- 不复制官方评测题面，不使用官方题目作为同构模板；
- 每题必须有人工审核的标准答案和解题要点，gold 只进入离线 scorer。

建议按结构而非竞赛标签分层：

- 证明/全称覆盖；
- 符号变形与定义域；
- 有限枚举与计数；
- 反例与存在性；
- 多步骤代数/不等式；
- 几何或文字建模；
- 混合约束题。

来源层只用于审计报告，不得成为运行时路由条件。

## 3. 数据分割

100 题冻结后分为：

| 分区 | 数量 | 用途 |
|---|---:|---|
| discovery | 50 | 发现重复错误模式，允许查看 gold |
| review | 20 | 人工确认错误解释是否真实、是否可泛化 |
| held-out | 30 | 不得参与经验编写，只用于最终验证 |

分割按题目组去重。相同题目的语言改写、数字替换或结构微调必须放在同一组，不能跨分区。

## 4. 离线审计流程

```text
本地评测 answers/trace/gold
        ↓
筛选 incorrect、invalid、correct→incorrect
        ↓
生成候选错误解释和参考解法
        ↓
人工确认：错误原因是否真实
        ↓
删除题号、原文、答案、来源指纹
        ↓
写入候选经验
        ↓
在 review/held-out 上验证
        ↓
合格后才升级为版本化 Skill
```

“按照 gold 生成解题思路”只允许出现在离线 discovery 工件中，用于提出候选解释；
它不等于证明模型当时能发现该解法，也不能直接进入运行时。

## 5. 错题本条目格式

运行时可见条目只能描述结构性规则：

```json
{
  "entry_id": "universal-coverage-before-finite-check",
  "pattern": "有限样本被当作全称证明",
  "domain": "proof",
  "mistake": "验证了若干取值但没有覆盖量词范围",
  "corrective_rule": "先提取量词并明确覆盖义务；有限测试只能搜索反例",
  "use_when": "题目要求任意、所有或每个对象满足条件",
  "do_not_use": "题目只要求检查明确列出的有限集合",
  "source_trace_ids": ["audit-2026-09-pattern-01"],
  "validation": {
    "status": "validated",
    "held_out_total": 8,
    "held_out_pass": 7
  }
}
```

禁止字段包括：

- `problem_text`；
- `answer`、`gold_answer`；
- `raw_prompt`、`raw_response`；
- `solution`、`reference_solution`；
- 官方题号、原题 hash 或可恢复来源的指纹。

## 6. “相似题匹配”的合规替代

不能把团队 112 题集或任何官方题集作为在线相似题答案检索库。若需要运行时识别适用经验，只允许匹配已经审核的
结构特征，例如：

```text
全称量词 + 有限测试迹象
符号分母 + 未给定义域
存在性要求 + 缺少 witness
有限域 + 要求全部覆盖
```

匹配结果只能加载一条程序性检查规则，不能返回相似原题、答案或完整解法。

该匹配器必须：

- 默认关闭；
- 不读取 A30/B70 的原始题面；
- 不按题号、source、domain 标签直接路由；
- 不返回答案候选；
- 在不确定时返回空匹配；
- 通过 held-out A/B 后才允许考虑启用。

## 7. 验收门

### 数据合规门

- `eval_112.json` 不在 Git tracked files 中；
- capability/health/A-B 的 `user_agent.py`、Skill、错题本 validator 和运行时模块不读取该文件；
- submission answer-bank 使用必须显式配置、单独标记并与模型能力统计分离；
- 运行时资源中不存在官方题面、答案或可逆题目指纹；
- 每个 A30/B70 条目都有来源和许可证记录；
- 题目组没有跨 discovery/review/held-out 泄漏。

### 泛化门

- 每条经验至少有 3 个 discovery/review 支持样例；
- held-out 至少 5 个同结构案例；
- held-out 通过率至少 80%；
- 经验条目不得绑定具体数字、变量名、题号或固定答案；
- 人工审核确认“错误原因”而不是 gold 事后合理化。

### 运行时安全门

- 默认不加载错题本；
- 不产生额外模型调用；
- 不改变 baseline 的 token/call budget；
- 匹配失败时不影响自由求解；
- 错题经验不能直接写入 `final_response`；
- 任何不确定匹配返回空或 `UNKNOWN`。

## 8. 工件布局

```text
docs/experiments/ERROR-NOTEBOOK-AUDIT-001/
  spec.md
  dataset_manifest.json
  discovery_cases.jsonl
  review_cases.jsonl
  held_out_cases.jsonl
  raw_audit/              # 仅离线，禁止运行时导入
  candidate_patterns.jsonl
  reviewed_patterns.jsonl
  report.json
  result.md

reasoning_agent/error_notebook/
  schema.py               # 只验证抽象条目
  schema.json
```

若原始评测材料的公开性无法证明，应放在仓库外的受控目录，不应仅依赖 `.gitignore`。
本项目不自动移动、删除或读取该材料。

## 9. 启动顺序

1. 先确认 A30/B70 与团队 `eval_112.json` 的来源、权限和用途边界；
2. 冻结 manifest、题目组划分和 gold hash；
3. 运行 discovery，生成候选错误模式；
4. 人工审核并删去题面/答案/来源指纹；
5. 运行 held-out 验证；
6. 通过后才生成新的 Skill 版本；
7. 对 Skill 做独立代码验收；
8. 最后才做默认关闭的 opt-in A/B。

当前不启动真实模型窗口，也不修改 `SUBMISSION_CONFIG`。
