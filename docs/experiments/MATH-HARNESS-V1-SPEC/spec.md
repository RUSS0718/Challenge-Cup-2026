# MATH-HARNESS-V1：约束适配的数学推理 Harness 改造计划

状态：原始 V1 已完成代码验收与诊断运行；本次修订规划针对性加强，未修改
`SUBMISSION_CONFIG`、提交仓库 main 或发布指针。

## Problem Statement

当前系统已经积累了 FSDF、CAR、FESF、CoD、Re2、PS-C 等多条求解路线。可复核证据显示，固定五阶段 handoff、预算交换、强制候选 marker、thinking-on 端点兼容性和若干旧候选均没有形成可晋升的稳定能力结论；最近的 FSDF 协议稳定性窗口还出现阶段 timeout、D→E 缺失和 E `finish_reason=length` 饱和。继续在 FSDF 内增加 handoff、预算或 finish 开关，会把协议可靠性问题与数学能力问题继续耦合。

公开的 Kaggle/AIMO 高分方案提供了可迁移的机制线索：有限的独立解题轨迹、题内状态与证据记录、工具反馈、证据驱动的早停、资源预算和压力测试。它们同时依赖 H100/vLLM、并行采样、streaming/logprob、持久 sandbox 或训练运行时，这些并不属于本仓库的公开平台契约，不能原样复制。

本项目需要一个适配本仓库约束的新架构，目标不是复刻某个冠军，而是在官方只保证 `client.chat(messages, temperature, max_tokens)`、官方并发为 3、单题最长 20 分钟、整轮最长 6 小时的条件下，提高可观察的正确答案产出，同时不牺牲提交兼容性、题目隔离和可审计性。另一个必须明确的事实是：`temporary_answer_bank` 是 submission 能力，不是模型能力；本地真实解题能力、健康和 A/B 实验必须关闭它，线上提交与 submission simulation 才能开启它。

2026-09-10 的 `MATH-HARNESS-EVAL112-SMOKE-001` 暴露了原始规格没有充分分开的两个概念：
**终答表示形状**与**获得终答所需的推理难度**。团队自建 `eval_112.json` 前 10 题全部被
路由为 `answer_type=scalar / complexity=short`，但它们包含深组合、函数方程、极值、参数表达式、
有限解集、范围和函数族。结果为 10/10 invalid；7 题返回非 `UNKNOWN`，其中 5 题以一次调用的
`candidate_unproven` 早停，Parser 还接受了未完成推导片段。该结果证明原有单轴路由、宽松
scalar fallback 与统一 early-stop 门组合不安全；它不证明 API 故障，也不能仅凭缺失的
finish reason/actual completion tokens 断言全部响应被 token 截断。

## Solution

建立外层 `Constraint-Fit Math Harness`，版本标识为 `MATH-HARNESS-V1`，首个能力候选命名为 `bounded_evidence_trajectory_selection_v1`。新 Harness 通过一个最高层的 `ReasoningAgent.solve()` seam 接入，不继续向 FSDF 内部堆阶段；FSDF 保留为可插拔的 legacy backend 和后续对照臂。

一次 solve 的默认控制流如下：

1. SubmissionGateway 先确定 bank 模式、题目隔离和输出契约。
2. Host Router 先产生双轴 `ProblemContract`：独立判断终答表示形状与推理风险，不访问答案或隐藏评测信息。
3. Attempt Scheduler 先发起一次普通自由格式解答，不要求 `CANDIDATE:` 首行或完整证明协议。
4. Host Parser 从响应中抽取候选答案，并把候选、理由摘要、检查结果和未决项写入本题 Evidence Ledger。
5. 只有 direct 单值题可在一个契约完整候选后早停；structured/deep 题必须继续取得独立一致、确定性检查或 Critic 裁决。若候选缺失、冲突或不可信，再发起一次相互独立的解答。
6. 两次结果冲突时才调用一次短 Critic；只有 Critic 明确指出可修复错误时才允许一次 Repair。
7. 若响应被截断但已包含唯一、可解析候选，最多允许一次短 Continuation/Finish；没有候选时禁止凭空补答。
8. Selector 采用保守的规范化、精确等价和有限数值检查；不能安全裁决时返回显式 `UNKNOWN` 语义的非空 `final_response`，而不是静默猜答。
9. Formatter 根据答案类型生成简洁、可 JSON 序列化且始终非空的 `final_response`；trace 只保留决策摘要，不保存完整 prompt 或敏感信息。

