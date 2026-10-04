# 基于“评测方法调研采纳报告”的 ARM 全架构重设计

日期：2026-10-03  
范围：Challenge-Cup-2026、Intern-S2、ARM v2.1.x、GRH v1.1/v1.2/v1.3、frozen-221   
状态：架构审阅与实验设计；不修改生产代码，不改变 `SUBMISSION_CONFIG`，不构成官方提交授权。

## 1. 审阅结论

这次不应该把 ARM 替换成另一个名字或另一个大而全的 Agent。更合理的做法是保留 ARM 作为**控制平面**，重新划分它与 solver、验证器、答案表示层之间的责任边界。

建议把下一版称为 **ARM-ARH / Decision-Aware ARM**（暂定名）：

```text
ARM：路由、预算、升级、候选生命周期和状态机
Solver：理解题目、选择路线、推导、产生候选
ARH：抽取、规范化、完整性检查、最终序列化
Verifier：只执行有边界的确定性检查
Decision：根据候选和证据选择、保留或 abstain
Evaluator：统一判分、逐题配对和损伤统计
```

这不是把 ARM 换成 GRH、FSDF、GSA 或另一个 Council。它是把 ARM 从“同时求解、评价、修复、裁决、格式化”的混合实现改成一个可审计的编排控制器。原有 ARM 的 per-request thinking mode、bounded budget、safe incumbent、candidate ledger 和 A/B 诊断能力保留；结构检查、数学验证和提交格式必须独立出来。

当前最重要的架构原则不是“让 ON 运行更久”，而是让每个阶段只承担一个可验收职责：

1. 模型负责产生数学候选，不负责保证比赛格式。
2. 候选是否完整，与候选是否有数学证据，必须是两个字段和两个状态。
3. 可以执行的局部验证优先于另一个 LLM 的泛化评价。
4. 第二候选必须带来路线或检查增量，不能只是更长的同质自由推理。
5. `UNKNOWN` 是合法状态，不能为了降低 invalid 把它强行改成 PASS。
6. 最终答案必须由 host-side contract 生成；模型没有写出 `\\boxed{}` 不能单独造成失分。
7. 每一个“invalid 下降”都必须同时报告 `invalid→correct`、`invalid→incorrect`、`correct→incorrect` 和 `correct→invalid`。

## 2. 证据边界

### 2.1 已确认事实

以下结论直接来自仓库文档、源码或已归档实验：

- [`evaluation_adoption_提分行动_2026-08-29.md`](../evaluation_adoption_提分行动_2026-08-29.md) 对 9 个判分实现做了源码级核对，指出 `\\boxed{}`、最简规范形、明确答案句式和无解释性尾缀是多种判分口径的共同安全区。
- 该报告明确建议 ARH 作为纯后处理：数值题同时输出“最终答案：canonical”和 boxed 形态；不新增模型调用，不修改 solver prompt。
- 该报告建议并行接入 Math-Verify 做本地诊断差集，但不把 Math-Verify 变成本地默认判分器，也不根据未知官方判分器进行投机对齐。
- 该报告不采纳本地 LLM-as-judge、PRM 运行时组件、强 JSON/XML 默认输出和异常回复剔除分母。
- [`arm_harness_v1.md`](../architecture/arm_harness_v1.md) 已经支持按请求选择 `on`、`off`、`inherit`，并把 route、mode、budget 和 escalation reason 写进 trace。
- [`arm_v2.1.3_technical_spec.md`](../9.29/v2.1.3/arm_v2.1.3_technical_spec.md) 已把 ARM 的主要问题定义为“完整候选不等于数学可信”，并要求 forced A/B、positive-evidence gate、bounded second sample 和不创造第三候选的 resolver。
- [`arm_v2.1.3_acceptance_spec.md`](../9.29/v2.1.3/arm_v2.1.3_acceptance_spec.md) 要求 correctness 优先于 formation，要求报告 A/B/Oracle、`A wrong → B correct`、`A correct → B wrong`，并规定两轮重复和调用上限。
- [`0003-thinking-on-adaptive-candidate-first-harness.md`](../adr/0003-thinking-on-adaptive-candidate-first-harness.md) 已否决固定多阶段长协议和无条件多路完整求解，选择 bounded candidate-first relay。
- [`excluded_approaches.md`](../excluded_approaches.md) 明确禁止跨时间窗口归因、VOID 后挑选好看指标、未独立过门就融合多个候选、用 invalid 下降替代 correct 提升和无界 rollout。
- `reasoning_agent/arm_v21_verification.py` 的默认 `DeterministicVerifier` 仍是 `NOT_APPLICABLE` 占位；因此 ARM 当前 trace 中出现的“verification”不能被写成数学正确性证据。
- `reasoning_agent/safe_candidate.py` 的 safe candidate 只表示中断时可保留的 incumbent，不表示候选已经被证明正确。
- `reasoning_agent/fesf_verifiers/adapters.py` 的安全范式是 `EXACT / REFUTED / UNKNOWN`，有限搜索没有找到反例时也不会把结果升级为全称 PASS。

