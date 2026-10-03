# 基于评测采纳报告的 ARM 全架构重设计

日期：2026-10-03  
范围：`Challenge-Cup-2026`、Intern-S2 endpoint、ARM v2.1.x、GRH v1.1/v1.2 相关文档与实验记录。  
状态：架构审阅与实验设计；本文件不修改生产代码、不切换 `SUBMISSION_CONFIG`，也不把零模型回放或跨窗口结果写成能力提升。

## 1. 结论

ARM 不需要被另一个“更合适的架构”替换。当前真正需要替换的是 ARM 内部职责混合的方式。

建议保留 ARM 作为 **控制平面**，重新定义为：

```text
ARM = Route + Compute Budget + Candidate Lifecycle + Evidence Policy + Bounded Escalation
```

把答案表示、候选规范化、确定性检查和最终提交拆成 ARM 外部可独立测试的宿主层：

```text
Problem
  ↓
Task / Output Contract
  ↓
ARM Router + Compute Policy
  ↓
Solver Backend
  ├─ Direct / OFF
  ├─ Structured / OFF or ON
  └─ Deep Reasoning / ON
  ↓
Candidate Ledger
  ↓
Host Extraction + Canonicalization（ARH）
  ↓
Structural / Completeness Gate
  ↓
Deterministic Verification Gate
  ↓
ARM Decision State Machine
  ├─ select incumbent
  ├─ bounded second route
  ├─ bounded repair / resolver（实验开关）
  └─ abstain
  ↓
Host Serializer
  ↓
Optional OFF Finalizer（仅协议修复，最多一次）
  ↓
Final Response
```

这里的 ON/OFF 是阶段职责，不是把同一次调用同时当作“推理器”和“判分器”：

- Thinking ON 负责困难题的理解、路线选择、推导和候选形成；
- ARM 负责预算、状态、升级条件和不可覆盖规则；
- Host verifier 负责可计算检查；
- ARH 负责抽取、规范化和稳定序列化；
- OFF finalizer（若接口支持 request-local 模式）只修复已闭合候选的协议问题，不重新解题。

如果比赛 client 不支持逐请求设置 `thinking_mode`，就直接使用宿主 serializer，不为了模拟 OFF 再增加一次模型调用。

## 2. 证据边界

### 2.1 已确认事实

以下结论来自仓库文档、代码或已封存实验，可直接复核。

1. [`evaluation_adoption_提分行动_2026-08-29.md`](../evaluation_adoption_提分行动_2026-08-29.md) 对 9 类判分实现做了源码级核对。跨口径的安全表示是“明确答案句式 + `\\boxed{}` + 最简规范形 + 无解释性尾缀”。缺少句式、十进制与最简分数、无序对象、单位覆盖和尾缀污染都会造成判分差异或 `invalid`。
2. 该报告明确建议 ARH 作为纯后处理：

   ```text
   最终答案：<canonical>
   $\\boxed{<canonical>}$
   ```

   它不新增模型调用，不修改 prompt，也不负责判断数学真值。
3. 同一报告明确不采纳默认 LLM-as-judge、PRM/process 评测、猜测官方判分器、Math-Verify 作为本地唯一口径和强 JSON/XML 输出。
4. [`docs/architecture/arm_harness_v1.md`](../../architecture/arm_harness_v1.md) 已经把 ARM 的 request-local ON/OFF、`fast_off`、`adaptive`、`deep_on`、有限调用数和候选账本写成实验接口；这说明 ARM 已具备控制平面雏形，不需要再引入一个平行总控架构。
5. [`docs/adr/0003-thinking-on-adaptive-candidate-first-harness.md`](../../adr/0003-thinking-on-adaptive-candidate-first-harness.md) 要求候选优先、最多三次调用、候选冲突不静默丢弃、safe candidate 只作保护、resolver 不能创造第三答案。
6. [`reasoning_agent/arm_v21_verification.py`](../../../reasoning_agent/arm_v21_verification.py) 当前默认 `DeterministicVerifier` 是 `NOT_APPLICABLE`。因此“模型写了 CHECK/VERIFIED”不能写成独立数学验证证据。
7. [`reasoning_agent/safe_candidate.py`](../../../reasoning_agent/safe_candidate.py) 的 safe candidate 是低信任 incumbent，用来防止中断或后续弱候选覆盖已有结果；它不代表数学上正确。
8. [`reasoning_agent/fesf_verifiers/adapters.py`](../../../reasoning_agent/fesf_verifiers/adapters.py) 已采用 `EXACT / REFUTED / UNKNOWN` 的 fail-closed 思路。有限搜索没有找到反例时仍是 `UNKNOWN`，不能自动升级为 `PASS`。
9. ARM v2.1.3 验收规范已经把 primary correctness、A/B oracle、`A_wrong→B_correct`、`A_correct→B_wrong`、false trusted primary、重复性、invalid/incomplete、平均调用和晋升门分开定义。它不允许只凭 invalid 减少或调用减少晋升。
10. [`docs/excluded_approaches.md`](../../excluded_approaches.md) 要求同窗口交错、单变量实验、VOID 先于能力判断、禁止跨窗口归因、禁止题号/答案库特判和无界 rollout。