首个实验 profile 的硬预算为每题最多 5 次逻辑模型调用，建议的调用上限为 A=4096、B=4096、Critic=2048、Repair=4096、Continuation=2048 completion tokens，总上限 16384；所有值必须在对应 preregistration 中冻结，禁止运行中隐式重试或临时加预算。该 profile 只表示待验证的约束适配方案，不改变当前线上配置。

### 2026-09-10 针对性加强：双轴契约与 Deep lane

原始 `bounded_evidence_trajectory_selection_v1` 缩小为 **direct single-answer lane**，不再覆盖
所有被旧分类器称为 `calculation` 的题。新增候选
`typed_contract_adaptive_deep_v1`，仍位于同一个 Constraint-Fit Orchestrator 内，不建立第二套
总编排器。`ProblemContract` 只包含三个决定所需字段：

- `answer_shape`：`single_numeric / parameterized_expression / finite_set / interval_or_range /
  function_family / proof_text / unknown`；
- `reasoning_risk`：`direct / structured / deep`；
- `route_confidence`：有限枚举，低置信时保守回退而不是默认 scalar。

路由规则固定为：direct 的单数字或选择题进入原 bounded lane；structured/deep 的单值题进入
Deep lane；参数表达式、集合、范围与函数族进入 typed Deep lane；证明、推导、解释和低置信 mixed
题保留 FSDF 回退。输出很短不再等价于推理很短。

Deep lane 不复制 FSDF 的固定五阶段，只采用最多三次调用的状态驱动流程：第一次
`deep_primary` 产生完整自然解答；宿主按 typed contract 判断为“完整答案 / 有推导但结论未完成 /
无候选”；随后分别触发独立复核、一次 continuation 或独立第二解；仅在两个完整答案冲突时使用
一次 Critic。首个 formation profile 可预注册为 `8192 + 4096 + 4096 <= 16384`，但必须先用新鲜
冻结题验证端点能形成完整 typed answer，不能直接进入能力实验，也不能在原 10 题上调 Prompt 或预算。

## User Stories