### 2.2 数据支持的判断

- 当前 frozen-221 的 invalid 审计显示，很多 invalid 同时具有截断、候选记录或无效第二样本等信号。以已完成的两次 ON 运行遥测为例：221 题 invalid 中有 69 条出现 `finish_reason=length`，70 条有两个候选记录，86 条第二样本没有产生可用新值，且 invalid 的 verification 全为 `NOT_APPLICABLE`。这些集合重叠，不能直接相加成互斥类别，但足以说明“候选闭合、有效验证和收束决策”比单纯增加 token 更接近当前瓶颈。
- GRH v1.2 的 proxy-221 事后审计显示，跨窗口的 correct 回退不能归因于单一 ARM 机制；首候选波动、boxed 原值与 normalized value 的边界、错误替换和 Resolver 全部 UNKNOWN 同时存在。因此不能以一次回退宣布 ARM 已被证伪，也不能把一次局部回放当成数学提升。
- ARM-ISOLATION-001 重跑显示高 token 上限本身就会造成明显读超时，裸 endpoint 也会超时；不能把这类健康问题单独归咎于 ARM 状态机。

### 2.3 尚未验证的假设

- ON solver 是否在 Intern-S2 上稳定产生比 OFF 更正确的困难题候选。
- 第二条“不同路线”的候选是否能在当前 endpoint 上增加 `A wrong → B correct`，而不是只增加冲突和成本。
- 一次 OFF finalizer 是否能减少协议 invalid，同时不改动 canonical value。
- 受限 substitution、symbolic、finite-domain 或 constraint check 在本赛事题型上的覆盖率和误拒率。
- adaptive router 是否比固定 OFF 或固定 ON 在同一 endpoint 时段内有稳定的 paired 净收益。

以上问题只能通过新的、同题交错、同 evaluator 的预注册实验回答，不能从 README、自报分数或历史不同窗口分数推断。

## 3. “评测方法调研采纳报告”对架构的直接约束

### 3.1 ARH 是提交层，不是 solver

原报告的 ARH 规格应直接成为 ARM 的最后一层：

```text
Candidate object
    ↓ canonicalizer
TaskContract serializer
    ↓
最终答案：<canonical>
\\boxed{<canonical>}
```

这个出口只在 candidate 已经通过题型和完整性门时执行。它可以修复 LaTeX 包装、单位表面形态、选项标签和答案 marker，不能从半截推理中猜一个值，也不能改变 candidate 的数学值。

非数值题、证明题、多问结构题不应强行套单一 boxed 规则；它们仍然需要各自的 `TaskContract` 和完整性判定。

### 3.2 双判分器只用于差集诊断

默认 evaluator 保持项目冻结的 native 口径；Math-Verify 或其他实现只在本地离线重判中报告差集：

```text
native verdict
Math-Verify verdict
surface / normalization difference
```

差集用于测量“语义可能存在但表示不兼容”的上限，不允许用更宽松的判分器美化能力结果，也不允许据此反推官方 checker 的非对称细节。

### 3.3 不使用强结构化输出作为默认解法

当前 `InternChatClient.chat()` 的公开 payload 没有确认支持 `response_format`、JSON Schema、grammar 或 tool choice。vLLM、Outlines、Guidance、Instructor、PydanticAI 的结构化输出经验可以用于研究，但必须先做 capability probe；在此之前，默认采用 host-side typed parser、canonicalizer 和 serializer。