### 2.2 数据支持的推断

1. 当前 ARM 的主要风险不是“有没有更多模块”，而是结构完整、正常停止或候选存在被过早解释成“数学可信”。这会把生成、验证、选择和序列化问题混在一起。
2. 现有 221 invalid 遥测显示，大量失败同时具有 `finish_reason=length`、候选记录或第二样本无增量等信号；这支持优先修复候选闭合、验证和提交路径，而不是默认增加长推理。
3. ARH 与候选生成、路线多样性、确定性验证正交，适合先做零模型 replay，再做逐步 paired 实验。
4. ARM 的二次调用只有在“路线不同”或“验证增量明确”时才有可能提供能力收益。重复同一自由推理更像随机扰动，不能默认称为有效多样性。

### 2.3 尚未验证的假设

- ON solver 是否在官方题型分布上比 OFF 产生更多正确且闭合的候选；
- 一次 OFF finalizer 是否能净减少 invalid，且不把已有 canonical value 改坏；
- 当前 endpoint 在复杂请求上的超时是否主要来自 token、排队、网络还是架构 prompt；
- deterministic verifier 在真实题型上的覆盖率和误拒率；
- 路由器能否在不使用题号、gold 或 benchmark lookup 的前提下可靠地识别适合 ON 的题。

这些问题必须通过同题、同评测器、同模型和交错顺序的实验回答，不能由架构图直接推出。

## 3. 为什么不是“删除 ARM、换成新架构”

ARM 已经承担了比赛环境最需要的四项职责：

| 现有 ARM 职责 | 保留原因 | 重设计后的边界 |
|---|---|---|
| request-local reasoning mode | 允许按题或按阶段控制 ON/OFF | 只记录与执行模式，不把模式等同能力结论 |
| candidate lifecycle | 防止弱候选覆盖已有候选 | 独立保存 raw、canonical、evidence 和版本 |
| compute allocation | 比赛有调用、token、单题和整轮预算 | 只决定是否升级，不负责“猜正确答案” |
| trust / escalation | 可把预算投给不稳定题 | trust 表示证据状态，不表示 gold correctness |

需要移出 ARM 内部的职责是：

- 直接把模型输出字符串当最终答案；
- 用结构完整、正常停止或模型自报检查作为 verified；
- 用同一个 generic resolver 同时完成数学求解、候选选择和格式修复；
- 把 `UNKNOWN` 通过 prompt 或额外自由推理强行变成 PASS；
- 让后续 challenger 无条件覆盖 primary 或 safe incumbent。

所以建议的方向是 **ARM-ARH / Decision-Aware ARM**：ARM 仍是唯一控制平面，ARH、Verifier、Serializer 是受 ARM 调度但可独立验收的能力与卫生组件。这样既不抛弃 ARM 的预算/状态积累，也避免继续扩张一个包含所有职责的巨大 harness。

## 4. 新架构的职责分层

### 4.1 Task Contract：先确定“要交付什么”

每题进入模型前，宿主只生成不含 gold 的任务契约：

