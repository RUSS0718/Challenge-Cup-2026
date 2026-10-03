# GRH v1.3 全架构重设计实验计划

日期：2026-10-03  
状态：研究设计与实验预注册草案；**不修改生产代码、不修改 `SUBMISSION_CONFIG`、不产生官方候选**。

本文回答一个具体问题：在不把 ARM 简单替换成另一个“更漂亮”的框架的前提下，如何依据 [`evaluation_adoption_提分行动_2026-08-29.md`](../../research/evaluation_adoption_提分行动_2026-08-29.md) 重组整个答题链路，把一部分 `invalid` 安全地转成 `correct`，同时避免 `invalid→incorrect`、`correct` 被破坏、超时和调用成本恶化。

## 1. 先固定事实、推断和未知项

### 1.1 已确认事实

来自 `current_invalid_telemetry_2026-10-03.md` 及对应运行工件：

- proxy-221 Thinking ON：`106 correct / 10 incorrect / 105 invalid`，模型调用 417。
- eval-112 Thinking ON：`2 correct / 6 incorrect / 104 invalid`，模型调用 225。
- proxy-221 的 105 个 invalid 中，69 个至少出现一次 `finish_reason=length`，86 个第二样本为 `no_value`，所有 invalid 的 verification 都是 `NOT_APPLICABLE`。
- eval-112 的 104 个 invalid 中，92 个至少出现一次 `finish_reason=length`，100 个第二样本为 `no_value`，所有 invalid 的 verification 都是 `NOT_APPLICABLE`。
- `candidate_count=2` 只表示 harness 记录了两个候选，不表示候选独立、完整或数学正确。
- v1.3 已发现并修正冲突候选在 `UNKNOWN` 情况下被错误计入救回的问题；此前报告的 9 个救回最多只能计为 6 个安全 host replay 救回。这 6 个是**已有响应证据的离线重放结果**，不能直接宣称新增数学能力。
- [`docs/excluded_approaches.md`](../../excluded_approaches.md) 与实验总规范要求：共享端点实验串行、单变量归因、完整 manifest/report、先判健康/VOID 门，再判能力门；只降 invalid 而不增 correct 只能称为 hygiene improvement。

### 1.2 数据支持的推断

1. 当前最大缺口可能是候选闭合、截断后的提交、第二路线无有效增量和缺少确定性验证，而不是单纯需要更多自由推理。
2. 一部分 invalid 可能属于 R3/R4（候选已存在但最终化或解析失败），适合 host-side rescue；R1（推理本身没有可复核候选）不能靠格式修复变成正确。
3. ARM 中的 Router、Safe Candidate、Candidate Ledger、Verifier Adapter 等组件可能仍有价值，但 ARM 作为一个全包式状态机没有足够的单组件因果证据。这里采用“保留可验证组件，重组边界，逐步验收”的方案。

### 1.3 尚未验证的假设

- Thinking ON 是否在隐藏分布产生更多可验证正确候选。
- 一次有界 finalizer 是否能减少 invalid，且不会改变已确认数学值。
- 题型级确定性验证是否能稳定实现 `invalid→correct`，而不是 `invalid→incorrect`。
- 自适应计算分配是否优于固定调用预算；不得用外部模型论文的结果替代本项目的配对实验。

## 2. 设计原则：重组 ARM 的职责，不换皮复刻另一个大框架

新的架构不是“ARM v3”或另一个黑盒 Agent 框架，而是五层可审计管线。每层有单一职责、输入输出契约和独立关闭开关：

```text
Problem
  ↓
Task Contract + Risk Features       （host，零模型调用）
  ↓
Route Plan                          （OFF direct / ON deep / bounded alternate）
  ↓
Candidate Ledger                    （候选、来源、完整性、状态）
  ↓
Evidence Gate                       （结构检查 + 确定性局部验证）
  ├─ PASS → Safe Selection → ARH Serializer → final_response
  ├─ CONTRACT_ERROR → 一次有界 Finalizer 或 host serializer
  ├─ CONFLICT/NO_VALUE → 一次不同路线 recovery；无证据则 UNKNOWN
  └─ FAIL/UNKNOWN → 保留安全 incumbent 或 fail-closed
```

### 2.1 ARM 组件的处置