1. As a solver maintainer, I want a new outer Harness seam, so that future improvements do not require adding another FSDF stage.
2. As a solver maintainer, I want FSDF retained as a legacy backend, so that every new route has a stable rollback and comparison anchor.
3. As a platform participant, I want the implementation to use only the public client chat contract, so that it remains valid in the official isolated runner.
4. As a platform participant, I want every solve to return a JSON-serializable dictionary with a non-empty `final_response`, so that interface failures cannot turn a mathematical answer into a zero-score submission.
5. As a platform participant, I want the Harness to tolerate thinking-on endpoints without relying on a visible marker protocol, so that CAR-002's failed `CANDIDATE` formation is not repeated.
6. As a solver maintainer, I want a first ordinary free-format attempt, so that the model can answer naturally under the endpoint's actual behavior.
7. As a solver maintainer, I want a second attempt only when the first result is missing, conflicting or untrusted, so that easy questions do not pay a fixed multi-call cost.
8. As a solver maintainer, I want independent attempts to be mutually blind, so that the second attempt measures independent evidence instead of copying the first answer.
9. As a solver maintainer, I want a critic called only on a genuine conflict, so that adjudication is reserved for cases where it can change a decision.
10. As a solver maintainer, I want repair restricted to an explicitly diagnosed error, so that the system does not enter an unbounded self-correction loop.
11. As a solver maintainer, I want truncation with an explicit candidate to be recoverable once, so that a useful answer is not discarded solely because its explanation ended at the token cap.
12. As a solver maintainer, I want truncation without a candidate to fail closed, so that the host never fabricates an answer from an incomplete proof.
13. As an evaluator, I want candidate formation, proof completion and verification represented as different states, so that a parsed answer is not reported as a proved answer.
14. As an evaluator, I want every candidate to record its source and extraction status, so that answer selection is auditable per question.
15. As an evaluator, I want conflict candidates retained together with their checks, so that the selector cannot silently discard one branch by order.
16. As a solver maintainer, I want deterministic equivalence checks reused at the host boundary, so that generic formatting differences are handled without unrestricted symbolic search.
17. As a solver maintainer, I want answer-type-aware extraction, so that integer, rational, exact-expression and proof-style outputs are not forced through one unsafe rule.
18. As a solver maintainer, I want a conservative selector, so that unresolved conflicts become explicit abstentions rather than confident wrong answers.
19. As an evaluator, I want a compact per-solve Evidence Ledger, so that trace explains the decision without leaking full prompts, private data or hidden answers.
20. As a platform participant, I want state discarded after each solve, so that question order, process reuse and prior answers cannot affect hidden evaluation.
21. As a platform participant, I want the offline error notebook frozen before evaluation, so that it can provide reviewed generic advice without becoming an online learning channel.
22. As a platform participant, I want `temporary_answer_bank` disabled in all capability, health and A/B runs, so that reported correct answers measure the solver rather than lookup.
23. As a release operator, I want `temporary_answer_bank` enabled in submission simulation and the online profile, so that the allowed submission behavior is tested exactly where it will be used.
24. As a release operator, I want bank hits and model-derived answers tagged separately, so that leaderboard behavior is not confused with capability evidence.
25. As an evaluator, I want bank overlap, hit and miss paths tested, so that the gateway cannot accidentally leak bank state into the model path.
26. As an evaluator, I want the official three-worker concurrency and per-question 20-minute limit preserved, so that local results remain operationally relevant.
27. As an evaluator, I want all logical calls and completion budgets recorded, so that a capability gain cannot be purchased by hidden retries.
28. As an evaluator, I want health gates evaluated before correctness gates, so that a window with client errors or protocol failure is marked VOID rather than over-interpreted.
29. As an experiment owner, I want a fresh endpoint preflight before a capability run, so that answer extraction is tested against the actual thinking-on endpoint.
30. As an experiment owner, I want mechanism A/B to change only evidence-ledger selection and early-stop behavior, so that any gain has a defensible attribution.
31. As an experiment owner, I want ability A/B to use fresh paired questions and rotated arm order, so that the comparison is not driven by question mix or run order.
32. As an experiment owner, I want two independent ability rounds before promotion, so that one lucky sample cannot change the default route.
33. As an evaluator, I want correct, incorrect, invalid, model error, timeout, calls, tokens and P95 wall-clock reported together, so that quality and cost are judged as one trade-off.
34. As a solver maintainer, I want scalar-answer questions routed to the new Harness only after its own gate, so that proof and derivation tasks remain on a known backend during early validation.
35. As a solver maintainer, I want uncertain or mixed task types to fall back conservatively, so that a weak classifier cannot silently change the official answer path.
36. As a release operator, I want a submission simulation after every promotion candidate, so that imports, constructor compatibility, output serialization and bank behavior are checked before release.
37. As a release operator, I want no automatic modification of `SUBMISSION_CONFIG`, main, GitCode or the official work, so that experiments remain reversible and explicitly authorized.
38. As a researcher, I want Kaggle/AIMO mechanisms documented as inspiration rather than proof, so that external leaderboard claims do not become unsupported local capability claims.
39. As a researcher, I want rejected CoD, Re2, PS-C, CAR-002 and FSDF reliability variants excluded from raw reruns, so that the new work tests a genuinely different mechanism.
40. As a maintainer, I want every experiment to leave a manifest, per-question records and a disposition, so that future decisions can be reproduced from artifacts.
41. As a solver maintainer, I want answer shape separated from reasoning risk, so that a short final value does not make a hard problem enter the short lane.
42. As a solver maintainer, I want parameterized expressions, finite sets, ranges and function families represented explicitly, so that the parser does not force them through a numeric scalar contract.
43. As a solver maintainer, I want low-confidence contracts to fall back conservatively, so that absence of proof keywords is not treated as evidence that a problem is easy.
44. As an evaluator, I want the seven non-UNKNOWN smoke outputs replayed as negative fixtures, so that incomplete derivation fragments cannot again become accepted answers.
45. As an evaluator, I want incomplete fragments classified separately from mathematically incorrect complete answers, so that invalid and incorrect remain meaningful metrics.
46. As a solver maintainer, I want unverified early-stop limited to direct single-answer problems, so that deep tasks cannot end after the first plausible expression.
47. As a solver maintainer, I want a bounded Deep lane inside the existing orchestrator, so that hard problems gain continuation or independent review without creating another fixed five-stage system.
48. As an experiment owner, I want typed-answer formation demonstrated before deep capability A/B, so that a larger budget is not spent on an endpoint that still cannot expose a complete answer.
49. As an experiment owner, I want zero typed-complete answers among the first three formation items to stop the probe, so that obvious endpoint incompatibility does not consume the whole window.
50. As a release operator, I want the original bounded lane and current FSDF submission route unchanged until the revised Deep lane independently passes its gates, so that this amendment remains reversible.