```json
{
  "answer_type": "integer|rational|expression|tuple|set|choice|proof",
  "required_fields": ["value", "unit"],
  "allowed_equivalence": ["rational_normalization", "set_order_insensitive"],
  "domain_assumptions": ["x != 0"],
  "completeness_rule": "one_closed_value_or_all_requested_parts",
  "serialization": "competition_answer_v1"
}
```

契约不得包含题号特判、gold、answer bank 或 benchmark lookup。它只描述答案类型、必需字段、合法表面等价和何时算闭合。

### 4.2 ARM Router：只做路由和预算，不做数学判定

Router 输出 `risk_class`、`answer_type`、`route_confidence` 和 `budget_lane`。第一版只允许通用、可审计的特征：题目结构、答案契约、是否多问、是否需要证明或有限约束。不能用题号、题面片段、gold 或历史题答案特判。

建议初始 lane：

| lane | 初始 solver | 触发二次调用 | 上限 |
|---|---|---|---:|
| `direct_off` | OFF Direct | 候选缺失、结构失败或负证据 | 2 solver calls |
| `structured` | OFF/ON Structured | 无正证据、冲突或候选不完整 | 2 solver calls |
| `deep_on` | ON Deep | 只在候选缺失、截断或高风险冲突时升级 | 2 solver calls |

默认不因为题目更长就强制 ON；路由器只能提出预算策略，不能预言答案正确。

### 4.3 Solver Backend：ARM 调度，solver 解题

统一 backend 接口：

```text
solve(problem, task_contract, reasoning_mode, token_budget)
  -> raw_response + runtime_metadata + candidate_events
```

候选 backend 可以沿用现有 Direct/Structured/Deep 路径，不在此阶段大规模重写 FSDF。ARM 应允许 backend 返回“没有闭合候选”，而不是逼它填一个猜测值。

ON solver 的提示词只需要求通用 checkpoint，供宿主记录：

```text
CLAIM: <当前候选或 UNKNOWN>
EVIDENCE: <一条可检查的局部依据>
FINAL_CANDIDATE: <闭合候选；没有则 UNKNOWN>
STOP_REASON: <closed|conflict|insufficient|truncated>
```

这些 marker 是 telemetry 和抽取边界，不是数学证明。

### 4.4 Candidate Ledger：保存“模型产生了什么”

Candidate 不应只是字符串。建议在现有 `Candidate` seam 上补足：

```json
{
  "candidate_id": "c-01",
  "value": "…",
  "canonical_value": "…",
  "answer_type": "rational",
  "source": "explicit_marker|boxed|terminal_line|checkpoint|fallback",
  "completeness": "closed|partial|conflict|unknown",
  "reasoning_status": "established|tentative|truncated|unknown",
  "verification_evidence": [],
  "confidence": "deterministic|symbolic|enumerated|nl|unverified",
  "raw_span_hash": "sha256:…",
  "serialization_status": "ready|repairable|rejected"
}
```

`confidence` 必须由宿主证据填写，不能采用模型自报 confidence。raw span hash 用于审计来源，不要求把完整长思维写进逐题报告。

### 4.5 ARH：抽取、规范化、序列化

ARH 采用固定顺序，避免宽松 fallback 抢走高质量候选：

1. typed answer block；
2. `FINAL_CANDIDATE` 或明确 answer marker；
3. 平衡括号的 `\\boxed{...}`；
4. 题型专用 parser；
5. standalone numeric/choice/finite-set；
6. terminal line / RHS fallback；
7. 无闭合候选时返回 `UNKNOWN`。

canonicalizer 只做表面规范化：Unicode minus、LaTeX 包装、有理数约分、允许的集合顺序和单位表面形式。它不能改变多问顺序、定义域、单位含义或数学值。

数值/表达式题的宿主 serializer 目标是：

```text
最终答案：<canonical>
$\\boxed{<canonical>}$
```

非数值题使用对应的题型 contract；不强行套 boxed。serializer 只接受 `SELECTED` candidate，不能自行猜值。

ARH 的职责是降低抽取和表示失败；它不能把错误数学候选变正确。因此 ARH 单独通过时只能称为 `hygiene improvement`，除非同一 evaluator 下观察到 `invalid→correct`。