这不是拒绝结构化对象，而是把结构化边界放在 host。模型可以被提示输出 `FINAL_CANDIDATE` 和 `EVIDENCE`，但 marker 命中不等于数学证明，host 仍必须重新检查。

### 3.4 不把 LLM judge/PRM 作为默认验证层

数学判分、过程奖励和自然语言评价有不同用途。默认路径不添加 LLM-as-judge 或 PRM；如果后续实验需要 resolver，它只能在 deterministic check 返回 UNKNOWN、已有闭合 candidate 且预算满足时运行一次，并只能返回：

```text
PASS / FAIL / UNKNOWN + 固定长度 objection
```

它不能创建 candidate C、重写 canonical value、根据题目重新完整求解或覆盖已经有强证据的 incumbent。

### 3.5 统计纪律属于架构的一部分

每个候选版本都必须固定：dataset manifest、题序、model/version、endpoint、evaluator、canonicalizer、runner、预算和源码 hash。报告同时列 point estimate 和 Wilson 95% 区间；小规模 30 题和 112 题实验不应把 ±1–3 题波动写成确定性能力结论。

## 4. 新架构：Decision-Aware ARM + ARH

### 4.1 总体数据流

```text
                       ┌──────────────────────────────┐
                       │ Task Contract / Risk Profile │
                       │ type, fields, domain, budget │
                       └──────────────┬───────────────┘
                                      │
Problem ──> ARM Router / Compute Policy
                  │
          ┌───────┴────────┐
          │                │
      Easy/direct       Hard/uncertain
      OFF Solver        ON Solver
          │                │
          └───────┬────────┘
                  ▼
        Candidate Event + raw-span hash
                  ▼
       ARH extractor / canonicalizer
                  ▼
     completeness + contract validation
                  ▼
      deterministic verification gates
          │          │          │
        PASS       FAIL       UNKNOWN
          │          │          │
       select      reject   bounded escalation
          │                     │
          │       ┌─────────────┴─────────────┐
          │       │                           │
          │   independent route B         abstain/incumbent
          │       │                           │
          │       └─────────────┬─────────────┘
          │                     ▼
          │        pair comparison / local checks
          │                     │
          └─────────────────────┴──────────────┐
                                                ▼
                         DecisionRecord: SELECT / REPAIR / ABSTAIN
                                                ▼
                         host serializer or one OFF finalizer
                                                ▼
                         strict final response + compact trace
```

### 4.2 ARM 控制平面

ARM 继续负责：

- 读取不含 gold 的 `TaskContract` 和风险配置；
- 选择初始 OFF/ON 模式与 solver backend；
- 维护每题的 logical call、token、wall-clock 和 endpoint health ledger；
- 判断何时需要第二路线、局部验证、协议修复或 abstain；
- 保存 Primary、Challenger、safe incumbent 和每次版本迁移；
- 禁止弱候选覆盖已有强证据候选；
- 在全局预算内终止，不启动无限 ON→ON→ON。

ARM 不再负责：

- 直接把“结构完整”标成数学可信；
- 依赖模型自报 `CHECK`、`VERIFIED` 或 confidence；
- 用 Resolver 从两个错误值中创造第三个值；
- 在 serializer 中猜测缺失答案；
- 把 parser 成功、invalid 下降或 avg calls 下降写成 correct 提升。

### 4.3 Solver 平面

Solver backend 采用已有接口，不把所有题强塞给一个 generic prompt。第一阶段只保留三种可审计 lane：

| Lane | 适用条件 | 思考模式 | 责任 |
|---|---|---:|---|
| `direct` | 低风险、单值/选择、题型契约明确 | OFF 优先 | 快速形成闭合候选 |
| `structured` | 多步代数、约束、组合、需要中间关系 | ON | 推导路线和候选 |
| `deep` | 高风险或首候选无法闭合 | ON | 受限深度推理；仍需候选 checkpoint |

ON solver 的 prompt 可以要求通用边界事件：

```text
CLAIM: <当前候选或 UNKNOWN>
EVIDENCE: <一条可检查的局部依据>
FINAL_CANDIDATE: <闭合候选；没有则 UNKNOWN>
STOP_REASON: <closed|conflict|insufficient|truncated>
```

