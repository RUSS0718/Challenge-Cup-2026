# 挑战杯数学推理智能体：文本核对与 HTML 生成稿

更新时间：2026-09-22

核对范围：用户提供的长文本、当前 checkout `b3854f7`、仓库赛事约束、源码与官方评测归档。

## 结论先行

用户文本的主线判断基本成立：这个项目的工程优化对象不是训练新模型，而是在固定模型端点、隐藏题目分布和严格资源预算下，提高“最终可判分答案”的概率。

但这句话应标为**基于接口和运行约束的工程解释**，不能写成赛事官方定义。文本中关于实验因果、CAR/Deep/Harness 的收益，以及“当前 Router 的实际决策”的部分，需要按本稿修正。

最重要的边界是：

- `correct / incorrect / invalid / runner error` 是评测结果类别；L0–L3 是本项目用于分析失败链的内部框架，不是官方评分层级。
- 官方日志显示的是不同 commit/configuration 的快照；9 月 12 日的 29/112 是当前归档中的最高分，但同时开启了 Harness、Deep、hybrid FSDF 和 temporary answer bank，不能归因给某一个组件。
- 当前 `SUBMISSION_CONFIG` 显式打开了 Harness、Deep 和 hybrid fallback，但 Deep formation 之前的健康/能力门是 `NO_GO / NO_CAPABILITY_CONCLUSION`。这是授权覆盖或 canary，不是证据晋升。
- 当 Deep lane 开启时，`HarnessConfig.effective_call_limit` 会把 Harness 账本的 5-call 上限压到 3；但 legacy FSDF 通过独立 relay 执行，不能把这个 3-call 直接说成整个 `solve()` 的全局调用上限。

## 一、逐条事实核对

| 文本主张 | 结论 | 核对与修正 |
|---|---|---|
| 比赛更像“固定强模型 + 隐藏分布 + 预算下的 inference-time policy” | **合理解释，不是官方原话** | 与根目录 `AGENTS.md` 的接口、隐藏集、调用/时间预算约束一致；可作为项目定位，不能冒充赛事定义。 |
| 平台调用 `agent.solve(problem, metadata)`，主要看 `final_response` | **已确认** | `AGENTS.md` 明确规定接口和非空字符串 `final_response`；`README.md` 也说明返回契约。 |
| Agent 更像 LLM inference controller，Python host 才是 policy | **工程解释，基本成立** | `user_agent.py`、`reasoning_agent/math_harness.py` 中确有路由、预算、解析和 fail-closed 逻辑；“真正的 Agent”属于概念表述。 |
| L0 Runtime / L1 Closure / L2 Reasoning / L3 Success | **内部分析框架** | 有助于解释 `runner error → invalid → incorrect → correct`，但不是官方分类。应在 HTML 中加“项目分析模型”标签。 |
| 官方并发 3、单题 1200 秒、整轮 6 小时 | **已确认（以仓库赛事约束为准）** | `AGENTS.md` 记录为并发 3、单题 20 分钟/1200 秒、整轮 6 小时；公开规则原文当前未在本环境独立抓取，应保留来源说明。 |
| 多调用不一定更强，必须优化 completed/parsable/within-budget | **合理推断，证据充分** | 官方约束与实验归档中的 timeout、truncation、invalid 记录支持该结论；公式应标“工程近似目标”，不是官方公式。 |
| 仓库从多候选/投票逐步转向 bounded FSDF、CAR、Harness | **架构演进已确认；因果叙述需降级** | `docs/architecture_evolution.md` 和 `docs/excluded_approaches.md` 记录了这些家族与处置；“因为发现 X 所以转向 Y”是基于记录的解释。 |
| CAR 是 candidate-first / adaptive compute allocation | **机制描述已确认；价值判断属推断** | CAR-001/002 的规格和处置在 `docs/excluded_approaches.md` 中；不能写成已证明优于 FSDF。 |
| CAR-002 在 2048 token 下没有形成 candidate/final | **已确认** | `CAR-002B`：10/10 `finish_reason=length`，8/10 无 `CANDIDATE`；`CAR-002C`：10/10 length，CANDIDATE/FINAL/最终答案 marker 均 0。 |
| Math Harness 抽象为 Contract + Router + Ledger + Parser + recovery | **代码结构已确认；“最成熟”属观点** | `reasoning_agent/harness_contracts.py`、`math_harness.py` 和相关实验报告与此一致。 |
| Deep 是设计合理但证据未通过 | **基本已确认** | `MATH-DEEP-FORMATION-PROBE-001`：首 3/6 题均在 1200 秒边界 timeout，typed-complete 0/6，处置为 `NO_GO / NO_CAPABILITY_CONCLUSION`。 |
| Deep 已进入 submission profile | **已确认，但需加“显式覆盖/未晋升”** | 当前 `user_agent.py` 的 `SUBMISSION_CONFIG` 开启 Harness、Deep、hybrid；`README.md` 与 `excluded_approaches.md` 明确说这不构成能力证据。 |
| 四个核心能力是 mathematical capability、closure、compute allocation、reliability | **有用的项目模型，不是官方四分法** | 可保留，但 HTML 中应标注为“本文分析框架”。 |
| repo-hygiene 分支主要是架构整理，不应宣称 accuracy improved | **已确认** | `docs/architecture_evolution.md` 明确写明解析/Harness seam 拆分不改变默认路由。 |
| Deep 开启会把 Harness 5-call cap 变成 3-call cap | **代码事实，但原文需补边界** | `HarnessConfig.effective_call_limit = min(call_limit, deep_max_model_calls)`，且 `BudgetLedger` 在 route 前初始化；因此 direct/deep Harness ledger 为 3。legacy FSDF 由独立 relay 执行，不受该 ledger 的实际模型调用计数约束。 |
| “最终竞争力是 resource-aware orchestration + answer closure + conservative verification + evaluation discipline” | **总结性判断** | 与当前代码和文档一致，属于项目定位，不是可独立验证的赛事事实。 |