| ARM 组件 | 新架构中的位置 | 处置 | 安全边界 |
|---|---|---|---|
| Router | Route Plan 的候选输入 | 保留为 host 特征路由，先 shadow | 不能单凭题长决定 ON/OFF；不能读取 gold |
| Safe Candidate | Candidate Ledger 的不可变 incumbent | 保留 | 弱候选、resolver 或 finalizer 不得覆盖已确认 incumbent |
| Dual Candidate | 路线多样性记录 | 保留但收紧 | 两个候选必须来自不同方法族且都闭合，不能把重复自由推理当多样性 |
| Resolver | Conflict/contract repair 的有界动作 | 缩减 | 只能选择/修复已有候选，不得重新完整求解；最多一次 |
| Deterministic Verifier | Evidence Gate | 提升为主决策层 | 只返回 `PASS/FAIL/UNKNOWN`；模型自报 CHECK 不算证据 |
| Thinking Switching | Route Plan 中 request-scoped mode | 条件保留 | 接口不支持逐调用模式时回退到同一模式 + host parser，不增加伪调用 |
| ARM state machine | 编排实现 | 暂不重写为 LangGraph；先用现有 imperative runtime 旁挂 sidecar | 只有两个以上已过门动态分支需要共享预算时才做 FSM sidecar |

这满足“重新设计整个架构”的要求，同时避免因换名而绕过已有 ARM 失败证据。任何组件只有在独立实验过门后才可进入下一层融合。

## 3. 目标失败分类与可救援边界

每题只保留一个主失败类别，允许附加遥测标签；分类必须在不读取 gold 的情况下完成，gold 只在离线 evaluator 中用于最终转移统计。

| 类别 | 判定特征 | 可用动作 | 允许目标 |
|---|---|---|---|
| R1 reasoning failure | 没有闭合候选，或已有候选通过局部反例 | 不强行救援；必要时 UNKNOWN | 不宣称 rescue |
| R2 decision failure | A/B 候选闭合但未裁决、选择理由不足或错误覆盖 | 先确定性比较，再一次 bounded resolver | 只接受独立证据支持的 candidate |
| R3 finalization/truncation | 截断或尾部污染，但截断前已有完整候选 | safe incumbent + host serializer；必要时短 finalizer | invalid→correct；不得改值 |
| R4 parser/contract failure | 值可能存在，boxed、单位、集合、多问或字段未抽出 | typed parser、canonicalizer、ARH 双形态 | invalid→correct；解析不清则 UNKNOWN |
| R5 evaluator boundary | 题型/等价关系或判分器边界争议 | 记录 evaluator issue；并行 Math-Verify 仅作诊断 | 不用放宽 judge 伪造正确率 |
| R6 health/timeout | API error、timeout、缺响应或资源超限 | 保留已验证 incumbent；禁止无界重试 | 仅在 contract 和 evidence 都安全时提交 |

核心转移矩阵必须逐题报告：

- `invalid→correct`（Invalid Rescue）
- `invalid→incorrect`（Invalid Damage）
- `correct→incorrect` 与 `correct→invalid`（Correct Damage）
- `Net Correct Gain = new correct - lost correct`

## 4. 实验总契约

### 4.1 固定对照与数据层

1. **健康锚**：冻结当前官方健康配置（优先 `hetero_k5` 对应固定 commit）；若提交 profile 仍是 v1.1，则先记录实际 commit、配置 hash 和 `SUBMISSION_CONFIG`，不能把 v1.2 或未验证 v1.3 当 baseline。
2. **开发层**：proxy-221，仅用于工程和逐题 ledger。
3. **能力层**：按实验规范使用 `core120_v2` 两轮；如果该层尚未就绪，不得把 221 的结果称为能力门。
4. **确认层**：`confirm30_v2` 或预注册的独立确认池。
5. 所有能力比较使用相同 model、endpoint、evaluator、canonicalizer、题序交错和请求契约；共享端点实验串行。

### 4.2 预算硬约束

在实验中预注册并写入 manifest，不能出现 v1.3 已暴露的“manifest 为 3 calls、实际 profile 为 5 calls”不一致：

- 每题最多 3 次逻辑模型调用；
- 每题请求 token 总预算不超过 16,384；
- 官方候选预计整轮不超过 5.5 小时；官方约束仍是并发 3、单题 20 分钟、整轮 6 小时；
- health retry 最多 1 次且计入调用/成本；不以 retry 掩盖 endpoint 不健康；
- 任何 pending future 在 hard deadline 必须硬取消并写 VOID，不允许线程池退出继续等待导致越过墙钟上限。

建议的实验起点（最终数值以 manifest 为准）：

