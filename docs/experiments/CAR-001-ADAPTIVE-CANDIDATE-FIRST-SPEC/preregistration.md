# CAR-001：thinking-on 自适应候选优先 harness 预注册

状态：**已达成设计共识，未执行**。本文件只登记候选架构和实验顺序；运行前仍须
冻结代码快照、题集、评分器、健康门阈值和实际配置，并由 manifest 记录。本文不授权
修改 `SUBMISSION_CONFIG`、提交 GitCode 或启动官方评测。

## 1. 目的与假设

官方 client 不能由 `ReasoningAgent` 可靠关闭 thinking。现有 FSDF v1 的固定
Analyze→Fork→Select/Deepen→Finish 五阶段在 thinking-on 下会把阶段截断、协议失败
和 fail-closed 级联成 invalid；提高预算和多次投票也没有稳定提升正确数。

CAR-001 假设：先形成一个短、可解析的候选答案，再按需追加候选或短裁决，能在不依赖
关闭 thinking 的前提下减少固定阶段税，同时保留难题的有限追加机会。首要能力门是
`correct`，其次是 valid/可解析与错误反转；截断率只作机制与成本诊断，不能单独晋升。

## 2. 对照与唯一增量

| 臂 | 协议 | 状态 |
|---|---|---|
| `fsdf_v1` | 当前 FSDF v1：A/B/C/D/E，最多 5 次调用，预算序列 2048/2048/2048/8192/4096 | 直接对照 |
| `car_001` | 候选梯度：1 次短候选 → 条件第 2 候选 → 至多 1 次短裁决/恢复 | 单一架构候选 |

CAR-001 是架构替换候选，不声称能把内部提示、预算和 handoff 逐项归因；若通过探索
门，下一轮必须再拆出单变量组件。两臂均使用 thinking-on 的官方默认行为，不传
`thinking_mode=False`。

运行前必须写入 `protocol_snapshot`：当前工作区有未提交改动，不能直接视为有效实验
快照。`SUBMISSION_CONFIG` 保持 FSDF v1；FESF、Claim DSL、Host intake、强制 skill、
临时答案库和所有跨题写回均关闭。

## 3. CAR-001 单题协议

### 3.1 首轮短候选

CAR 臂输入为原题、题型元信息和最多一个简短的冻结错题本条目；对照臂保持现有
FSDF 输入。CAR 的 skill 只注入一条“建议路线 + 适用边界”，模型可采纳或拒绝；
不要求逐步执行。F0/F1 若没有经过验证的冻结错题本条目，则不注入任何 notebook 文本。

首轮 system/user 约定：

```text
只求一个当前最可能的答案，不展开完整证明。
尽早输出：CANDIDATE: <答案>
随后最多写三行关键理由。没有可靠候选时写 CANDIDATE: UNKNOWN。
不要输出多个候选，不要输出长篇协议字段。
```

候选解析规则：

- `CANDIDATE:` 后必须有非空、非占位值；`UNKNOWN`、`无法确定` 等视为缺失；
- 缺失、显式 UNKNOWN、多候选标记、解析失败或宿主发现冲突时触发第二候选；
- 模型自报“低置信度”不单独触发追加调用；
- 候选形成不等于证明完成，trace 标记 `candidate_unproven`。

### 3.2 第二候选

第二次调用只在 3.1 的触发条件出现时执行，提示采用互补策略，仍只要求一个
`CANDIDATE:` 和最多三行理由。首版单题内部串行调用；runner 可用 3 workers 交错
题目和实验臂，不能假设公开 client 线程安全。

### 3.3 冲突账本与短裁决

两个候选同时存在时，宿主保留双方及来源，不按分支顺序静默丢弃：

1. 先做现有安全的规范化、精确等价和有限数值代入；
2. 若可确定等价，合并为一个候选并标记 `deterministic_agreement`；
3. 无法判定时最多调用一次短裁决器，输入原题、两个候选和有界理由；
4. 裁决器只输出 `FINAL: <答案>` 或 `FINAL: UNKNOWN` 及最多三行依据；
5. 仍冲突、显式 UNKNOWN 或裁决失败时返回 UNKNOWN。

不允许无界 SymPy、程序搜索或 verifier 链替代模型选择；Claim DSL/verifier 只做
shadow 记录，不进入首版决策链。

### 3.4 截断恢复

公开 client 若提供 finish metadata，则记录 `finish_reason`；若未提供，记录
`unavailable`，不得用字符长度伪造截断结论。若截断/不完整响应已经含唯一候选，
候选可直接进入账本；若候选缺失或截断导致解析失败，最多执行一次恢复调用：输入
原题和有界截断片段，只要求恢复/核对一个候选和一句理由，不要求从断点继续长证明。