## Implementation Decisions

- **架构边界**：`ReasoningAgent.solve()` 是唯一主 seam。SubmissionGateway、ConstraintFitOrchestrator、Attempt Scheduler、Evidence Ledger、Selector 和 Formatter 通过这一边界协作；FSDF 只实现为 legacy backend，不在本规格内修改其 handoff、budget 或 finish 阶段。
- **路由契约**：Host Router 使用双轴 `ProblemContract`，分别输出 `answer_shape`、`reasoning_risk` 和 `route_confidence`。输出契约和推理难度不得互相代替；无 proof 关键词不等于 direct，旧 `calculation` 标签也不自动等于 scalar-short。proof、derivation、explanation 和低置信 mixed 题保留 FSDF 回退。路由结果必须进入 trace，不能读取题库答案或依赖题目顺序。
- **答案库隔离**：Gateway 接受显式 `bank_mode=off|on`。`off` 是 capability、health、mechanism A/B、ability A/B 的硬前置；`on` 只用于 submission simulation 和线上提交。bank lookup、命中、未命中、模型求解分别记录，bank 命中不计入 solver capability。
- **单题状态机**：状态至少包括 `start`、`attempt_a`、`candidate_a`、`attempt_b`、`conflict`、`critic`、`repair`、`continuation`、`selected`、`abstained` 和 `finalized`。每次转移都由宿主决定，模型不能增加状态或调用次数。
- **候选状态**：候选与完整证明分离。候选状态使用 `missing / parsed / truncated_with_candidate / conflict / rejected / verified` 等有限枚举；`verified` 只在确定性检查或独立证据满足门槛时出现，不能由“模型写得更长”推导。
- **调用调度**：direct lane 沿用 A/B/Critic/Repair/Continuation 的有界调度；Deep lane 只使用 `deep_primary`、按 typed completeness 触发的 independent-check 或 continuation，以及冲突时的 Critic，最多三次调用。两条 lane 均不得无界重试，总请求 token 不超过 16384。
- **token/时限账本**：每次调用前由 solve-local BudgetLedger 原子扣减 profile 中的 `max_tokens`，记录请求、实际 completion tokens、finish reason、耗时和剩余额度。单题 20 分钟、整轮 6 小时、runner 3 workers 是硬约束；超过任一限制立即进入可审计的 fail-closed 分支。
- **端点兼容**：只调用公开的 `client.chat(messages, temperature, max_tokens)` 形态，不假设能够关闭 thinking，不读取私有字段，不依赖 streaming、logprob、熵或线程安全。
- **抽取与 matcher**：优先复用现有答案抽取和 matcher seam，并按 `answer_shape` 选择完整性契约。`single_numeric` 只接受完整数值；`parameterized_expression` 必须保留题目要求的自由变量；`finite_set`、`interval_or_range` 和 `function_family` 必须形成完整结构。高风险题禁止使用“最后一条含数字/等号的文本”作为通用 fallback。允许的规范化只能处理任意同类表示；禁止绑定题号、题面或金标。解析失败必须区分无候选、未知、冲突、截断、结构不完整和类型不匹配。
- **等价与检查**：宿主只做已有安全规则、精确字符串/数值关系、有限代入和无序集合等通用检查。禁止在 selector 内引入无界 SymPy 搜索、任意代码、隐藏 judger 或答案反查。
- **Evidence Ledger**：每题仅保存候选值、answer type、来源 attempt、短理由摘要、确定性检查结果、冲突关系、开放问题、预算和阶段状态；不保存完整 prompt、完整模型输出、API key、token 或个人信息。
- **Typed micro-tools**：首版默认关闭，不允许模型生成任意 Python。若后续实验需要工具，只能增加宿主白名单的 typed provider，例如有限有理数运算、gcd、质因数分解或有限域检查；工具调用、输入上限、异常和结果必须写入 Evidence Ledger，并另立实验验证。
- **Selector 与 early-stop**：先做 typed completeness、候选有效性和确定性等价，再做证据等级排序。只有 direct single-answer lane 可以选择单个 `candidate_unproven`；structured/deep 题必须具备独立一致、确定性验证或 Critic 明确选择。冲突仍无法安全裁决时返回 `UNKNOWN`。Selector 不按分支顺序静默丢弃候选。
- **Formatter**：最终返回字段至少包含非空字符串 `final_response`，可附简洁 trace。scalar 题优先输出明确答案；proof 题保留必要推导。任何 fallback 都必须可序列化且不把占位符、半截公式或完整 prompt 当作终答。
- **FSDF adapter**：保留现有 FSDF v1 行为作为显式 backend；adapter 只负责统一输入、预算记录、输出归一化和 trace，不把新 Harness 的候选状态写入 FSDF handoff，也不复活已封存的 FSDF reliability 变体。
- **错误笔记本**：离线审核可从逐题工件提炼通用、可复核的错误模式；正式运行只读取评测开始前冻结的版本，运行期间不得写入、更新、跨题传播或按题目顺序改变提示。
- **配置与发布**：新 Harness、typed tools、router 和 notebook 注入均默认关闭。任何 canary 或 `SUBMISSION_CONFIG` 改动都需要独立实验通过、用户明确授权、干净环境验收和可回滚锚；本规格本身不授权部署。
- **修订后实验顺序**：原 FIT/CODE 与诊断工件保留，不覆盖。针对性加强按 `MATH-CONTRACT-ROUTER-CODE-001` → `MATH-TYPED-PARSER-CODE-001` → `MATH-DEEP-FORMATION-PROBE-001` → `MATH-DEEP-TRAJECTORY-SMOKE-001` → `MATH-DEEP-ABILITY-AB-001` → 既有 `MATH-HYBRID-ROUTER-001` → submission simulation 执行。每窗串行；先写报告、manifest 和处置，再启动下一窗。
- **formation 停止门**：Deep formation 使用与原 10 题不重叠的新鲜冻结深题，bank-off。预注册门为 0 model error、0 timeout、typed-complete 至少 5/6；若前三题 typed-complete 为 0，立即停止。门槛失败即 `NO_GO / NO_CAPABILITY_CONCLUSION`，不临场修改 Prompt、parser 或预算。
- **适配审计**：FIT-AUDIT 先建立官方接口、并发、时限、bank、题目隔离、依赖和 fail-closed 矩阵；不调用真实模型，不修改默认配置。
- **零模型代码门**：CODE-ACCEPTANCE 覆盖状态机、预算账本、互盲、解析/截断、selector、typed-tool 白名单、trace 卫生、bank off/on 隔离、官方构造函数和最小 solve 输出。
- **端点预检**：ENDPOINT-PREFLIGHT 只回答“普通自由格式响应能否稳定抽取”，不要求 `CANDIDATE:`、FSDF handoff 或完整证明 marker。题集、seed、模型配置和调用上限在运行前冻结；若端点不具备可用抽取条件，整条 Harness 路线停止，不临时调 prompt 追分。
- **健康门**：HEALTH 先检查 durable record、client/model error、阶段 timeout、finish reason、协议失败、非空输出和真实调用数。任一臂超过 preregistered void 门即整窗 `VOID / NO_CAPABILITY_CONCLUSION`，不得用正确题抵销健康失败。
- **机制 A/B**：MECHANISM-AB 只比较同一候选生成结构下“无 Evidence Ledger/早停选择”和“启用 Evidence Ledger/早停选择”，保持题集、提示词、预算和抽取器不变；目标是验证证据驱动调度是否改善调用、截断、有效答案或错误反转。
- **能力 A/B**：ABILITY-AB 仅在前置窗过门后，与 FSDF v1 做两轮 fresh、同题配对、轮换先后顺序的 scalar/exact-answer 比较。报告 correct、incorrect、invalid、error、paired b/c、调用数、completion tokens、平均/P95 wall-clock 和反向变化；不能把 valid 或截断下降单独当能力提升。
- **混合路由**：HYBRID-ROUTER 只有在新 Harness 独立通过能力门后才启动，比较 `scalar → Harness`、`proof → FSDF` 与全 FSDF。路由本身只增加一个可归因变量，不把多个旧开关叠加进同一窗口。
- **submission simulation**：bank-on，覆盖命中、未命中、模型成功、模型失败、非空 final_response、JSON 序列化、导入和构造兼容；bank 命中单独计数，不写入能力结论。
- **证据处置**：每个实验都必须有 protocol snapshot、dataset manifest、run manifest、逐题 answers、summary 和 result/disposition。任何历史转述数字、旧失败窗口或外部 leaderboard 只作背景，不进入晋升统计。