这些字段只用于遥测和抽取，不构成 verifier。候选内容与 route tag 分开记录，便于统计“路线多样性”而不是把措辞变化当作独立样本。

### 4.4 ARH：Answer Representation and Hygiene

ARH 由四个小模块组成：

1. **Extraction**：按固定优先级读取 typed answer block、明确 final marker、平衡 boxed、题型 parser、standalone value、末行 fallback。
2. **Canonicalization**：只做 Unicode/LaTeX 表面归一化、有理数约分、允许的集合排序和单位表面统一，不改多问顺序、定义域或数学值。
3. **Completeness**：区分 closed、partial、conflict、unknown；检查多问、单位、集合、向量、矩阵和 proof contract。
4. **Serialization**：只接受已选中的 candidate，按 contract 生成比赛格式；若仅 marker 或包装缺失且 canonical value 已确认，才允许一次 finalizer。

建议 Candidate 至少包含：

```json
{
  "candidate_id": "c-01",
  "value": "raw value",
  "canonical_value": "normalized value",
  "answer_type": "integer|rational|expression|set|choice|proof|unknown",
  "source": "explicit_marker|boxed|terminal_line|checkpoint|fallback",
  "completeness": "closed|partial|conflict|unknown",
  "reasoning_status": "established|tentative|truncated|unknown",
  "verification": [],
  "confidence": "deterministic|symbolic|enumerated|nl|unverified",
  "raw_span_hash": "sha256:...",
  "serialization_status": "ready|repairable|rejected"
}
```

`confidence` 是 host 证据等级，不是模型自报置信度。`raw_span_hash` 用于离线追溯，不要求把完整长思维写入正式 trace。

### 4.5 Verification Gate：三态且有边界

统一接口：

```text
PASS    在明确假设和输入上成立
FAIL    找到明确反例、代入不成立或结构冲突
UNKNOWN 超出安全范围、缺少条件或软超时
```

验证优先级：

1. 结构和完整性；
2. 整数、有理数、有限算术和候选代入；
3. 受限 AST/SymPy 等价，明确处理定义域；
4. contract 允许时的有限域枚举；
5. 模约束、边界、单位、维度和必要条件；
6. 只检查能形式化的局部证明义务。

“有限样本没有找到反例”返回 UNKNOWN；“模型说 CHECK: PASS”不是 host evidence。默认不使用 LLM judge 代替这些检查。

### 4.6 Decision Layer：候选优先级和状态机

推荐状态机：

```text
MISSING → PARSED → CLOSED
                    ├─ VERIFIED
                    ├─ REJECTED
                    └─ UNKNOWN
                         ↓
                 SELECTED / REPAIR / ABSTAIN
                         ↓
                    SERIALIZED
```

冲突候选必须进入 `CONFLICT`，不能用最后出现的文本覆盖早先候选。DecisionRecord 至少记录：

```json
{
  "candidate_ids": ["c-01", "c-02"],
  "checks": ["substitution:PASS", "domain:UNKNOWN"],
  "selected_id": null,
  "decision": "select|repair|abstain",
  "reason": "...",
  "abstain_reason": "conflict|incomplete|unsupported|budget"
}
```

ARM 的 trust gate 从“我是否敢相信这个完整字符串”改成“这个 candidate 当前拥有哪种证据、还缺哪种证据”。

### 4.7 有界 escalation

建议沿用当前 ARM 的单题最多 3 个 logical slots，但第三槽互斥：

1. **Primary**：一次 direct/structured/deep solver。
2. **Second**：只有候选缺失、完整性不足、冲突、截断或无正证据时，调用独立路线 B；B 不能读取 A 的 raw response 或 candidate value。
3. **Third**：只选择一种动作：
   - 已有闭合 candidate 且只差格式：一次 OFF finalizer；
   - 候选冲突且 deterministic 为 UNKNOWN：一个有限 resolver 实验臂；
   - 没有任何候选：不调用 finalizer，不启动第四次长求解，返回 UNKNOWN/既定 incumbent。

deterministic verifier 不消耗模型调用。若 endpoint 不支持 request-local OFF，则直接使用 host serializer，不能为了模拟 OFF 增加一轮长推理。第三槽的 resolver 和 finalizer 不得同时开启。

### 4.8 路线多样性，而不是表述多样性