### 4.6 Deterministic Verification Gate：先算，再问模型

统一返回三态：

```text
PASS     在声明的假设和输入范围内成立
FAIL     找到明确反例、代入不成立或结构冲突
UNKNOWN  超出安全范围、无法形式化或检查超时
```

推荐顺序：

1. 结构与完整性；
2. 精确数值或代入；
3. 受限符号等价；
4. 合同明确的有限域穷举；
5. 反例搜索；
6. 边界、模、单位和维度检查；
7. 可形式化的局部证明义务。

每个 `PASS` 绑定 candidate id、raw hash、check 名称、版本和耗时；`FAIL` 保存短 witness；`UNKNOWN` 保存原因。模型输出中的 `CHECK`、`VERIFIED`、confidence 或“我已检查”都不构成 PASS。

### 4.7 ARM Decision State Machine：只做可解释裁决

```text
MISSING
  → PARSED
  → CLOSED
  → VERIFIED / REJECTED / UNKNOWN
  → SELECTED
  → SERIALIZED
```

冲突进入 `CONFLICT`，不按最后出现顺序覆盖。

建议的决策优先级：

```text
deterministic PASS
  > independent route agreement
  > typed completeness + safe domain
  > single unverified closed candidate
  > partial / truncated candidate
```

这不是把多个信号粗暴压成一个浮点分数。每个证据维度都要单独记录：完整性、确定性证据、路线独立性、定义域安全、冲突、截断。

### 4.8 Second Route：路线多样性优先于表述多样性

第二次 solver 调用必须满足以下至少一项：

- 使用不同的通用 backend 或路线族；
- 对原题重新建模，不读取 A 的 raw response；
- 产生可检查的不同中间关系或局部证据；
- 对 A 提供局部反例/代入义务，而不是再次自由作文。

不得把仅改变“请更仔细”“再算一次”称为有效多样性。B 不能读取 A 的候选值，否则其一致性不再是独立证据。

第二调用的三种用途必须区分：

| 类型 | 输入 | 允许输出 | 目的 |
|---|---|---|---|
| independent solver | 原题 + contract | 新候选/UNKNOWN | 生成路线不同的候选 |
| targeted challenger | 原题 + A 的有限 claim/evidence | objection + PASS/FAIL/UNKNOWN | 定点找错，不重算全题 |
| protocol finalizer | 已闭合 candidate + contract | 同值序列化/UNKNOWN | 修 marker、字段或包装 |

一个题最多使用其中两类追加动作，默认总 logical calls 不超过三次；deterministic check 不消耗模型调用。禁止 ON→ON→ON→resolver 的无界链。

### 4.9 Optional OFF Finalizer：只能修协议

只有下列条件同时满足时才允许调用：

- candidate value 已闭合；
- answer type 和 completeness 已确定；
- deterministic check 未发现数学冲突；
- 失败原因仅是 marker、字段、LaTeX 包装或序列化。

适配版提示词：

```text
You are a bounded final-answer serializer.
Do not solve the problem again and do not invent a missing result.
Read the supplied candidate object and task contract.
Return exactly one object with the existing canonical value, or UNKNOWN.
You may repair only delimiters, LaTeX wrappers, option labels, units,
and required field names. You must not change the mathematical value,
add a new candidate, or turn UNKNOWN evidence into PASS.
```

宿主必须重新解析 finalizer 输出，并验证 canonical value 与输入相等；不相等就丢弃并记录 `finalizer_value_changed`。如果接口没有 request-local OFF，使用 host serializer，不能为了阶段名称增加长推理。

## 5. ARM 旧组件到新边界的映射

| 旧组件/概念 | 新定位 | 保留/修改 |
|---|---|---|
| `HostRouter` / ARM route | 估计 contract、风险和预算 lane | 保留，禁止读取 gold |
| `reasoning_mode` | 每次请求的执行参数 | 保留，不能作为能力结论 |
| `CandidateTrustPolicy` | 追加证据与分配预算 | 修改；不得把完整格式当数学信任 |
| `SafeCandidateState` | 中断保护和 incumbent 保存 | 保留；明确 low-confidence |
| `DeterministicVerifier` | 三态 host gate | 改为窄范围真实 check；默认 unknown 仍安全 |
| ARM resolver | 有限 A/B 选择器 | 保留为实验开关；不能生成 C、不能重解全题 |
| ARM salvage/recovery | 分为 candidate recovery 与 protocol finalization | 修改命名和触发条件 |
| `final_response` | ARH serializer 的输出 | 移出模型自由文本路径 |
| GSA / voting | 候选聚合实验 | 不作为默认验证器，先独立过门 |
| skill/RAG | 软建议或独立实验层 | 默认关闭，不能读取答案库 |

