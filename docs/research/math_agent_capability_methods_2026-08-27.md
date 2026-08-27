# 数学推理 Agent 能力提升候选研究（2026-08-27）

状态：**只读调研与实验设计**。本次没有运行模型评测、没有修改运行时代码，也没有把论文结果
当成本仓库收益。外部资料只采用论文原文、会议页面和作者官方代码；仓库事实以当前
[`AGENTS.md`](../../AGENTS.md)、[`CONTEXT.md`](../../CONTEXT.md)、
[`docs/excluded_approaches.md`](../excluded_approaches.md) 及已落盘实验报告为准。

## 结论先行

接下来的顺序不应是继续堆 token、投票或 rollout，而应是：

1. P1 `current_salvage` 首次回归因端点健康门触发 VOID；hetero 启动前 dev3 探针也为
   3/3 model_error。此后用户明确批准跳过本地 A/B,直接发布 hetero_k5 未验证 canary;
   官方结果前不得把发布动作表述为能力通过；
2. 若仍需新能力候选，优先测试 **Chain-of-Draft（CoD）** 和 **Re2**，因为它们不增加
   调用数，并直接针对官方 C0 的高截断与长输出风险；
3. 再依次测试 Generative Self-Aggregation（GSA）、PS+、Key-Condition Verification、
   Step-Back、Least-to-Most、Self-Discover；每次只开放一个新机制；
4. 单方法未独立过门前不融合。最先值得尝试的融合是“已过门的能力方法 + 已过门的
   CoD/Re2 成本或理解方法”，而不是两个未验证的复杂框架叠加。

这里的 P1 是“减少必为零分的 invalid”的输出卫生方案，不等于核心推理能力提升；
`hetero_k5` 才是当前唯一已经实现、预注册且未被旧证据否定的能力候选。

## 当前事实与硬边界

- 官方 C0（`b8b78aa`，answer-first + k5 + 4096）为 9/112、invalid 20、截断率
  88.7%、约 5 小时 12 分。过去在 k1/k5、B1、32k 之间切换没有突破正确数平台，见
  [官方评测记录](../experiments/官方评测记录.md)。
- `public_regression_112` 当前全被分类为 `calculation`，只能做计算题与输出卫生回归，
  不能证明证明题、解释题或长题能力。
- 32k、方法卡 RAG、PoT/TIR-first、模型生成程序回代、确定性求解器、SymPy 默认路径、
  P3/refine 原协议、exact_g/GR、普通 k3/k5 自洽扩采样均已 `REJECTED` 或 `ARCHIVED`；
  不得换名字原样复跑，也不得作为融合组件绕过否决。
- 官方接口只有 `client.chat(messages, temperature, max_tokens)`。候选不能依赖 logprobs、
  私有 client 字段、额外模型、隐藏答案、跨题状态或未声明服务。
- 官方并发 3、单题 20 分钟、整轮 6 小时。新方案的有效调用上限原则上不得超过 C0 的 5，
  且平均调用、P95、completion tokens、墙钟与 model error 必须同时报告。

## 统一实验闭环

### 1. 候选进入条件

外部论文只提供“值得测试”的先验，不提供本模型上的通过证据。每个新候选在进入模型窗前
必须先完成：

- 代码缝隙审计：确认不是 `excluded_approaches.md` 中旧机制的同义改写；
- 预算审计：列出最坏调用数、平均预期调用数、每次 max_tokens 与失败回退；
- 单变量测试：锁定除该方法外所有配置，测试开关默认关闭；
- 预注册：冻结 commit、Prompt/配置哈希、题集、轮数、void 门、能力门、卫生门、成本门；
- 工件：manifest、逐题 answers、汇总报告全部落盘后才允许判定。

若一个论文框架无法在公开 client 契约和最多 5 次调用内忠实表达，应停止，而不是实现一个
名称相同但机制不同的“缩写版”后借用论文结果背书。

### 2. 新能力候选的统一筛门