## Testing Decisions

- 测试最高边界是 `ReasoningAgent.solve(problem, metadata)` 的外部行为，使用 ScriptedClient/FakeClock/FakeToolProvider 构造可重复响应；不测试私有正则实现细节或 prompt 逐字内容。
- 代码验收必须覆盖：官方构造函数兼容、公开 client 调用形态、5 次调用硬上限、token 账本不超额、每题状态隔离、A/B 互盲、冲突保留、截断有候选的单次恢复、截断无候选的 fail-closed、空响应和异常响应、非空 `final_response` 及 JSON 序列化。
- Matcher 测试必须覆盖任意同类的整数、分数、精确表达式、无序集合、占位符、半截公式、括号不闭合、重复候选和类型不匹配；不得使用隐藏题或按题号特判。
- 双轴路由测试必须同时覆盖 direct 单值、deep 单值、参数表达式、有限集合、范围、函数族、证明文本和低置信 mixed；同一 answer shape 在不同 reasoning risk 下必须能得到不同 lane，简单题 parity 必须保留。
- Typed parser 测试必须把 `MATH-HARNESS-EVAL112-SMOKE-001` 中七个非 `UNKNOWN` 输出作为只读负例类别回放，断言推导句、未完成函数式和孤立变量不满足其题目契约；测试不得把金标传给 Router、Parser 或 Agent。
- Early-stop 测试必须证明 direct 单值题仍可一次结束，而 structured/deep 题的单个 parsed-but-unverified 候选不能结束 solve。
- Evidence Ledger 测试必须断言候选来源、检查结果、状态枚举和预算摘要可观察，但完整模型原文、敏感值和跨题状态不可见。
- Typed-tool 测试必须断言白名单、输入边界、确定性结果、超时和异常处理；首版没有任意 Python、Jupyter、shell 或网络工具路径。
- bank 测试分成两套：bank-off 断言不导入、不查找、不命中；bank-on 断言命中/未命中路径、来源标记和最终输出契约。任何 bank 命中都不得计入模型 capability 计数。
- FIT、CODE、PREFLIGHT、HEALTH、MECHANISM、ABILITY、HYBRID 和 submission simulation 都必须使用独立的 manifest 与冻结配置；同一窗口内不得修改 prompt、预算、题集或判定门。
- 健康门先于能力门。只要出现预注册规定的 client error、阶段 timeout、durable record 缺失、协议失败或输出契约失败，窗口就标记 VOID，并保留诊断数据供下一轮设计使用。
- 能力测试使用 fresh 题组、问题组隔离、固定 seed、同题配对、臂顺序轮换和至少两轮独立复验。统计以逐题分歧对和 paired sign test 为主，分母明确写为配对数。
- 运行前后执行干净环境导入检查、官方 client 初始化、最小 solve、`py_compile`/测试套件、`git diff --check` 和提交模拟；不以开发机隐式依赖替代隔离环境验收。
- 测试报告必须同时列出正确性、协议健康、调用/token 成本、平均/P95 wall-clock、错误反转和 bank 状态；任何“截断下降”“valid 上升”或“格式更整齐”都不能单独触发晋升。