恢复仍失败时返回 UNKNOWN；没有候选时不得凭空补答案。

### 3.5 最终输出

- 唯一、非占位、来源可追踪的候选：`final_response` 返回候选本身，trace 标记
  `candidate_unproven` 或 `adjudicated`；
- 通过确定性等价合并：标记 `deterministic_agreement`；
- 裁决器明确给出唯一终答：标记 `adjudicated`；
- 无候选、冲突未解、显式 UNKNOWN 或协议失败：返回 `UNKNOWN`；
- 不把截断原文全文当作最终答案，也不把未完成证明伪装成 verified。

## 4. 固定预算与时限

CAR-001 每题最多三次模型调用，completion 上限固定为：

```text
首轮候选 2048 + 第二候选/恢复 2048 + 短裁决 4096 = 8192 tokens（最坏情况）
软截止 10 分钟；硬截止 15 分钟
```

不得在同一窗口临时改预算。若 2048 的候选形成率不足，另立
`CAR-002-budget`，不得把预算调高混入 CAR-001。按最坏情况估算，112 题最多约
917,504 completion tokens，低于赛方 2M TPM；这只是容量投影，不是能力保证。

## 5. 错题本与 skill 边界

- 本地审核可从逐题记录沉淀错题本；每条经验必须有抽象题型、适用条件、失败模式、
  反例和证据链接；不得只记录“某题答案”。
- 正式评测只能读取评测开始前冻结的错题本版本，运行期间不得写入、更新或让前题
  影响后题；题面—答案直接映射仍属于独立答案库，不得伪装成错题本。
- skill 首版是软建议。只有两轮 fresh 同窗 A/B、correct 净胜至少 2 个分歧题、
  valid 不恶化、correct→incorrect 反转不超过 1 且健康门通过，才另立强制 skill
  实验；路线合规率不能替代能力门。

## 6. 分阶段实验计划

### F0：零模型代码门

检查候选解析、UNKNOWN/占位拒绝、冲突账本、确定性检查白名单、一次恢复上限、
deadline/call/token 硬上限、trace 脱敏、跨题状态隔离、冻结错题本只读、默认
`SUBMISSION_CONFIG` 不变。F0 不产生能力结论。

### F1：健康探针（baseline 6 题，CAR 6 题）

同一冻结小集、3 workers、逐题交错并轮换首臂。只判：端点可用性、顶层/阶段错误、
超时、候选形成率、解析失败、平均/P95 latency、调用数和 token。任何系统性端点故障、
未处理异常或预注册健康阈值触发即 `VOID`，不进入能力门。

### F2：24 题配对探索

通过 F1 才启动。baseline/CAR 同题交错、固定 3 workers、窗口串行。报告 native
correct/incorrect/invalid、valid accuracy、候选形成率、候选梯度触发率、裁决率、
截断/finish metadata、平均/P95 调用、completion token、wall-clock、6 小时投影及
逐题 correct→incorrect / incorrect→correct 反转。F2 只筛选方向，不自动晋升。

### F3：48 题 fresh A/B

仅当 F2 健康、机制实际激活、能力方向不反转且成本/时限门通过时启动。使用新编号
冻结集和新的协议快照；两臂同题交错、3 workers、thinking-on。F3 仍是本地候选门，
不自动修改 `SUBMISSION_CONFIG`；若要进入正式 canary，至少还需第二轮独立 fresh A/B。

## 7. 判定顺序与停止规则

1. **VOID/健康门**：端点、runner、超时、序列化和跨臂污染先判；VOID 后不得挑选
   好看的能力指标继续晋升。
2. **能力门**：correct 优先；建议 F3 预注册净胜至少 2 个分歧题，且
   correct→incorrect 反转不超过 1。只降低 invalid 或截断率不算能力通过。
3. **卫生门**：`final_response` 非空可序列化、无敏感 trace、冲突/UNKNOWN 规则不被
   绕过，invalid 不出现结构性恶化。
4. **成本门**：平均/P95 调用、token、wall-clock 和 112 题 6 小时投影不劣化；
   CAR 的早停收益必须由 manifest 的真实调用统计证明。

任一窗口结束后，先落盘 report、逐题 answers、manifest、协议快照和处置，再决定
下一窗口。共享端点实验串行；不提交、不推送、不改默认配置。

## 8. 必备工件

```text
docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-SPEC/preregistration.md
docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-*/run_manifest.json
docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-*/answers.jsonl
docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-*/report.json
docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-*/result.md
```

`run_manifest.json` 必须记录真实启用的开关、thinking 模式（官方默认）、每阶段
预算、调用上限、prompt/config 版本、题集 hash、评分器版本、平均/P95 成本和是否有
finish metadata。未执行前不创建 result 或伪造任何运行数字。