除 P1 和 `hetero_k5` 已有独立预注册外，排名 3–10 建议采用同一小筛骨架：

| 项 | 冻结建议 |
| --- | --- |
| 对照 | C0 `current`；若机制需要匹配调用结构，再加 matched control，但正式比较仍必须回到 C0 |
| 主集 | `sample_data/complex_capability_freeze_48.jsonl` 全量一轮 |
| 执行 | 双臂逐题交错，workers=3，timeout=90s，retry=1，temperature=0.6 |
| VOID | 任一臂 `model_error > 10%`，整窗作废，先于任何好看指标 |
| 能力 | 新能力候选须 `b>c`；只打平或净负即不继续追加样本 |
| 卫生 | candidate 的 `invalid + error` 不高于同窗 C0 |
| 成本 | 平均 calls ≤ C0×1.10，P95 calls ≤5；同时记录 token、截断与墙钟 |

CoD 是成本候选，例外门槛见其方法卡：允许正确率极小幅不确定波动，但必须取得足够大的
token/延迟下降，才能以“成本组件”身份独立过门。

### 3. 正式门与停止规则

小筛通过只解锁正式门，不产生晋升结论。建议正式门为：

- `complex48 ×2` 与 `medium_capability_freeze_60 ×2` 独立窗口；
- 每窗同题交错、同一协议快照；任一窗触发 VOID 时整窗不计；预注册最多允许一次健康复跑，
  再次 VOID 即归档为“无有效结论”，不能持续抽样；
- 每个数据集池化均不得净负，四窗合并须 `b>c` 且双侧精确配对符号检验 `p<0.05`；
- `invalid + error` 不增加，平均 calls ≤ C0×1.10，P95 ≤5，预计官方总墙钟不超过 C0；
- `public112` 只做计算与输出非回退检查，不计入“广泛能力提升”论证。

若方向为正但 `p≥0.05`，处置为 `ARCHIVED`，而不是继续加轮直到显著。若某方法只通过成本门，
则只能标为“成本组件 PASSED”，不得称为提分方法。

## 候选排序

| 排名 | 候选 | 当前状态 | 预期杠杆 | 最坏调用 | 优先级理由 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | P1 `current_salvage` | `OPEN / NO_VALID_CONCLUSION`；首次窗口 VOID | invalid→可判答案 | 不增加 | 首次证据已归档，不是能力失败，也不具备晋升资格 |
| 2 | `hetero_k5` | `DEPLOYED_UNVALIDATED_CANARY`；A/B 未完成 | 同预算解法多样性 | 5 | 用户批准直接发布；等待官方结果，不宣称提分 |
| 3 | Chain-of-Draft | 研究候选 | 缩短推理，降低截断/延迟 | 5 | 不加调用，直接命中 C0 的 88.7% 截断风险 |
| 4 | Re2（重读题目） | 研究候选 | 改善题意理解 | 5 | 只改输入提示，工程量和归因风险最低 |
| 5 | GSA | 研究候选 | 三候选信息的生成式聚合 | 4 | 固定 3+1 调用，区别于多数投票且适配公开 client |
| 6 | PS+ | 研究候选 | 计划、缺步与计算检查 | 5 | 单 Prompt 家族可隔离，但有增大输出长度风险 |
| 7 | Key-Condition Verification | 研究候选 | 用关键条件反向检查答案 | 5 | 比自由 self-refine 更可检验，适合数值/选择/填空 |
| 8 | Step-Back | 研究候选 | 先抽象原则再解题 | ≤5 | 对 STEM/长推导有先验，调用结构更复杂 |
| 9 | Least-to-Most | 研究候选 | 分解子问题、逐步求解 | ≤5 | 适合组合难题，但必须硬限子问题与调用数 |
| 10 | Self-Discover | 研究候选 | 动态组合推理结构 | 4 | 潜力高但实现和验证成本最大，最后测试 |

## 方法卡

### 1. P1 `current_salvage`：首次窗口 VOID，不扩大含义