## Out of Scope

- 不在本规格内继续修改 FSDF handoff、D/E budget、finish prompt、multiline marker 或其他已封存可靠性变量。
- 不原样重跑已处置的 CoD、Re2、PS-C、CAR-002/CAR-002B/C-03、FSDF D/E budget-swap 和 FSDF multiline-handoff 实验。
- 不复制 Kaggle 方案的 H100/vLLM/8 路固定并行、streaming、logprob/entropy voting、跨题全局时间状态或持久 Jupyter sandbox。
- 不接入任意 Python、shell、网络、MCP、未隔离的 Code Judge、训练/RL 或新的外部运行时依赖。
- 不读取、推断、构造隐藏题、标准答案、judger 内部信息或题目执行顺序。
- 不按公开题号、固定题面片段或单题金标特化 matcher、prompt、router 或 error notebook。
- 不把候选形成等同完整证明，不把 shadow verifier 或软 skill 合规率当作能力证据。
- 不在实验中自动修改 `SUBMISSION_CONFIG`、默认开关、AtomGit/GitCode/GitHub main、提交作品或发布指针。
- 不把 temporary_answer_bank 命中纳入本地真实解题能力、健康或 A/B 结论。
- 不以一次小样本、单轮 leaderboard、不可复核历史数字或外部方案排名直接宣称官方分数收益。
- 不在原 `eval_112.json` 前 10 题上继续调 Prompt、预算、Router 或 Parser 后反复报分；这些题只保留为路由与契约的回归夹具，不进入修订候选的能力证据。
- 不通过放宽 matcher 把未完成推导从 invalid 改记为 valid/incorrect，也不把 invalid 下降本身当作数学能力收益。