| 路径 | 调用 1 | 调用 2 | 调用 3 | 最坏请求 token |
|---|---:|---:|---:|---:|
| easy | OFF solver 2,048 | 不调用或 host verifier | 仅协议修复 1,024 | 3,072 |
| hard | ON solver 8,192 | 不同路线 4,096 或 bounded verifier | 不改变值的 finalizer 2,048 | 14,336 |
| no-mode fallback | 同一模式 solver | host extraction/verification | host serializer | 以一次模型调用为上限 |

若 endpoint 不支持 ON/OFF request-scoped 参数，不能为了模拟 OFF 再发一个长调用；最终化由 host serializer 完成。

### 4.3 必备产物

每个实验目录必须含：

- `preregistration.md`：假设、唯一变量、臂、预算、停止条件、VOID 条件；
- `run_manifest.json`：commit、profile、dataset hash、model/endpoint、temperature、max_tokens、workers、retry、deadline、启用的 P0/P1/P2/P3 开关；
- `answers.jsonl`：逐题原始 response 摘要、candidate ledger、finish_reason、usage、latency、decision record；不要把 gold 写入 solver 输入；
- `report.json`/`result.md`：五数、转移矩阵、calls/tokens/latency 平均和 P95、候选完整率、验证状态；
- `disposition.md`：`PASS/FAIL/VOID/ARCHIVED/FORMAL_PASSED` 及下一步；
- 所有 artifacts 写入 `artifacts/<run_id>/`，不把 raw dump 写入 `docs/experiments/`。

## 5. P0：架构冻结、健康和证据账本

### 目标

先证明新架构可审计、可回滚、不会因 runner 或 parser 缺陷制造假提升；本阶段不测试新的 reasoning 能力。

### 实施步骤

1. 记录健康锚的 commit/config/input hash，并对 v1.1、v1.2、v1.3 工件做只读核对。
2. 修订 invalid ledger：每题唯一主分类 R1–R6，附加 `finish_reason=length`、`candidate_count`、`answer_complete`、`verification_status` 等标签。
3. 实现/验证零调用 host replay：typed extraction、canonicalizer、ARH 双形态、safe incumbent、冲突 fail-closed。
4. 执行 preflight：3/3 轻量请求成功、零 model error、零 deadline、零 orphan；manifest 与实际 profile 一致。
5. 做 A/A 顺序与噪声自测，按总规范的 Pre-P0 门判定；失败即 VOID，不启动 P1。

### P0 验收条件

- 221/221 逐题记录齐全，raw response hash 可追溯；
- parser/canonicalizer 单测覆盖 boxed、末行、分数、集合、向量/矩阵、单位、多问、占位符、冲突和括号失败；
- `unknown`、`invalid`、health error 分母分开；
- host replay 不产生 `invalid→incorrect`、`correct→incorrect` 或 canonical value 改写；
- manifest 声明的 calls/tokens/deadline 与实际运行一致；
- 任一完整性、健康或接口门失败，状态为 `VOID`，不得进入 P1。

### P0 回滚

删除/停用新 parser 或 ledger 开关，恢复健康锚的原始 finalization；保留 artifacts 和失败 disposition，不重写历史结果。

## 6. P1：零调用输出契约与 ARH 复评

### 唯一变量

只加入 host-side Task Contract、typed parser、canonicalizer 和 ARH：

```text
最终答案：<canonical>
$\\boxed{<canonical>}$
```

仅对 numeric/finite answer 族启用；证明/推导类仍使用原正文重建。P1 不增加模型调用、不增加 token、不引入 LLM judge 或 PRM。

### 实施步骤

1. 从 baseline raw response 生成 Candidate Object：`value/type/source/completeness/confidence/reasoning_status`。
2. 运行结构完整性和题型专用 canonicalization；集合顺序、最简分数、单位和多问必须遵守 Task Contract。
3. 用同一 evaluator 重判 baseline 与 P1，生成逐题转移矩阵；并行 Math-Verify 只作差集诊断，不能替代 native judge。
4. 对 host replay rescue 做双轮交错重放；不将 6 个 safe replay rescue 直接记作能力提升。

### P1 验收条件

- `invalid→correct >= 1` 且 `invalid→incorrect = 0`；
- `correct→incorrect = 0`、`correct→invalid = 0`；
- parser/judge coverage 不降低，ARH 双形态 canonical 一致率 100%；
- 平均 calls、tokens、P95 latency 与 baseline 相同（零新增调用）；
- 若只减少 invalid 而 correct 不增加，处置为 `HYGIENE_ONLY`，不能晋升为能力方法。