现有 [P1 预注册](../experiments/p1_salvage_preregistration_2026-08-27.md) 要求先看任一臂错误率
是否超过 10%。首次 complex48 两轮已有三份 arm-report 超阈值，public112 未产出，因此按
[结果报告](../experiments/p1_salvage_result_2026-08-27.md) 记为 `ARCHIVED_VOID`，invalid 与正确率门
均未评估。它仍只是失败路径卫生候选；`invalid→incorrect` 不是提分，不能据本次 VOID 进入融合。

### 2. `hetero_k5`：固定预算的策略多样性

- **机制**：保留 C0 所有配置和有效上限 5，只把 5 路同类生成改成 4 Direct + 1 Alternative。
- **单变量**：只切换 `enable_heterogeneous_reasoners`；不改温度、token、投票阈值、输出协议。
- **现有门**：严格执行 [`hetero_k5` 预注册](../experiments/hetero_k5_screen_preregistration_2026-08-27.md)：
  正确率净失≤2、平均 calls≤C0×1.10 且 P95 不高于 C0、卫生不劣于 C0。
- **当前发布状态**：首次 dev3 健康探针 3/3 均出现 model_error，按
  [`hetero_k5_health_probe_result_2026-08-27.md`](../experiments/hetero_k5_health_probe_result_2026-08-27.md)
  判为 `UNHEALTHY`；没有运行 complex48，也没有能力结论。随后用户批准以 `18f4f5a`
  直接发布；该动作是风险接受,不是门槛通过。
- **解释边界**：DIVERSE 论文表明“多样化提示 + 验证”可提高多类推理任务表现，但论文使用的
  verifier 与本仓库不同；这里只支持测试“真正的策略多样性”，不支持重开普通 k5 自洽采样。

### 3. Chain-of-Draft：优先测试的成本组件

- **来源思路**：CoD 要求只保留极简但有信息量的中间草稿。论文报告其在若干推理任务上匹配或
  超过 CoT，并可把输出 token 降到 CoT 的 7.6%；这是论文环境结果，不是本模型承诺。
- **最小实现**：`current_cod_numeric` 只对 calculation/fill-blank/choice 的推理风格增加
  “每步只写必要草稿、避免解释性重复”，保留 answer-first、k5、4096、抽取、选择与回退；
  proof/derivation/explanation 完全沿用 C0，不引入新依赖。
- **忠实度边界**：作者 GSM8K 配置要求每个草稿步骤最多 5 个词、答案置于末尾 `####` 后，
  并使用 few-shot 示例。本仓库为维持 C0 单变量和高截断下的 answer-first，不复制“答案末置”
  与示例，只测试“每步极短草稿”这一机制；报告必须称 `CoD-style adaptation`，不能称论文复现。
- **来源适用边界**：作者仓库公开任务为 GSM8K、date、sports、coin-flip，没有证明/推导任务。
  因此首臂只覆盖结构化短答案族，不把“每步最多 5 词”外推到需要完整论证的输出。
- **单变量**：C0 vs `current_cod_numeric`，唯一差异是数值族 Prompt 片段及其哈希；非数值题
  必须有字段级/输出级 parity 测试。
- **小筛专用门**：paired 净失≤1；invalid+error 不增；平均 completion tokens≤C0 的 60%；
  P95 墙钟≤C0 的 70%；若只省不到 30% token，直接归档，避免把措辞变化包装成能力方法。
- **风险**：过短草稿仍可能删掉必要计算步骤；必须同时报告目标数值族和全局结果，不能只用
  public112 的成本数字支撑晋升，也不能表述为证明题能力提升。

### 4. Re2：最低工程成本的理解增强

- **来源思路**：Re2 在输入中让模型再次读取问题，而不是要求更长的输出推理；论文在 14 个
  reasoning 数据集上广泛测试，也明确存在 vanilla ChatGPT 的例外情况。
- **最小实现**：`current_re2` 在每次实际求解 Prompt 中原样重复题目一次，再接同一任务指令；
  不添加示例、不改输出协议、不改调用数。