## Further Notes

- 这是一项架构替换候选，而不是“把更多 agent 接到 FSDF 里面”。推荐的最小可行落点是外层 Harness + FSDF adapter + 单题 Evidence Ledger；先验证 seam 和约束，再决定是否实现 typed tools 或混合路由。
- 公开高分方案最值得借鉴的是“有界搜索—证据—选择—资源调度”闭环，而不是硬件、并行规模或训练配方。研究笔记中的外部材料只作为设计输入，不是本仓库能力证据。
- 当前已确认的风险优先级是：端点 thinking-on 下的答案可见性与抽取、阶段/总时限、错误反转和 bank 误计数；不是继续增加协议字段或模型调用次数。
- 如果 ENDPOINT-PREFLIGHT 失败，停止 Harness 能力窗并保留 FSDF；如果 HEALTH 失败，只修复可观察的工程/协议阻断并重新编号，不进入能力 A/B；如果两轮 AB 未显示可归因的正确数收益或出现明显错误反转，保持 FSDF 线上路径。
- 任何默认路径晋升都需要：独立代码门、端点预检、健康门、至少两轮 fresh 能力 A/B、submission simulation、用户明确授权和可回滚发布锚。该 spec 本身不构成部署授权。
- `MATH-HARNESS-EVAL112-SMOKE-001` 的 `incorrect=0` 不能解释为“模型没有答错”：7 个非 `UNKNOWN` 输出因不满足答案契约被记为 invalid。当前主因是路由、typed completeness 与 early-stop 的组合缺陷；matcher 可能仍有覆盖缺口，但不是该窗口 0 correct 的主要解释。
- 本修订不是历史“长题统一加 token”的原样复跑。新假设是双轴契约先识别深题，再由 typed completeness 驱动有限 continuation/独立复核；较大首调用预算只有 formation probe 过门后才可进入 trajectory smoke。

## 用户授权的 112 题诊断例外（2026-09-10）

在端点预检 `MATH-HARNESS-ENDPOINT-PREFLIGHT-001/002` 失败后，用户明确授权新增一次
`MATH-HARNESS-112-DIAGNOSTIC-001` 完整诊断运行及其必要的 parser 校正窗口
`-002` 至 `-005`。该例外只允许对
`sample_data/public_regression_112.jsonl` 做 bank-off、多 worker 的工程/能力观测，必须
单独预注册、单独落盘，且永久标记为 `diagnostic-only / NO_CAPABILITY_CONCLUSION`；它不能
解除端点预检的 NO_GO，不能替代 HEALTH、机制 A/B 或两轮能力 A/B，也不能触发默认路径晋升。
官方接口、3-worker、单题 20 分钟、整轮 6 小时、单题最多 5 次逻辑调用和 16,384 请求 token
上限仍保持不变。该例外不允许读取隐藏题、向模型传递标准答案、启用
`temporary_answer_bank` 或修改 `SUBMISSION_CONFIG`。

若该诊断发现通用 parser/评分边界错误，允许在修复并增加回归测试后另立一个新的
`MATH-HARNESS-112-DIAGNOSTIC-002` 校正诊断窗口；校正窗口必须重新冻结配置和工件，不能
覆盖 `-001`，且仍然永久标记为 `diagnostic-only / NO_CAPABILITY_CONCLUSION`。

若校正窗口再次发现同一类通用 parser 边界错误，必须停止该窗口并重新编号；不得在运行
中修改 parser、评分器或提示词。

本次 `-003` 发现该类错误后，后续校正窗口必须统一对所有 scalar 候选入口执行同一套
受限 RHS/数学定界符规范化；不允许只修复某一个抽取路径。

`-004` 若发现孤立数学定界符，也必须停止并重新编号；修复后只允许继续一次最终校正，
并保留此前窗口的原始记录。