Second sample 的路由 tag 至少区分：

- `algebraic_derivation`；
- `constraint_elimination`；
- `invariant_or_counting`；
- `constructive_or_counterexample`；
- `finite_check_or_enumeration`；
- `direct_recompute`。

实际可用的 route 必须由题型契约、solver 输出的中间关系和通用风险分类产生，不得按题号、gold、answer bank 或 benchmark lookup 特判。若 A 已使用某路线，B 应优先选择不同的通用方法族；若没有足够信息确定路线，使用互盲 fresh candidate，并将“路线未知”写入 trace，而不是假装多样。

路线多样性本身不等于正确性。只有 `A wrong → B correct` 在同一 evaluator 下出现，并且 B 没有造成过量 `A correct → B wrong`，才说明这条 escalation 值得继续。

## 5. ARM 旧组件到新组件的映射

| ARM 旧职责/组件 | 新定位 | 处理方式 |
|---|---|---|
| ARM Router | 控制平面 Router | 保留；只负责风险、题型和预算，不负责猜答案 |
| `thinking_mode` switching | Compute Policy | 保留 per-request ON/OFF；不把 ON/OFF 当数学能力证明 |
| Primary candidate | Candidate ledger | 保留原始版本和 canonical 版本，禁止就地覆盖 |
| Safe Candidate | Safe incumbent | 保留；只表示可追溯的中断候选，不表示 verified |
| CandidateTrust | Evidence policy | 保留但改为证据分层；完整性不能单独升级 high trust |
| `DeterministicVerifier` | Verification adapters | 保留接口，替换 `NOT_APPLICABLE` 默认路径前必须逐 check 过门 |
| Candidate B | Independent route challenger | 保留；必须盲于 A 且记录 route diversity |
| Resolver | Bounded decision aid | 默认关闭/实验；只能 A/B/UNKNOWN，不能造 C 或重解整题 |
| Recovery | Typed recovery | 只修复可定位的局部/协议问题；没有 candidate 不进入 finalizer |
| Final response assembly | ARH Serializer | 从 ARM 中拆出；以 TaskContract 生成 canonical + boxed 形态 |
| `arm_v21_summary` | Evidence Ledger + DecisionRecord | 扩充字段，区分 candidate、verification、serialization 和 evaluator verdict |

因此，ARM 不是被替换，而是由“求解器中心的混合 harness”变成“证据驱动的编排层”。现有 ARM 文件可继续作为兼容 facade；新逻辑应放进小模块，避免继续扩大单一总控文件。

## 6. invalid → correct 的切入顺序

### 6.1 分类

采用 R/S 双轴，避免把不同问题混成“invalid”：

| 类别 | 现象 | 首选动作 | 是否允许强救援 |
|---|---|---|---|
| R4/S1 parser-contract | 已有语义候选，但 boxed、单位、集合、多问等未抽取 | host parser + canonicalizer + contract | 允许，优先级最高 |
| R3/S2 finalization-truncation | `finish_reason=length`，但已有闭合候选或 checkpoint | safe incumbent + serializer | 允许；不得改值 |
| R2/S3 decision | A/B 候选存在，选择错误或无理由 abstain | deterministic comparison，再考虑有限 resolver | 有条件 |
| R3/S4 protocol-only | canonical value 已确认，仅缺 marker/字段 | 一次 OFF finalizer 或纯 host serializer | 允许一次 |
| R6/S5 health | timeout/API error，但已有强 incumbent | 保留 incumbent，禁止完整重跑 | 有条件 |
| R1/S6 reasoning | 没有可复核候选或推导本身错误 | 保持 UNKNOWN/invalid | 禁止强救援 |
| R5 evaluator-boundary | 等价规则、题型边界或 judge 有争议 | 冻结原答，离线重审 | 禁止用 prompt 改判 |

优先级应是 S1 → S2 → S4 → S3 → S5；S6 不通过“更多 token”伪装成可救援。只有同一 evaluator 重判为 correct，才计入 Invalid Rescue：

```text
Invalid Rescue = invalid → correct
Invalid Damage = invalid → incorrect
Correct Damage = correct → incorrect + correct → invalid
Net Correct Gain = new correct - lost correct
```

### 6.2 预期收益边界