- **实现锚**：作者代码把输入构造成
  `question + "\n\nRead the question again: " + question`（`read_times=2`）；首个候选应忠实使用
  这一变换，而不是再加入“仔细思考”等额外提示。
- **单变量**：C0 vs `current_re2`；唯一差异是“题目第二遍”输入变换。
- **门**：通用小筛门 + 输入 context 不溢出、model error 不增；正式门同时看 complex48 与
  medium60。若收益只来自 public112，按过拟合风险归档。
- **风险**：长题输入 token 近似翻倍；当前公开 client/runner 不提供 prompt-token 用量，因此
  必须记录可复核的输入字符数、最长题行为与 context 错误，不能读取私有字段伪造精确 token。

### 5. GSA：固定四调用的生成式聚合

- **来源思路**：Generative Self-Aggregation 不让模型判优或多数投票，而是把多个响应当作
  上下文，生成一个吸收其有效部分的新解答。论文主实验固定 4 次调用：3 个候选 + 1 次聚合。
- **最小实现**：`current_gsa` 固定生成 3 个候选，第 4 调用携带原题与三个候选作生成式汇总；
  聚合 Prompt 仍要求非空、可抽取的 `final_response`，不再追加校验或第 5 次调用。
- **单变量**：三臂设计：C0 作运营参照；compute-matched `k4_sc` 生成 4 个候选后按现有
  等价分组/投票；`k3_gsa` 把第 4 次候选调用替换为一次生成式聚合。机制判定比较后两臂，
  整臂还必须不劣于 C0。这与论文“固定 4 次模型调用”的主比较一致。
- **门**：compute-matched pair 与整臂均须 `b>c`；mean calls≤4、P95≤4；聚合后 invalid+error 不增；
  聚合输入不能因三个长响应触发 context 溢出。若必须丢弃绝大部分推理文本才能运行，就不再是
  论文中的 GSA，应在代码缝隙审计阶段停止。
- **风险**：C0 原始响应常接近 4096 token，三个完整响应可能使聚合上下文过长。CoD 若先独立
  通过，可在后续融合中缓解，但不能为了让 GSA 过门而在首个单方法窗同时加入 CoD。

### 6. PS+：计划后求解，补足缺步与计算检查

- **来源思路**：Plan-and-Solve 先拟计划再执行；PS+ 再加强变量、计算与中间结果检查。论文在
  GPT-3 的十个数据集上优于 Zero-shot-CoT，但并未覆盖本比赛模型和高截断分布。
- **最小实现**：只替换 C0 的任务 Prompt，要求先形成完整子任务计划、逐项执行并检查计算，
  同时维持现有 `final_response` 契约；不加入 few-shot 示例。
- **单变量**：C0 vs `current_ps_plus`，调用结构、温度、token、选择器完全一致。
- **门**：通用能力小筛门；额外要求 mean completion tokens≤C0×1.10、截断率不增。若正确率
  有信号但输出明显变长，不能晋升，应先归档并让 CoD 独立过门后再考虑融合。

### 7. Key-Condition Verification：约束化反向验证

- **来源思路**：ProCo 不是自由地问“你错了吗”，而是遮住题目中的关键条件，把当前解答作为
  上下文，让模型反推该条件，再决定是否修正。论文在 arithmetic 等任务上报告提升。
- **适用边界**：首版只针对能稳定识别单一关键数值/选项条件的 calculation、fill-blank、choice；
  证明、解释、多关键条件题一律不触发。
- **最小实现**：最多 3 路基础候选 + 1 次关键条件验证 + 验证失败时 1 次修正，总上限 5；
  验证输出必须符合闭合 schema，否则 fail-closed 保留原答案。
- **单变量设计**：三臂更清晰：C0 作运营参照，`k3_matched` 与 `k3_kcv` 用相同 3 路候选；
  机制判定只比较后两臂，唯一差异为 KCV；整臂最终还必须不劣于 C0。