## 6. 221 invalid 的分层救援顺序

不能把所有 invalid 都交给模型重算。建议按照离数学答案最近的类别优先：

| 层级 | 典型现象 | 首选动作 | 预期结果 |
|---|---|---|---|
| S1 / R4 | 候选存在，但 boxed、末行、单位、集合、矩阵或多问未抽取 | ARH parser + canonicalizer | invalid→correct；错误抽取必须 fail-closed |
| S2 / R3/R6 | `finish_reason=length`，但已有闭合候选或 checkpoint | safe incumbent + host serializer | 保留已有候选；不能凭截断自动升信任 |
| S3 / R2 | A/B 存在冲突，或选择错误 | deterministic comparison → bounded challenger/resolver | 只在有独立证据时切换 |
| S4 / R3 | canonical value 已确认，只缺提交协议 | 一次 OFF finalizer 或 host serializer | 只修格式，不改数学值 |
| S5 / R6 | timeout/health error，但已有强证据 incumbent | 保留 incumbent，禁止完整重跑 | 只在 contract 满足时提交 |
| S6 / R1/R5 | 没有闭合候选、推理本身错、题意/等价规则争议 | abstain / UNKNOWN | 不把 invalid→incorrect 当救援 |

必须同时记录：

```text
Invalid Rescue  = invalid → correct
Invalid Damage  = invalid → incorrect
Correct Damage  = correct → incorrect + correct → invalid
Net Correct Gain = new_correct - lost_correct
```

如果只降低 invalid、correct 不升，标记为 hygiene-only；不能用 coverage 替代 accuracy。

## 7. 采用评测调研结果的具体方式

### 7.1 ARH 直接采用

采用答案句式、canonical 规范形、boxed 双形态和无尾缀输出。该动作零新增调用，先做离线 replay，再做同题 paired 运行。

### 7.2 Math-Verify 只作诊断第二口径

并行记录当前 native evaluator 与 Math-Verify 的差集，量化“语义候选存在但表示不一致”的上限。Math-Verify 不替换默认本地口径，不写入官方提交路径。

### 7.3 Wilson 区间和重复实验

112 题或 221 题的小幅变化必须报告 Wilson 95% 区间；单轮 1–3 题波动不能直接解释成架构收益。候选至少做两轮同题交错 A/B。

### 7.4 明确不采纳

- 默认 LLM-as-judge：位置偏差、冗长偏差和同模型自增强风险；
- 默认 PRM/process judge：它是评测/训练侧组件，不是当前比赛 outcome 的独立证明；
- 为适配未知官方 verifier 而定制字符串投机；
- 强 JSON/XML 作为默认 solver 输出：当前 `InternChatClient` 没有公开 `response_format`/grammar 参数，native support 尚未验证；
- 通过放宽判分、剔除异常或删除无答案题来美化分数。

### 7.5 GSA、hetero+refine、FSDF 的位置

- `hetero+refine` 是采样/修正层实验，与 ARH 正交；必须以独立 paired 结果确认，不因单窗描述性结果直接融合。
- GSA 是候选聚合器，不是数学 verifier；保持 opt-in，先报告 `A_wrong→B_correct`、`A_correct→B_wrong` 和 resolver/aggregate cost。
- FSDF 继续作为 solver backend/历史对照，而不是把其多阶段交接强行塞进 ARM 的每题默认路径。

## 8. 实验顺序与验收条件

每一步都保持同一 frozen dataset、同一 model/version/endpoint、同一 evaluator/canonicalizer、同一题序交错和固定 workers。先判 VOID，再判能力。