## 二、可直接替换的第 9 节：当前 Router 的实际决策

### 9. 当前 Router 的实际决策

当前 Router 不是“先判断题目难不难，再决定调用几次”，而是先做一个双轴合同判断：

1. **答案形态（answer shape）**：标量/选择、参数化表达式、有限集合、区间或范围、函数族、证明文本、未知。
2. **推理风险（reasoning risk）**：`direct`、`structured`、`deep`。

随后再计算路由置信度：答案形态未知、题面同时出现多个任务信号，或学科/任务信号混合时，置信度降为 low；结构化风险通常为 medium；其余才可能是 high。

当前 `HostRouter.route()` 的实际规则可以概括为：

```text
low-confidence contract
    └─ hybrid 开启 → legacy FSDF
    └─ hybrid 关闭 → unsupported / UNKNOWN

proof_text
    └─ hybrid 开启 → legacy FSDF
    └─ hybrid 关闭 → unsupported / UNKNOWN

high-confidence + direct risk + scalar/choice
    └─ Direct Harness

其余 structured/deep risk
    └─ Deep typed lane（仅当 deep_enabled）
    └─ 否则 → legacy FSDF（若 hybrid 开启）
```

因此，当前 submission profile 的语义是：

- 简单且高置信的标量/选择题优先走 Direct Harness；
- 结构化答案或更高推理风险的题目走 Deep typed lane；
- 证明题、混合题、未知答案形态和低置信题回退到 legacy FSDF；
- 若无法找到可安全解释的路由，采用 fail-closed，返回 `UNKNOWN`。

需要特别说明：路由是确定性的文本合同分类，不等于模型已经具备相应数学能力；Deep lane 被选中也不代表它已经通过 formation 或 capability gate。

证据：`reasoning_agent/math_harness.py` 中的 `HostRouter.contract()`、`HostRouter.route()`，以及 `user_agent.py` 的 `SUBMISSION_CONFIG`。

## 三、可直接替换的第 11 节：官方评测效果

### 11. 官方评测的效果：能确认什么，不能确认什么

官方日志说明了不同提交快照的实际分数变化，但不能把变化归因给单一方法。当前归档的 112 题官方结果如下：