- **门**：变化题中 `wrong→right > right→wrong`，全体 paired `b>c`；schema 解析失败不增加
  invalid；mean calls≤C0×1.10、P95≤5。

### 8. Step-Back：先找第一性原理

- **来源思路**：Step-Back 先从具体问题抽象出高层概念或第一性原理，再用它指导解题；论文在
  STEM、知识问答和多跳推理上报告收益。
- **最小实现**：第一调用只生成短原则/适用条件，第二调用携带原则求解；剩余预算不得使总调用
  超过 5。若无法稳定产生短原则，不退化为自由长篇“思考更多”。
- **单变量**：matched control 使用相同两调用结构和 token 配额，但第一调用只做普通题意摘要；
  challenger 只把该 Prompt 换成 step-back abstraction。机制通过后，整臂再对 C0。
- **门**：matched pair 和整臂对 C0 均须 `b>c`；原则调用 P95 输出长度受限；不得增加总截断、
  invalid 或 error。

### 9. Least-to-Most：有硬上限的子问题分解

- **来源思路**：Least-to-Most 把复杂问题拆成更简单的子问题，并让后续子问题利用先前答案；
  论文重点是 easy-to-hard 泛化。
- **最小实现**：调用 1 只输出最多 3 个有序子问题；调用 2 在同一响应中顺序完成全部子问题并
  给最终答案。禁止按子问题数循环调用，因此最多 2 次，不实现无界链。
- **单变量**：matched control 同样两调用、同 token；只把“直接计划”换成“至多 3 个可解
  子问题”。机制通过后再对 C0。
- **门**：全局 `b>c`，且 proof/derivation/explanation 子集不净负；分解解析成功率≥95%；
  mean calls、P95、completion tokens 均不过通用成本门。
- **风险**：这是对原论文的受限适配，不是严格复现；若两调用限制破坏方法关键机制，应停止。

### 10. Self-Discover：最后才测的结构发现

- **来源思路**：Self-Discover 让模型选择、适配并组合原子推理模块，形成任务内推理结构后再
  求解。论文在 MATH 等任务上报告相对 CoT 的明显收益，并报告比 CoT-SC 少 10–40 倍推理
  计算；这些数字不能外推到本端点。
- **最小实现审计**：必须确认论文的 select/adapt/implement/solve 四阶段能在最多 4 次调用、
  每次 4096 内表达；不能把四阶段压成一句普通 Prompt 后仍称 Self-Discover。
- **单变量**：matched control 使用同样四阶段与 token 配额，但采用固定通用结构；challenger
  只将结构来源改为 self-discovered。机制通过后整臂再对 C0。
- **门**：两个比较均 `b>c`；平均 calls≤C0、P95≤5；结构 schema 成功率≥95%；总体墙钟不
  高于 C0。任何一项失败即归档，不扩大框架。

## 融合路线（仅在单方法过门后）

论文中的“可组合”不等于仓库内可以直接叠加。融合对照必须是**已通过的最强单方法**，不是
回到较弱 C0；融合臂只新增一个组件。

| 融合阶段 | 前置条件 | 唯一新增变量 | 调用上限 | 建议 |
| --- | --- | --- | ---: | --- |
| F1 `winner + P1` | P1 与能力 winner 各自通过 | 只在 winner 的失败路径启用 salvage | 不变 | 最小风险；仍分别报告能力与 invalid |
| F2 `CoD + Re2` | CoD 成本门通过；Re2 能力门通过 | 在 Re2 上加入 CoD 风格 | 不变 | 输入理解与输出压缩相对正交 |
| F3 `hetero prompts + GSA` | hetero 与 GSA 各自通过 | 用异构 Prompt 产生 GSA 的三候选 | 4 | 三候选+一聚合，不能再叠加多数投票 |

融合正式门建议比单方法更严格：四窗合并 `b>c, p<0.05`，每个数据集不净负，
`invalid+error` 不增，mean/P95 calls、completion tokens 与预计官方墙钟均不高于最强单方法。
不满足即把**该融合组合**归档，不反向否定已过门的组件。