host parser/replay 可以测量原始 response 中已经存在的可判答案上限，但不能证明模型数学能力增加。safe incumbent 可以减少后续空结果覆盖，但不能把截断片段升级为 verified。finalizer 可以改善协议卫生，但如果它改变 canonical value，立即视为失败并关闭。

## 7. 实验与验收设计

### 7.1 单变量顺序

| 实验 | 唯一变化 | 模型调用 | 目的 |
|---|---|---:|---|
| E0 | 冻结现有 ARM baseline | 原配置 | 保存逐题 verdict、health、候选和 finish reason |
| E1 | 纯 host ARH replay | 0 | 测量 parser/canonicalizer 的真实救援上限 |
| E2 | ARM ledger + safe incumbent + positive evidence | 与 baseline 相同 | 防止结构和候选迁移损伤 |
| E3 | E2 + independent route B | +条件 1 | 测量路线多样性是否产生 A/B rescue |
| E4 | E3 + deterministic gates | +0 | 测量局部验证的 rescue/damage |
| E5 | E4 + 一次 OFF finalizer | +条件 1 | 只测格式修复，不测重新求解 |
| E6 | E5 + adaptive OFF/ON router | +条件 0–1 | 最后评估 compute allocation |

每个实验使用同一 frozen set、同一模型版本、同一 endpoint 时段、同一 evaluator/canonicalizer，并按题交错执行。健康 VOID 先于能力判定；错误、timeout 和未完成题留在分母。

### 7.2 必须报告的指标

**正确性**：`correct / incorrect / invalid / unknown`、四类 transition、Invalid Rescue/Damage、Net Correct Gain。  
**候选质量**：candidate count、closed/weak rate、answer marker rate、Decision Completion Rate、Final Candidate Stability、conflict rate、route diversity、resolver A/B/UNKNOWN、finalizer rate。  
**运行健康**：logical calls、requested/completion tokens、平均/P95 latency、`finish_reason=length`、timeout、API error、response length。  
**证据质量**：deterministic PASS/FAIL/UNKNOWN、每个 check 的 witness/hash/version、serializer 是否改变值、safe incumbent 是否被覆盖。

### 7.3 晋升门

区分探索门和 ARM 正式 Full-30 门，避免口径混乱：

**探索候选至少满足：**

- 两轮同题交错；
- 两轮 Net Correct Gain 均不为负，目标至少一轮 `>= +2`；
- Invalid Rescue 严格大于 Invalid Damage；
- Correct Damage 不超过 2 题；
- error/timeout 增加不超过 1 题；
- 平均调用增加不超过 0.5/题；
- P95 不超过 baseline 的 120%；
- 不使用 gold、题号特判、answer bank、benchmark lookup 或无界 rollout。

**ARM v2.1.3 Full-30 正式候选还必须满足既有规范：**

- 代码、接口、预算、无 gold 和无循环门全部通过；
- 同一 30 题的 paired net gain 至少 +3，或达到既有 correct floor；
- 第二轮方向非负，且不是单轮偶然上涨；
- invalid/incomplete 不超过既有硬门；
- false-trusted-primary 相对基线减少；
- `A wrong → B correct` 大于 `A correct → B wrong`。

只减少 invalid、不增加 correct 的实现标记为 `hygiene-only`，可以保留在 ARH/host 层，但不能称为数学能力晋升。

### 7.4 NO-GO 条件

以下任一情况立即停止该候选：

- finalizer 改变 canonical value；
- invalid→incorrect 或 correct→incorrect 稳定增加；
- Resolver 需要重解整题或产生 candidate C；
- parser 依赖某题编号、gold、答案库或 benchmark lookup；
- verifier 的 UNKNOWN 被改写为 PASS；
- 只在一个窗口好看，第二轮方向反转；
- 健康 VOID 后继续挑选成功题统计；
- 为维持平均 calls 而接受大量 false-trusted primary；
- 通过强 JSON/grammar 迫使模型输出低质量值，但只报告 schema success。

## 8. 实现步骤与文件边界

不要把新的 parser、router、resolver、finalizer 和 telemetry 继续堆进 `harness_contracts.py` 或单一 ARM 总控文件。建议按以下小模块拆分：