| 日期/阶段 | 配置快照 | correct / incorrect / invalid | accuracy | 可得结论 |
|---|---|---:|---:|---|
| Run #2 | `b082c36` | 9 / 43 / 60 | 8.04% | 旧基线快照，不足以解释单组件收益 |
| Run #4 | `b8b78aa` | 9 / 83 / 20 | 8.04% | C0 answer-first + k5 + 4096 的历史快照 |
| Run #5 | `18f4f5a` / `25f99b5` | 12 / 83 / 17 | 10.7143% | hetero_k5 canary；只能说明该提交快照结果 |
| 2026-09-08 | `fc1b671` | 16 / 52 / 44 | 14.2857% | FSDF + answer-bank-on |
| 2026-09-09 | `dbf3b74` | 25 / 41 / 46 | 22.3214% | FSDF + temporary-50-bank |
| 2026-09-11 | `3ede125` | 24 / 20 / 68 | 21.4286% | Harness + Deep + hybrid FSDF + bank-on |
| 2026-09-12 | `bb31ac4` | 29 / 26 / 57 | 25.8929% | 当前归档最高，但仍是堆叠配置 |
| 2026-09-15 | `1507d3a` | 12 / 32 / 68 | 10.7143% | Harness + Deep + hybrid FSDF + bank-off + Skill-on |

从这些结果可以安全得出四点：

1. `invalid` 是实际得分损失的重要来源；可解析性和答案闭合必须单独治理。
2. 最高分 29/112 发生在多组件叠加且 bank-on 的快照上，不能写成“Deep/Harness 带来 25.89%”。
3. 2026-09-15 的 12/112 说明关闭 bank、改变 commit 和保留 Skill 后，结果可能大幅波动；它同样不能单独证明 Skill 有害或 Harness 失败。
4. 当前官方日志最强的用途是识别系统风险和验证运行可行性，不是为单个组件提供因果证明。单变量收益必须回到预注册的本地/等价冻结集 A/B，并满足健康、成本、卫生和逐题配对门槛。

这也是为什么仓库把官方结果标记为 `EXACT`（日志事实），而把“某组件带来收益”标记为 `NOT_IDENTIFIABLE` 或 `NO_CAPABILITY_CONCLUSION`。

证据：`docs/official_evaluations/README.md`、`docs/official_evaluations/INDEX.md`、各日期 `record.md` 和 `agent_analysis.md`。

## 四、建议补齐的 15–18 节（让原文编号连续）

### 15. 这些结论如何转成工程原则

- 先保证非空、可解析、可序列化的终答，再追求更长推理。
- 让预算、deadline、调用次数和恢复槽位成为显式状态，而不是隐含在 prompt 中。
- 将“答案形态”和“推理风险”分开路由；一个短答案不代表题目简单。
- 所有新机制先过零模型代码门、健康门，再谈能力 A/B；未过门不得进入默认路径。

### 16. 当前默认路径应该如何描述

当前 checkout 不是“已经证明最优的最终 Agent”，而是一个可审计、可继续实验的约束推理平台：`ReasoningAgent` 负责赛事接口，Harness 负责预算/合同/解析，FSDF 负责 legacy fallback；Deep 是显式 canary，不能写成已验证的能力升级。

### 17. 阅读官方分数时应避免的三种误读

1. 把 `invalid` 降低当成 accuracy 提升。
2. 把某个 commit 的最高分当成单一组件收益。
3. 把本地 112 题、answer bank 或 official-like hard set 的结果当作隐藏集能力证明。

### 18. 更值得继续研究的问题

下一阶段最有价值的问题不是继续堆叠 stage，而是测量当前 endpoint 的答案形成分布：候选首次形成的 token 位置、length/timeout 的条件概率、不同答案形态的闭合率，以及在这些统计量基础上设计 endpoint-compatible 的 candidate-first policy。

## 五、给 HTML 生成 agent 的结构化内容包

### 页面目标

生成一个中文单页研究型 dashboard，主题是：

> 在隐藏数学题分布与严格 inference budget 下，把有限模型智能稳定地转化为可判分正确答案。

页面不是宣传页，也不是“某个方法已经赢了”的结论页；必须突出证据等级、失败链和不可归因边界。

### 推荐页面结构