## 明确不推荐

以下方向本轮不进入候选池：

- `method_rag` 或任何“方法卡检索”换皮：本仓库已有双轮双负，永久排除；
- 32k、6144/8k 长题路由或再次提高 token：已有官方/本地负证据；
- 普通 k3/k5/k>5 self-consistency、调温度、多抽样碰答案：已不显著或成本失败；
- Tree-of-Thought、MCTS、多 Agent 辩论、无界 Progressive-Hint/rollout：无法守住 5 调用和
  6 小时总时限，也与禁止无界重试冲突；
- DIPPER 原协议：虽支持异构 Prompt 方向，但需要大 Prompt 池、开发集 fidelity、语义嵌入和
  并行 batch 优化；当前不单列候选，只在 `hetero_k5` 过门后作为新假设重新审计；
- Analogical Prompting：论文最佳通常需自生成 3–5 个示例，且明确增加输出 token；与当前
  4096/88.7% 截断冲突，除非 CoD 已有独立压缩证据，否则不启动；
- 训练式 GenRM/PRM：需要微调和更高验证计算；固定低预算研究还显示普通 solution sampling
  往往更算力高效，因此不适合当前公开 client；这不构成重开已归档普通 SC 的理由；
- PoT、PAL、TIR、模型生成程序后执行、回代程序：现有 PoT/TIR 与约束程序有效率均为 0/36；
- P3/refine、exact_g/GR 原协议复跑：已归档；协议修复和低成本观察都不等于能力通过；
- 自由 intrinsic self-correction（只问“检查并修正”）：ICLR 2024 论文和本仓库 P3 证据都
  提醒它可能把正确答案改错；若做验证只能采用 KCV 这类可判、fail-closed 的新假设；
- 针对 public112 的题号、题面、答案或学科标签优化 Prompt；
- 需要训练 reward model/PRM、微调模型、额外模型或 Lean 服务的方案：不符合当前公开 client
  与部署面，除非赛事环境和依赖约束发生可审计变化后另立研究。

## 坏方法归档与“不再做”协议

每个实验结束后、启动下一个方法前，必须更新 `docs/excluded_approaches.md`。建议每条至少写：

- `method_id`、机制指纹与适用题型；
- commit、Prompt/配置哈希、数据集、轮数、窗口时间；
- VOID 判定、b/c/p、correct/invalid/error、mean/P95 calls、tokens、墙钟；
- `REJECTED` / `ARCHIVED` / `SUPERSEDED` / `PASSED`；
- 失败原因、允许重启的必要变化、明确禁止的同义变体；
- manifest、逐题 answers、报告路径。

规则是：`REJECTED` 不原样重跑；`ARCHIVED` 不靠追加相同窗口“抽到显著”；VOID 只按预注册
允许的有限健康复跑；新论文若只是给旧方法换名，仍受旧处置约束。只有机制、适用条件或证据
前提发生可审计变化，才能用新 `method_id` 和新预注册重启。

## 一手来源表