### P1 回滚

任何 canonical value 变化、集合/多问误合并、单位丢失、evaluator 覆盖错误或 invalid→incorrect 出现，立即关闭 ARH，回到 host 原始 serializer；保存差集供后续 parser 修复，禁止放宽 judge。

## 7. P2：证据门与路线多样性候选

P2 遵守实验规范中的 GSA 顺序：`O=hetero_k5` 健康锚，`M=hetero_k4_sc`，`G=hetero_k3_gsa`。这里的 GSA 只是一种候选聚合实验，不等于把 ARM 整包换成 GSA；所有新架构层均需独立开关。

### 唯一变量与候选形态

- 前两次生成使用相同基础 prompt，但第二路线必须显式属于不同方法族（例如代数变形 vs 直接枚举/边界检查），不接受仅改写表述的重复样本。
- 候选写入 ledger，包含 `route_id`、`candidate_id`、`complete`、`source_span_hash`、`verification_status`、`conflict_set`。
- 聚合器只能在候选已闭合、契约可比且没有确定性 FAIL 时选择；无法判断则 `UNKNOWN`。
- 聚合失败回退前三候选的确定性选择，不能让 aggregator 自己重新求解。

### P2 实施步骤

1. Fidelity probe：固定 12 题验证 3+1 transcript、聚合解析和 fallback；不通过即 VOID。
2. legacy84 探索：只测候选独立性、局部验证覆盖和预算，不根据单题调 prompt。
3. `core120_v2` 两轮正式：G vs M 的 paired sign test；G vs O 各数据集不净负。
4. `confirm30_v2` 确认；每轮完成 report、manifest 和 disposition 后才进入下一轮。
5. 若 GSA 独立 `FORMAL_PASSED`，先以无 ARH、无 finalizer 的单变量候选申请官方 canary；后续 ARH 另做零调用附加实验。

### P2 验收条件

沿用总规范的硬门：

- fidelity：3+1 transcript 正确，聚合可抽取至少 11/12，context/model error=0；
- 能力：`G vs M` item-cluster `b>c` 且双侧 `p<0.05`；
- 整包：G vs O 在每个固定数据集不净负；
- 调用：mean/P95 calls ≤4（或更严格的正式 profile 上限）；聚合解析率 ≥98%；context overflow=0；
- 转移安全：`invalid→incorrect` 不得超过预注册上限，`correct damage` 不得形成稳定方向；仅 invalid 下降而 correct 不升则不晋升。

### P2 回滚

Fidelity、健康、能力或成本任一失败，停止 GSA 运行，恢复 O 健康锚；保留候选账本用于诊断，但不把 GSA 与 refine、ARH、RAG、工具同时叠加。

## 8. P3：有限升级、确定性验证与自适应预算

P3 不是“再叠几次 LLM”。只有一个方法在 P2 正式通过后，才能从总规范队列中按序挑选一个：Key-Condition Verification、Step-Back、Least-to-Most、Self-Discover 或 PS+。每次只变一个变量。

### P3 推荐顺序

1. **Key-Condition Verification**：对已有候选检查关键条件，最多 5 calls 的旧规范上限必须重新按当前官方 profile 审计；优先缩到单题最多 3 个逻辑调用。
2. **Deterministic local verification**：代入、范围、单位、模、有限枚举、受限符号等价；返回三态，不把模型生成的 CHECK 当证据。
3. **Bounded finalization**：只在闭合候选存在且仅有 contract 错误时使用；输入 Candidate Object + Task Contract，禁止改数学值。
4. **Adaptive compute**：最后评估 easy→OFF、hard→ON、冲突→一次不同路线；路由特征只能来自题面和运行中 host 状态，不可使用 gold、题号或 answer bank。

### P3 验收条件

- 两轮同题交错 paired run；每轮包含完整九格转移矩阵和失败分类；
- `Net Correct Gain >= +2`；
- `Invalid Rescue >= Invalid Damage + 2`；
- `Correct Damage <= 2`；
- error/timeout 增量不超过 1 题；
- mean calls 增量不超过 0.5/题，P95 latency ≤ baseline 的 120%；
- 固定能力池不净负，且正式 item-cluster 门满足 `b>c, p<0.05`；
- finalizer 改值次数为 0；任何改值都触发 fail-closed；
- 不使用无界 rollout、LLM judge 替代 deterministic verifier、RAG/工具/MCP 或运行时框架迁移作为隐含变量。