```text
reasoning_agent/task_contract.py
reasoning_agent/candidate_canonicalizer.py
reasoning_agent/verification_gates.py
reasoning_agent/decision_record.py
reasoning_agent/invalid_recovery.py
reasoning_agent/finalizer.py
scripts/audit_invalid_ledger.py
scripts/replay_invalid_rescue.py
tests/test_answer_contract.py
tests/test_verification_gates.py
tests/test_invalid_replay.py
tests/test_finalizer_value_lock.py
```

实施顺序：

### P0：冻结证据和账本

- 固定 evaluator、canonicalizer、dataset manifest、runner 和源码 hash；
- 对已有 v1.1/v1.2/ARM 工件生成逐题 ledger；
- 分离 invalid、unknown、health error、timeout；
- 记录 raw span hash、finish reason、candidate source 和 failure class；
- 零模型调用，不切换默认配置。

验收：每题恰有一条 ledger；每个 invalid 有 R/S 类别或 UNKNOWN；100% 可追溯；gold 不进入 solver 或 recovery prompt。

### P1：实现 ARH host 层

- 先完成 typed parser、canonicalizer、completeness 和 serializer；
- 增加整数、有理数、表达式、集合、向量、矩阵、单位、choice、多问和 proof fixtures；
- 在 invalid-dev 上调试，在 invalid-holdout 和 valid-regression 上验收；
- 只输出 `最终答案 + boxed` 双形态，不改变模型调用。

验收：host replay 的 invalid→incorrect 为 0；已有正确答案不因包装归一化变坏；失败有 rejection reason；仅降低 invalid 则标记 hygiene-only。

### P2：重构 ARM candidate lifecycle

- 保留 Primary、B、safe incumbent、budget ledger；
- 把 completeness、verification、selection、serialization 分成独立状态；
- 修复 boxed raw value 与 normalized value 的边界；
- 禁止 weak challenger 覆盖有更强证据的 incumbent；
- 增加 `false_trusted_primary` 和 `candidate_replacement_reason`。

验收：B 失败不会丢掉合法 A；UNKNOWN 不会恢复被明确撤回的候选；候选版本可从 ledger 重放；所有调用仍受既有上限。

### P3：接入受限 deterministic gates

- 先做 substitution、numeric、constraint、mod、finite-domain、unit、boundary 中覆盖明确的少数 check；
- 每个 check 有 PASS、FAIL、UNKNOWN 三类 fixtures；
- 保存 candidate id、claim hash、check version、耗时和 witness；
- 任何 unsupported/domain unresolved 都返回 UNKNOWN。

验收：模型自报 CHECK 不可直接生成 PASS；check 不得误拒已知正确答案；没有全称证据时不输出 verified。

### P4：路线多样性和有界升级

- 强制 A/B 诊断先于扩大 resolver；
- B 互盲于 A，使用不同通用 route family 或 fresh independent route；
- 只在缺失、冲突、截断或无正证据时触发；
- 第三槽在 finalizer 和 resolver 之间互斥；
- 不新增第四次调用。

验收：逐题统计 oracle、A/B transitions、route diversity、平均和 P95 成本；若 Oracle(A,B) 不明显高于 A，停止扩展 resolver，回到 solver/generation。

### P5：一次 OFF finalizer

- 只接受 closed candidate + protocol-only failure；
- 输入 TaskContract、canonical value、validation summary 和失败字段；
- host 比较输入输出 canonical value；
- 不允许新 candidate、重解、脑补和 UNKNOWN→PASS。

验收：两轮同题交错满足探索门；否则关闭模型 finalizer，保留纯 host serializer。

### P6：最后才做 adaptive router

- easy/direct 走 OFF；hard/uncertain 走 ON；最终都经同一 ARH 和 Verification Gate；
- 记录 route decision、误路由、成本和结果；
- 若路由无法稳定区分，退回固定 OFF baseline + bounded host repair，而不是默认全 ON。

## 9. 外部调研如何采用