| 来源 | 论文/代码的一手结论 | 本文用途与限制 |
| --- | --- | --- |
| [Chain of Draft（arXiv）](https://arxiv.org/abs/2502.18600) / [作者代码](https://github.com/sileix/chain-of-draft) | 极简中间草稿可显著减少 token，论文报告最低为 CoT 的 7.6% | 支持优先测试 CoD；不证明本模型正确率不降 |
| [Re-Reading Improves Reasoning（EMNLP 2024/arXiv）](https://arxiv.org/abs/2309.06275) | 重复输入问题，在 14 个 reasoning 数据集上广泛评估；存在模型例外 | 支持低成本 Re2 单变量；必须测长题输入风险 |
| [Plan-and-Solve Prompting（ACL 2023/arXiv）](https://arxiv.org/abs/2305.04091) | 先计划再执行；PS+ 加强计算和中间步骤检查 | 支持 PS+ 候选；论文模型与本端点不同 |
| [Key Condition Verification / ProCo（EMNLP 2024）](https://aclanthology.org/2024.emnlp-main.714/) | 遮蔽关键条件并由当前解答反推，论文在 arithmetic 等任务报告自纠收益 | 支持约束化 verifier；不支持自由 self-refine |
| [Take a Step Back（ICLR 2024/arXiv）](https://arxiv.org/abs/2310.06117) | 先抽象高层概念/第一性原理，再指导具体推理 | 支持 Step-Back；需要 matched call-structure control |
| [Least-to-Most Prompting（ICLR 2023/arXiv）](https://arxiv.org/abs/2205.10625) | 把复杂问题拆成简单子问题并顺序求解，强调 easy-to-hard 泛化 | 支持有界分解；两调用版只是受限适配 |
| [Self-Discover（arXiv）](https://arxiv.org/abs/2402.03620) | 选择并组合推理模块形成结构；论文报告 MATH 等收益和较低推理计算 | 支持末位候选；必须保持原四阶段而非名称挪用 |
| [Generative Self-Aggregation（arXiv）](https://arxiv.org/abs/2503.04104) | 主实验固定 4 调用，以 3 个响应为上下文生成新答案而非判优 | 支持 GSA；作者仓库当前只有代码待发布占位，长候选的 context 风险必须先审计 |
| [DIVERSE / Step-Aware Verifier（ACL 2023/arXiv）](https://arxiv.org/abs/2206.02336) | 多样 Prompt、加权选择、逐步 verifier 在多类 reasoning benchmark 上有效 | 只支持测试策略多样性；本仓库无同款训练 verifier |
| [DIPPER（EMNLP 2025）](https://aclanthology.org/2025.emnlp-main.1801/) | 用 Prompt 池、fidelity 与语义多样性选择构建同模型 ensemble | 只支持 hetero 方向；当前不复刻其 200 Prompt 优化流程 |
| [When To Solve, When To Verify（COLM 2025/arXiv）](https://arxiv.org/abs/2504.01005) | 固定低推理预算下 SC 通常比 GenRM 更算力高效，GenRM 需更多验证计算 | 支持不引入训练式 verifier；不授权重开 SC |
| [Analogical Reasoning（ICLR 2024/arXiv）](https://arxiv.org/abs/2310.01714) | 单 Prompt 自生成示例；论文发现 3–5 个示例较佳且承认输出 token 增加 | 支持当前暂缓，待先有压缩证据 |
| [Scaling Test-Time Compute Optimally（ICLR 2025）](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b623663fd9b874366f3ce019fdfdd44-Abstract-Conference.html) | 测试时策略效力随题目难度变化；论文报告比统一 best-of-N 更高效率 | 只用于过门后的路由融合设计，不授权加 rollout |
| [Large Language Models Cannot Self-Correct Reasoning Yet（ICLR 2024）](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8b4add8b0aa8749d80a34ca5d941c355-Abstract-Conference.html) | 无外部反馈的 intrinsic self-correction 可能不升反降 | 支持排除自由修正循环和坚持 fail-closed |
| [A Closer Look at Self-Verification（NAACL 2024）](https://aclanthology.org/2024.naacl-long.52/) | 多种模型仍可能难以可靠识别逻辑谬误 | 支持 verifier 卫生门，防止把自评当事实 |

## 推荐执行队列

```text
P1 首次窗口 VOID 归档
  -> hetero_k5 用户批准直接发布(未验证;等待官方结果)
  -> CoD
  -> Re2
  -> GSA
  -> PS+
  -> Key-Condition Verification
  -> Step-Back
  -> Least-to-Most
  -> Self-Discover
  -> 仅从 PASSED 组件中选择一个融合增量
```

每个箭头都表示：上一方法已完成报告、manifest、逐题 answers 和排除注册表处置；不是要求
所有方法必跑到底。某候选一旦失败就归档并移到下一个，避免围绕一个无信号方法反复抽样。