| 阶段 | 唯一变化 | 模型调用 | 目的 |
|---|---|---:|---|
| E0 | 冻结当前 ARM/GRH baseline | 原配置 | 建立逐题 verdict 和 telemetry |
| E1 | ARH parser/canonicalizer replay | 0 | 测量纯输出可救援上限 |
| E2 | ARM candidate ledger + positive-evidence gate | 1–2 | 测量早停损伤、safe incumbent 和截断保护 |
| E3 | 第二路线/targeted challenger | 1–2 | 测量路线多样性是否产生真实 rescue |
| E4 | deterministic verification adapters | 1–2 | 测量 host gate 的 rescue/damage |
| E5 | 一次 OFF finalizer | 1–2 | 只测协议修复，值不变 |
| E6 | adaptive OFF/ON router | 1–2 | 最后评估 compute allocation |

### 8.1 必须报告

- `correct / incorrect / invalid / unknown`；
- `invalid→correct`、`invalid→incorrect`、`correct→incorrect`、`correct→invalid`；
- `A_correct`、`B_correct`、`oracle_correct`、`A_wrong→B_correct`、`A_correct→B_wrong`；
- Decision Completion Rate、Final Candidate Stability、answer marker rate；
- candidate count、complete/weak rate、conflict rate、finalizer rate；
- deterministic `PASS/FAIL/UNKNOWN` 及 check type；
- resolver A/B/UNKNOWN、judge rescue/damage（若做实验）；
- finish reason、truncation-before-final、平均/P95 latency、调用数、请求/完成 token、timeout、health error；
- 每一题的 raw span hash、candidate source、selection reason 和 rollback reason。

### 8.2 晋升门

建议区分探索门和正式 ARM 晋升门：

**探索门：** 两轮交错都不得出现净负 correct；`Invalid Rescue > Invalid Damage`；平均调用增幅不超过 0.5/题；P95 不超过 baseline 的 120%。

**ARM Full-30 正式能力门：** 沿用 `ARM-V2.1.3-ACCEPTANCE` 的严格条件，至少一轮 paired net gain `>= +3`，第二轮方向非负且 correct floor 高于 baseline；`invalid/incomplete <= 5/30`；false trusted primary 明显下降；平均调用满足 OFF `<=2.0`、ON `<=2.5` 的目标和硬上限；Gate A/D/F 必须通过。

**安全门：**

- `correct→incorrect` 不超过 2 题；
- error/timeout 增幅不超过 1 题；
- finalizer 不能改 canonical value；
- deterministic checker 不得把 unsupported 误判为 PASS/FAIL；
- 没有 candidate 时不得调用 finalizer；
- 不得使用 gold、answer bank、benchmark lookup、题号特判或无界 rollout。

只减少 invalid 或 incomplete，不增加 correct，记录为 hygiene-only；不能进入默认提交。

## 9. 分阶段实现计划

### P0：证据和 ledger

- 固定 judge/canonicalizer 版本；
- 生成 v1.1/v1.2/ARM 工件逐题 ledger；
- 分开 invalid、unknown、health error、timeout；
- 记录 raw span hash 和 failure class；
- 不产生模型调用，不改默认配置。

验收：每题一条可追溯记录，gold 不进入 solver、trace 或 recovery prompt。

### P1：ARH 宿主层

- `TaskContract`、`Candidate`、`DecisionRecord` 保持小模块边界；
- parser、canonicalizer、completeness、serializer 分离；
- 覆盖整数、有理数、表达式、集合、向量、矩阵、单位、choice、多问；
- 先做 invalid-dev replay，再用 invalid-holdout 和 valid-regression 验收。

验收：纯 replay 的 `invalid→incorrect=0`，不修改任何已有 canonical 数学值；只降低 invalid 时标 hygiene-only。

### P2：ARM 状态和正证据门

- primary、safe incumbent、challenger、selected candidate 分开保存；
- 取消“完整 + stop = trusted”的隐含规则；
- 让第二调用由缺失、冲突、截断或无正证据触发；
- B 不读取 A 的 raw response。

验收：错误 weak 候选不能自动覆盖正确 incumbent；`A_wrong→B_correct` 与 `A_correct→B_wrong` 可逐题统计。