1. **Hero 区**：标题、一次性结论、四个关键词卡片：`Math capability`、`Answer closure`、`Compute allocation`、`System reliability`。
2. **比赛本质**：固定模型 + 隐藏分布 + 预算约束的流程图。
3. **失败分层**：L0 Runtime → L1 Closure → L2 Reasoning → L3 Success 的阶梯图，并标注“项目分析模型，非官方评分分类”。
4. **当前架构**：ProblemContract → HostRouter → Direct / Deep / FSDF → Parser / Evidence Ledger → `final_response`。
5. **Router 决策**：用决策树展示第 9 节规则。
6. **架构演进时间线**：投票/verify → FSDF → CAR → Math Harness；每个节点显示 `CURRENT`、`DEFAULT_OFF`、`NO_GO` 等状态。
7. **官方评测表**：使用第 11 节表格；最高分卡片必须写“stacked configuration, not causal proof”。
8. **关键实验卡片**：CAR-002C 与 Deep formation probe，显示 timeout/length/marker/typed-complete 结果。
9. **代码层核对**：展示 5-call 配置、Deep 3-call effective cap、legacy FSDF 独立 relay 的边界说明。
10. **结论与下一步**：candidate formation distribution、endpoint compatibility、answer-first closure。
11. **证据与免责声明**：列出仓库相对路径，区分 `EXACT`、`TRACEABLE`、`INFERRED`、`NO_CAPABILITY_CONCLUSION`。

### 视觉与交互要求

- 视觉风格：深色研究控制台，背景近黑，使用蓝/青表示已确认，橙色表示推断，红色表示 `NO_GO`，灰色表示未知。
- 所有分数显示 `correct / incorrect / invalid` 三元组，不只显示 accuracy。
- 鼠标悬停或点击时显示证据路径与证据等级。
- 时间线节点可展开，但不要把归档实验默认展开成大段日志。
- 图表优先使用 SVG/CSS/原生 HTML；不要依赖远程 CDN 才能显示核心内容。
- 移动端至少保证表格横向滚动、流程图可折叠、正文可读。

### 数据模型建议

```js
const evidenceLevels = {
  exact: "日志或源码直接确认",
  traceable: "可由多个一手文件复核",
  inferred: "基于证据的工程解释",
  noCapabilityConclusion: "仅证明结构/健康/失败，不证明数学能力"
};

const officialRuns = [
  {date:"2026-09-08", commit:"fc1b671", correct:16, incorrect:52, invalid:44, config:"FSDF + answer-bank-on", causal:"not-identifiable"},
  {date:"2026-09-09", commit:"dbf3b74", correct:25, incorrect:41, invalid:46, config:"FSDF + temporary-50-bank", causal:"not-identifiable"},
  {date:"2026-09-11", commit:"3ede125", correct:24, incorrect:20, invalid:68, config:"Harness + Deep + hybrid FSDF + bank-on", causal:"not-identifiable"},
  {date:"2026-09-12", commit:"bb31ac4", correct:29, incorrect:26, invalid:57, config:"Harness + Deep + hybrid FSDF + bank-on", causal:"not-identifiable"},
  {date:"2026-09-15", commit:"1507d3a", correct:12, incorrect:32, invalid:68, config:"Harness + Deep + hybrid FSDF + bank-off + Skill-on", causal:"not-identifiable"}
];
```

### HTML 生成 agent 的硬性约束

- 不得把“比赛本质”写成官方原文或官方评分公式。
- 不得把 29/112 归因给 Harness、Deep 或任何单一组件。
- 不得把本地 112 题、answer bank 命中或 `NO_CAPABILITY_CONCLUSION` 写成隐藏集能力证明。
- 不得删除 `invalid`、`timeout`、`finish_reason=length` 等失败类别。
- 代码路径使用仓库相对路径；页面内可把路径渲染为证据标签，不要硬编码开发机绝对路径。

## 证据路径

- `AGENTS.md`：赛事接口、隐藏评测、并发/时间预算、实验纪律。
- `README.md`：当前架构、提交 profile、官方评测说明。
- `user_agent.py`：`SUBMISSION_CONFIG` 与官方入口。
- `reasoning_agent/math_harness.py`：`HarnessConfig`、`effective_call_limit`、`HostRouter`、legacy adapter。
- `reasoning_agent/harness_contracts.py`：ProblemContract、Candidate、TypedParser 合同。
- `docs/architecture_evolution.md`：架构谱系与状态口径。
- `docs/excluded_approaches.md`：CAR、Deep、Harness 等实验的处置与停止门。
- `docs/official_evaluations/README.md`、`INDEX.md` 及日期页：官方日志与不可归因说明。