### P3 回滚

任一轮出现 `invalid→incorrect` 扩张、stable correct damage、timeout/cost 超门、route misclassification 或 finalizer value change：

1. 先关闭 finalizer/adaptive 分支；
2. 回退到已通过的最强单方法（优先 P2 winner，否则 O 健康锚）；
3. 将失败实验标记 `ARCHIVED` 或 `VOID`，写回 `excluded_approaches.md`，不得改名重跑；
4. 若只是 parser/serializer 问题，允许零调用修复后重新立项；若是能力失败，不得用放宽 evaluator 复活。

## 9. 统一验收矩阵

| 维度 | 必须记录 | 通过条件 | 失败处置 |
|---|---|---|---|
| 正确性 | correct/incorrect/invalid/error、四类转移 | formal paired 门通过 | 回滚到最强已过门方法 |
| 候选质量 | marker、complete/weak、candidate_count、conflict | complete rate、独立路线率达到预注册值 | 收紧 route/contract，不增加自由 rollout |
| 验证 | 每个 check 的 PASS/FAIL/UNKNOWN、witness、耗时 | deterministic false-positive=0；unknown 不冒充 pass | 关闭该 verifier 或退回 UNKNOWN |
| 输出卫生 | boxed、canonical、单位、多问、parser coverage | 双形态一致，ARH 不改值 | 关闭 ARH，保留差集 |
| 决断 | decision completion、stability、resolver A/B/UNKNOWN | candidate 稳定性不低于 baseline | 禁止弱候选覆盖 incumbent |
| 健康 | model error、timeout、orphan、finish_reason、P95 | 0 orphan；error/timeout/cost 在门内 | VOID 或立即回滚 |
| 复现 | commit/config/input hash/seed/order | manifest 可重建，双轮结果可追溯 | VOID，不作能力结论 |

## 10. 结论与实施优先级

### P0（必须先做）

- 完成 invalid ledger、完整 telemetry 和 hard deadline VOID；
- 重新核对 v1.1/v1.2/v1.3 实际 profile；
- 保留 ARM 的 Safe Candidate、Router、Verifier Adapter，但拆开开关；
- 先做零调用 host replay，确认真实 R3/R4 救援上限。

### P1（最小提分杠杆）

- Task Contract + typed extraction + canonicalizer + ARH；
- 目标是把“已有值但不可判”的 invalid 转为 correct，零新增模型调用；
- 任何 invalid→incorrect 或 correct damage 立即回滚。

### P2（能力变量）

- 严格按 O/M/G 三臂验证路线多样性和聚合；
- 不与 refine、ARH、RAG、工具同时叠加；
- 通过正式门后才申请官方 canary。

### P3（决策与预算）

- 在已通过的候选上加局部确定性验证、一次 bounded finalizer 或 adaptive route；
- 先验证 invalid rescue/damage，再谈更长 Thinking；
- 运行时间、calls 和 P95 不能以正确率名义放宽。

最重要的工程判断是：`invalid→correct` 可以作为明确目标，但必须由“已有候选证据 + 题型契约 + 可复核验证 + 保守序列化”共同完成。将所有 invalid 视为“模型其实已经做对”会把 R1 reasoning failure 和 R5 evaluator boundary 混入救援池，最终更容易得到 `invalid→incorrect`。新架构应让 ON/ARM 负责产生和保存候选，让 host 负责验证、裁决、压缩和提交；若 endpoint 不支持 request-scoped OFF，直接使用 host serializer，不用额外模型调用模拟一个不存在的模式。

## 参考

- [`docs/research/evaluation_adoption_提分行动_2026-08-29.md`](../../research/evaluation_adoption_提分行动_2026-08-29.md)
- [`docs/research/10.3/current_invalid_telemetry_2026-10-03.md`](current_invalid_telemetry_2026-10-03.md)
- [`docs/research/10.3/reasoning_compute_allocation_research_2026-10-03.md`](reasoning_compute_allocation_research_2026-10-03.md)
- [`docs/experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md`](../../experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md)
- [`docs/excluded_approaches.md`](../../excluded_approaches.md)
- [`../10.3/grh_v13_acceptance_audit_2026-10-03.md`](../../../Challenge-Cup-2026-v11-release/docs/10.3/grh_v13_acceptance_audit_2026-10-03.md)