| 来源 | 在新 ARM 中采用 | 明确不照搬 |
|---|---|---|
| DeepSeek-Math | 多级抽取、boxed/answer-is 解析、抽取与判分分离 | 不把 boxed 直接当数学 verified |
| Qwen2.5-Math | 题型 parser、math equality 与有限工具轮次 | 不把工具循环扩成无界 agent |
| AgentAIMO | parser → arithmetic/symbolic/finite → format 的流水线 | 不直接引入多轮 correction loop |
| Light-R1 / DeepScaler | extractor、format reward、solver/evaluator 分栏 | ORM 不能代替 proof verifier |
| open-r1 | finish_reason、usage、有限 retry 和可审计产物 | 训练/生成配置不能直接当比赛配置 |
| vLLM / Outlines / Guidance / LM Format Enforcer | schema/grammar 的 capability probe 和离线测试 | 当前 client 未确认支持前不依赖 native constrained decoding |
| Instructor / PydanticAI | typed output、validation error、有限 repair | 不允许无限 retry |
| LangGraph | loop 结束后的 finalizer seam | 额外模型调用必须计入预算 |
| Math-Verify | 本地差集诊断 | 不替换默认 evaluator，不美化分数 |

这些来源证明的是成熟的工程分层模式，不证明它们在 Intern-S2 或本赛事数据上有净 correct 增益。每一项都必须先变成单变量、可回滚、可配对的实验。

## 10. 最终建议

ARM 应继续保留，但它的核心含义需要收窄：

```text
ARM 不是“另一个会解题的模型”。
ARM 是控制候选、证据、预算和提交状态的 host 控制器。
```

建议的下一版本顺序是：

1. 先以 ARH 解决可复用的答案表示和 parser-contract invalid；
2. 以 safe incumbent 和 checkpoint 解决截断后已有候选的保护；
3. 以 deterministic verification 解决“能验证就不再调用 LLM”；
4. 以路线多样性和 A/B Oracle 诊断决定第二候选是否值得；
5. 只对闭合候选做一次受值锁定的 OFF finalizer；
6. 最后才做 adaptive ON/OFF compute allocation。

这样设计既采纳了 2026-08-29 评测方法报告中证据最强、风险最低的 ARH 和双判分器诊断，也保留了 ARM 的候选生命周期和预算优势。它把“invalid → correct”放在最可能成功的 host 层先做，但不把 invalid→incorrect、correct damage、健康错误或跨窗口波动隐藏起来。

在 E0–E6 两轮配对实验和既有 ARM Full-30 晋升门全部通过以前，ARM-ARH 只能是实验候选；不能改默认提交配置，不能把本地分数写成官方能力，也不能因为架构图看起来更完整就宣称已经提升。

## 11. 参考索引

- 本仓库：[`evaluation_adoption_提分行动_2026-08-29.md`](../evaluation_adoption_提分行动_2026-08-29.md)
- 本仓库：[`arm_harness_v1.md`](../architecture/arm_harness_v1.md)
- 本仓库：[`arm_v2.1.3_technical_spec.md`](../9.29/v2.1.3/arm_v2.1.3_technical_spec.md)
- 本仓库：[`arm_v2.1.3_acceptance_spec.md`](../9.29/v2.1.3/arm_v2.1.3_acceptance_spec.md)
- 本仓库：[`0003-thinking-on-adaptive-candidate-first-harness.md`](../adr/0003-thinking-on-adaptive-candidate-first-harness.md)
- 本仓库：[`excluded_approaches.md`](../excluded_approaches.md)
- 本仓库：[`verification_decision_output_research_2026-10-03.md`](verification_decision_output_research_2026-10-03.md)
- DeepSeek-Math：`evaluation/data_processing/answer_extraction.py`、`evaluation/eval/eval_utils.py`，commit `b8b0f8c`
- Qwen2.5-Math：`evaluation/parser.py`、`math_eval.py`、`grader.py`，commit `a45202b`
- AgentAIMO：`src/verification/pipeline.py`、`src/solver/answer_selector.py`，commit `5be44b1`
- Light-R1 / DeepScaler：`system_prompts.py`、`rewards/math_reward.py`，commit `40b5965`
- vLLM structured outputs：`docs/features/structured_outputs.md`，commit `1a001d5`
- Outlines：`docs/examples/structured_generation_workflow.md`，commit `c52af84`
- Instructor：`structured_outputs.md`、`semantic-validation-structured-outputs.md`，commit `e12f8b4`
- PydanticAI：`docs/output.md`，commit `6695132`
- LangGraph：`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py`，commit `7dc9195`