### P3：窄范围 deterministic verifier

- 先实现代入、精确数值、定义域、边界、模和有限域检查；
- 每个 check 有 PASS/FAIL/UNKNOWN 正例、反例、超范围例；
- 把当前 no-op verifier 的 `NOT_APPLICABLE` 变成明确的适用性记录，而不是假验证。

验收：PASS 可绑定证据；UNKNOWN 不被 resolver 或 prompt 升级为 PASS。

### P4：路线多样性和 targeted challenger

- B 采用不同路线/后端，不只改变措辞；
- challenger 输出有限 objection、证据和覆盖范围；
- 不允许第三候选或完整重解作为默认行为。

验收：只有确定性检查或清晰异议支持时才更换 candidate；resolver 只输出 A/B/UNKNOWN。

### P5：一次协议 finalizer

- 仅处理已闭合候选的 marker、字段、LaTeX 包装和单位表面形式；
- host 比较输入/输出 canonical value；
- endpoint 不支持 request-local OFF 时关闭该模型调用，使用 host serializer。

验收：finalizer value changed、脑补、无候选调用立即 NO-GO。

### P6：adaptive ON/OFF

- 最后才引入 router 对 OFF/ON 的分配；
- 记录误路由和每个 lane 的成本/收益；
- 不能通过题长或单个关键词直接硬切 ON。

验收：两轮交错 paired，达到探索门；未达到则回退固定 baseline，不修改官方 profile。

## 10. 回退与 NO-GO

| 现象 | 处置 |
|---|---|
| ARH 把自然语言片段误抽成答案 | 收紧 parser，保留原始 invalid |
| checkpoint 增加错误候选 | 只保留 telemetry，关闭自动接管 |
| safe incumbent 被错误 challenger 覆盖 | 恢复版本化候选和证据比较，禁止就地覆盖 |
| verifier 误拒合法答案 | 降级该 check 为 UNKNOWN，不改 evaluator |
| finalizer 改变 canonical value | 立即关闭 finalizer，使用 host serializer |
| resolver 把 UNKNOWN 变成答案 | 禁止 resolver 进入默认路径 |
| invalid 降低但 correct 不升 | 标 hygiene-only，不宣传提分 |
| timeout/error 增加或 P95 超门 | 减少 ON 题比例，回退到固定 OFF/host serializer |
| 两轮结果方向不一致 | 保留实验，不晋升、不融合 |

以下任一条件应直接 NO-GO：

- 读取 gold、answer bank、benchmark lookup 或题号特判；
- 默认 ON→ON→ON→resolver 无界链；
- 用 LLM 自报 `CHECK/VERIFIED` 替代 host evidence；
- 用宽松 evaluator 或剔除异常回复美化 correct；
- 只有 invalid 下降，没有 `invalid→correct` 净收益；
- 未过单方法门就把 ARH、GSA、skills、RAG、resolver 一次性融合；
- VOID 健康窗仍被拿来做能力结论。

## 11. 最终建议

下一阶段不应发布一个与 ARM 平行的新总架构。应将 ARM 收敛为可靠的决策控制层，并按以下顺序增强：

1. ARH 宿主输出层，先从现有 invalid 记录中做零模型 replay；
2. Candidate ledger、safe incumbent 和正证据 gate；
3. 路线不同的第二候选或 targeted challenger；
4. 窄范围 deterministic verification；
5. 候选闭合后的一次协议 finalizer；
6. 最后才做 adaptive ON/OFF 路由。

这个方案直接采纳 2026-08-29 评测行动报告的可验证部分：输出共识表示、双判分器诊断、Wilson 区间、fail-closed 分母纪律和禁止默认 LLM judge/强结构化输出；同时保留 ARM v2.1.x 已有的 request-local mode、预算账本、候选生命周期和 Full-30 验收门。

它把“模型不会做”和“模型做到了但没有可靠提交”分开测量：R1 reasoning failure 不强行救援；R2 decision failure 交给有限证据裁决；R3/R4/R6 优先由宿主恢复；R5 evaluator boundary 保留争议。只有在同一 evaluator 下看到 `invalid→correct` 且没有相应 damage，才可以说架构真正提分。

