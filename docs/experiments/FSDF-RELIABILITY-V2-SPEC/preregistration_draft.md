# FSDF-RELIABILITY-V2 实验预注册草案（未运行、指标未冻结）

> 状态：**DRAFT — 不可执行**。本文件只登记候选与协议骨架；运行前必须由用户
> 冻结全部门阈值与样本量依据，并另行授权提交快照。本草案不授权任何真实模型
> 运行、官方评测或对 `SUBMISSION_CONFIG` / 提交仓库 main 的修改。
>
> 工程来源：Issue #15（FSDF v2 可靠性修复：多行交接、终答确认与可归因诊断），
> 规格见同目录 [`spec.md`](spec.md)。零模型代码验收记录见
> [`../FSDF-RELIABILITY-V2-CODE-ACCEPTANCE-001/result.md`](../FSDF-RELIABILITY-V2-CODE-ACCEPTANCE-001/result.md)。

## 0. 候选登记总览

| 增量 | method ID | 行为面 | 默认开关（AgentConfig） | 状态 |
| --- | --- | --- | --- | --- |
| P0 | `fsdf_diagnostics_v2` | 诊断与报告口径（不改变模型请求与最终答案） | `enable_fsdf_diagnostics_v2 = False` | 代码验收通过；作为所有实验窗的报告基座，不构成独立能力臂 |
| P1 | `fsdf_multiline_handoff_v2` | D→E 交接解析与组装 | `enable_fsdf_multiline_handoff_v2 = False` | 候选；需本预注册过门 |
| P2a | `fsdf_final_confirmation_v2` | 终答确认/弃答/冲突 | `enable_fsdf_final_confirmation_v2 = False` | 候选；需本预注册过门 |
| P2b | `fsdf_finish_prompt_v2` | 仅 E 收尾提示词 | `enable_fsdf_finish_prompt_v2 = False` | 候选；需本预注册过门 |
| P3 | `fsdf_branch_probe_v1` | B/C 分支包改为可检查中间进展 | 未实现 | 仅登记（见 §5），本规格不实施 |

各候选为独立单变量臂。**不默认合并**；任何组合必须重新预注册并满足方案排除表
的"单方法独立过门后才可融合"纪律。

## 1. 方法卡（每臂一份）

### 1.1 `fsdf_multiline_handoff_v2`（P1）

- **假设**：D→E 交接丢失多行推导、空字段吸收下一字段、重复候选静默取首值，
  导致 E 在不完整证据上收尾。修复字段边界后，E 收到完整推导/未解步骤/检查
  结果，可减少交接失败类 invalid 与 UNKNOWN。
- **唯一变化**：handoff 字段按已知标记边界多行解析；重复一致值去重、不一致值
  标记冲突（占位符值不参与冲突判定）；E 上下文 6500 总上限内 handoff 预留由
  2000 提至 3000，裁剪以完整字段/完整推导项为单位，丢弃对 E 可见
  （`HANDOFF_INCOMPLETE / HANDOFF_CONFLICT / HANDOFF_DROPPED / HANDOFF_PARTIAL`）；
  A 摘要与思路叙述在剩余预算内压缩。SELECTED_BRANCH 改用不跨行读取。
- **不改变**：调用数（≤5）、token 序列（2048/2048/2048/8192/4096）、其余阶段
  提示词、答案选择链（与 P2a 独立）。
- **协议快照**：`reasoning_agent/fork_select_deepen_finish.py` @ 本验收提交；
  RelayOptions.multiline_handoff_v2=True。
- **风险与边界**：块终止启发式（无标签冒号行/纯散文行/答案协议 token）可能
  截断个别带标签的推导行——宁可少传，不传半截内容；未选分支回显仍被排除。

### 1.2 `fsdf_final_confirmation_v2`（P2a）

- **假设**：v1 答案链会在 E 明确弃答后复活旧候选，并接受占位符、字段回显、
  冲突终答首项与孤立的 boxed/数学行，产生"看似有答案实则错误"的 incorrect。
  收紧为"仅确认终答可输出"后，incorrect 中相当部分转为 UNKNOWN；其中原本
  猜对的占比决定正确率升降（方向不可预先断言）。
- **唯一变化**：终答选择链改为——E 有效无冲突 FINAL 优先；E 显式
  `FINAL: UNKNOWN` 即最终 UNKNOWN（不回退）；重复冲突终答返回 UNKNOWN；E 终答
  缺失时仅可采用 D 协议成功且带显式 FINAL_D、无冲突、通过适用检查（占位符/
  回显/方法描述）的结果；未确认 CANDIDATE、boxed 中间量、孤立数学行不再自动
  成为终答；D 协议失败的原文不因含答案标记而绕过来源有效性检查。
- **不改变**：L0 选择逻辑、调用数、token 序列、E/D 提示词、交接内容。
- **协议快照**：RelayOptions.final_confirmation_v2=True。
- **注意**：本臂必然把部分 invalid/incorrect 转为 UNKNOWN；**只降低 invalid
  或 UNKNOWN 不构成能力门通过**（见 §3）。

### 1.3 `fsdf_finish_prompt_v2`（P2b）

- **假设**：v1 要求 E "第一项输出 CANDIDATE_E" 会诱导提前填写猜测候选；把 E
  的职责改为"先补完 OPEN 未解步骤、再回答原题实际要求的量、输出唯一确认
  终答（无法确认则 UNKNOWN）"可提高终答确认质量。
- **唯一变化**：仅 E 阶段 system prompt 替换为 `FINISH_PROMPT_V2`。答案解析、
  预算、其它提示词全部不变；不以模型自述"已检查"为验证。
- **协议快照**：RelayOptions.finish_prompt_v2=True。

### 1.4 `fsdf_diagnostics_v2`（P0，非能力臂）

- **内容**：finalize 事件新增有界摘要
  （`handoff_missing_fields / handoff_conflict_fields / handoff_clipped /
  finish_context_clipped / candidate_present / token_usage=unavailable /
  finish_reason=unavailable`）；运行器保留
  `stage/status/error_category/fallback_source/selected_branch/max_tokens` 等
  字段并分开统计顶层失败、阶段 client 异常、非字符串/空响应、协议失败、
  UNKNOWN；native/contract 判定逐题完整对比并标注"本地近似判定，非官方
  judger 等价实现"。
- **验收口径**：与关闭态在相同 ScriptedClient 序列上产生相同模型请求与
  final_response（已由零模型测试证明）。任何实验窗默认开启 P0，仅作为报告
  基座，不参与能力归因。

## 2. 数据、金标与题组身份

- **直接对照臂**：FSDF v1（官方评测提交 `de74934bf58c20a825af43e251da4c2eb9033b8c`，
  官方结果 correct 14 / incorrect 61 / invalid 37）。C0（9/112）仅作历史锚，
  不继承跨窗口收益。
- **开发/诊断集**：`sample_data/external_hard_sets` 三个冻结池
  （`set_a_olymmath_hard` / `set_b_aime` / `set_c_hle_math`，已查看的 150 题）
  **只用于诊断与回归**，不得作为能力确认集。
- **能力确认集**：待冻结。要求：事先冻结、与开发题组隔离、同一题的中英版本
  归入同组（组级抽样、组级配对）、评分器版本随 manifest 记录。
- **快照纪律**：正式实验窗必须基于已提交并授权的快照；**未提交工作区不得
  作为有效实验窗**。
- **评分器**：本地 native/contract 判定只是本地近似，不等于官方 judger；
  报告必须保留 `judge_note` 声明。

## 3. 门与统计（全部 UNFROZEN——运行前必须填写并经用户确认）

| 项 | 状态 |
| --- | --- |
| 健康 VOID 阈值（model_error/失败率上限） | UNFROZEN：运行前冻结 |
| 样本量与功效依据 | UNFROZEN：运行前冻结 |
| 双轮独立 A/B 规则 | 沿用仓库纪律：需两轮同窗交错复现，具体轮距 UNFROZEN |
| 配对检验与聚类口径（题组内相关） | UNFROZEN：运行前冻结 |
| 正确数门 | UNFROZEN：**不得**以"降低 invalid/UNKNOWN"替代 |
| 卫生门（invalid、serializable、trace 泄漏） | UNFROZEN：运行前冻结 |
| 成本门（平均/P95 调用、token、时长、6 小时整轮风险） | UNFROZEN：运行前冻结；预算上限不放宽（≤5 次逻辑调用、既有 token 序列） |
| 停止规则 | 先判 VOID（健康失败 → 窗口作废），再判能力、卫生、成本；任一门未冻结则协议不可执行 |

- **执行方式**：同窗口按题交错运行双臂、轮换首臂；固定 `workers=3`，运行中
  禁止改并发；共享端点的不同实验窗串行。
- **判定顺序**：VOID → 能力 → 卫生 → 成本；只降 invalid/UNKNOWN 不算过能力门。
- **归档**：每窗结束先写回报告、manifest 与处置至 `docs/excluded_approaches.md`，
  再进入下一方法。

## 4. 与既有排除表的口径冲突（不得默默绕过）

`docs/excluded_approaches.md` §六第 5 条要求"官方候选始终从 `b8b78aa` 对照面
构造聚焦单变量 diff"；本规格的直接对照是 FSDF v1（`de74934`，其本身已包含
相对 `b8b78aa` 的大量变更）。正式预注册时必须显式声明采用的对照面与理由
（FSDF 已是当前官方路径，`b8b78aa` 不再构成同协议对照），并取得用户确认后
更新排除表条目；在确认前，本草案不产生任何可执行实验。

## 5. P3 登记：`fsdf_branch_probe_v1`（不实施）

- **假设**：用"可检查的中间进展"替代仅列方法的分支包——B/C 在原预算内各输出
  恰好一个实际中间关系、适用条件与未解障碍——可提高 D 的选路质量与 D→E 交接
  的可验证性。
- **边界**：保持 B/C 各 2048 token、同一 client、五次逻辑调用上限；不增加
  分支搜索、不引入动态预算路由。
- **状态**：`REGISTERED_NOT_IMPLEMENTED`。本规格不实现、不运行；任何启动都
  需要新的 method ID、新预注册与用户授权。

## 6. 快速诊断实验登记：`fsdf_handoff_first_d_v1`（2026-09-05 用户授权）

- **假设**：D 阶段"交接产物优先"提示（SELECTED_BRANCH/CANDIDATE_D/OPEN/CHECKS/RISK
  在前、DERIVED 以"第N步:"完整条目持续交付、各字段只出现一次）在不增加调用与 token
  预算的前提下，提高 D→E 交接完整率与 E 终答形成率；正确数方向未知。交接可靠性由
  程序承担（保存/传递/完整性标记），提示词只是阶段约定，不是保证。
- **唯一变化**：仅 D 阶段 system prompt 替换为 `DEEPEN_PROMPT_V2`。用户建议的
  RESULT/PREMISES/NEXT 三问映射到现有协议字段（RESULT→DERIVED、PREMISES→RISK、
  NEXT→OPEN），不新增协议字段，不改解析、调用数与预算。
- **协议快照**：`RelayOptions.handoff_first_d=True`，其余为 v2 合并栈
  （P0+P1+P2a+P2b）；对照臂 `v2` 用旧 DEEPEN_PROMPT，唯一差异即 D 提示文本。
- **窗口设计**：同窗交错双臂 `v2` vs `v2hd`，冻结池 ×10/集（30 题，种子 20260905），
  workers=3，hard-stop 75 min。n=15/臂，仅支持方向性诊断，无统计功效。
- **验收观测**（不以格式通过率为唯一标准）：交接完整率（`handoff_missing_fields`
  为空的 finalize 占比 + 按字段分解）、E 终答形成率（`unknown_final` 与 finalize
  来源构成）、native correct 数、协议失败率、时长/调用分布。
- **边界**：门槛 UNFROZEN；诊断窗口不判定能力门、不修改 `SUBMISSION_CONFIG`、
  不推送、不发布；逐条目增量交付（长推导每完成一个局部步骤交付一个完整条目）的
  进一步协议改造不在本实验内，须独立预注册。

- **结果与修正（2026-09-05）**：窗口已完成并归档；用户审核修正三处报告口径
  （缺字段归因降级为假设、跨窗对照 20 题/池并撤回无漂移表述、成本口径改预算不变
  并补 nearest-rank P95）。v2hd 不晋升。交接验收缺口（程序无法识别模型侧截断、
  字段状态未分离）与下一候选 `fsdf_d_result_to_e_v1`（协议有效无冲突的 FINAL_D
  作为"待核查候选"进入 E 输入，单变量）及同题配对窗口已在
  [Issue #16](https://github.com/RUSS0718/Challenge-Cup-2026/issues/16) 规格化。

## 7. 迭代循环授权（2026-09-06 用户指示）

- 用户指示：以 FSDF-D-RESULT-TO-E-PAIRED-001 为底座（15 题、同题配对、先臂逐题轮换、
  workers=3、hard-stop 75 min），持续跑 15 题配对 A/B 回归；每轮结束后由子智能体
  分析结果并设计下一个方法；尝试不同方法反复迭代，直到用户干预。
- 规则：每轮恰一个单变量（前沿臂 vs 前沿+候选）；前沿仅在配对证据支持（correct 净增、
  无 correct→incorrect 反转、无卫生回退）时前移；失败候选记入排除表；每轮归档
  report/result 并写回排除表；总 token 18432 与 5 次调用上限不放宽（阶段内预算
  重分配允许，如 `fsdf_de_budget_swap_v1`）；不引入 RAG/文件记忆/额外 agent；
  全程在 `codex/fsdf-iterative-ab-001` 分支，不自动改 `SUBMISSION_CONFIG`/gitcode main。
- 已登记候选：迭代 0 `fsdf_d_result_to_e_v1`（配对窗 FSDF-D-RESULT-TO-E-PAIRED-001：
  机制未激活，D 14/14 未产出有效 FINAL_D，前沿不变）；迭代 1 `fsdf_de_budget_swap_v1`
  （D/E 预算对调 8192/4096→4096/8192，针对 E 截断近饱和 11-13/15 length）。

- 迭代 1 结果（FSDF-ITER-AB-001，15/15 对）：`fsdf_de_budget_swap_v1` 净增 +2 correct
  （invalid→correct ×2，无反转），E 终答形成 1→4、E 截断 13→10，D 侧交接缺失上升
  （29 vs 22）但 E 结果仍改善——**前沿前移至 v2hd_bs**。下一杠杆指向任务量/压缩
  （E 在 8192 下仍 10/15 截断）。仅迭代循环内基线选择，不改 SUBMISSION_CONFIG。
- 迭代 2 候选登记：`fsdf_finish_compact_final_v1`（E 紧凑输出 + 得到可确认答案立即
  FINAL 并停止；文本为 FINISH_PROMPT_COMPACT_V2 修订版，去掉对低激活机制
  FINAL_D_FOR_CHECK 的引用）。假设：E 的任务是自延展的，紧凑化 + 提前 FINAL 让终答
  在截断前落盘。主要风险：未验证中间量被提前确认转为 incorrect；冲突 FINAL 经 P2a
  归 UNKNOWN 抵消收益。观察：E 终答形成 ≥ 前沿 4/15 的方向、截断率、incorrect 计数、
  final_conflict 计数。反斥条件：E 终答形成仍 ≤4/15 且截断 ~10/15 → 提示词级任务
  塑造被证伪，转向 D 侧强制前置 FINAL_D。臂 `v2hd_bs_cf` = v2hd_bs + 该开关。
- 迭代 2 结果（FSDF-ITER-AB-002，15/15 对）：`fsdf_finish_compact_final_v1` 触发
  预注册反斥条件（E 终答形成 4/15 未超前沿、截断 11 未降）——候选证伪，前沿不变
  （保持 v2hd_bs）。方法学发现：同配置跨窗方差 ±1-2（v2hd_bs 两窗 3 vs 2 correct；
  aime-2024-I-8 / aime-9 摇摆题反复翻转），单窗净增 ±1 不足以稳健前移，后续前沿
  前移需跨窗复现或更大净增。
- 迭代 3 候选登记：`fsdf_mandatory_final_d_v1`（DEEPEN_PROMPT_MFD：CANDIDATE_D 后
  立即强制 FINAL_D、置于 DERIVED 之前以在 4096 截断下存活；删除可选 FINAL_D 尾句）。
  假设：激活休眠 deep_final 回退，把 E 失败的 ~11/15 invalid 池中"答对的 run"从 0
  变为可见；结构性单调（不影响 E 已形成终答的 run）。验收主门为机制激活
  （deep_final 有值 ≥5/15 候选 run 且 FINAL_D 具体值 ≥60% D-ok run），安全门为
  net ≥0 且零反转；net ≥ +1 且 M1+M2 → 前移；M1+M2 但 net ≤0 → 复跑一次。
  反斥：deep_final 激活 <5/15（机制再死）或 D handoff conflict+absent 恶化 ≥50%。
  臂 `v2hd_bs_mfd` = v2hd_bs + 该开关。
- 迭代 3 结果（FSDF-ITER-AB-003，15/15 对）：`fsdf_mandatory_final_d_v1` 机制激活门
  失败（deep_final 有值 1/15 < 门槛 5）——候选被反斥，前沿不变。新发现：强制输出
  字段使 D 截断 15/15、交接 absent 实例 42（vs 34）——D=4096 下"要求更多字段"与
  "预算约束"不可兼得；前沿 v2hd_bs 跨三窗 correct 3/2/4，方差观察确认。
- 迭代 4 候选登记：`fsdf_finish_handoff_share_v1`（E 输入构成重分配：删除"选中思路"
  块——其 PLAN 字段诱发 E 重推导——handoff 装配上限 3000→4600，总上限 6500 不变；
  预算/调用/提示词/解析均不变）。假设：E 截断是自延展重推导，移除重推导邀请并
  扩大进度交付让 E 从 OPEN 继续。门：M1 装配激活（候选臂交付 handoff 字符均值
  ≥+600 且 handoff_clipped 减半）；M2 行为（E 终答形成 ≥6/15、配对形成转化 ≥3、
  E 截断 ≤8/15）。前沿前移：net ≥ +2 且零反转，或 net ≥ +1 且 M1 通过并跨窗复现。
  反斥：E 终答形成 ≤4/15 且截断 ≥10/15 且 M1 失败；或 correct→incorrect 且 net ≤0。
  臂 `v2hd_bs_hs` = v2hd_bs + 该开关。
- 迭代 4 结果（FSDF-ITER-AB-004，15/15 对）：`fsdf_finish_handoff_share_v1`
  **net +3 correct、零反转**（含 1 例 incorrect→correct），E 终答形成 3→6、E 截断
  11→9（历史最低）——按注册规则第一条（net ≥ +2 且零反转）**前沿前移至
  v2hd_bs_hs**。M2 门大部分达标（截断 9 略超 ≤8 目标）；M1 为构造性激活（trace
  无直接字符量）。方差警示持续有效，确认性复现留待后续窗口。
- 迭代 5 候选登记：`fsdf_handoff_open_first_e_v1`（仅 E 侧 handoff 渲染顺序：
  OPEN 提到 DERIVED 之前，让 E 先读"剩余步骤"再读推导墙；装配保留优先级、解析、
  预算不变）。假设：E 自顶向下读输入并镜像其结构——推导墙在前诱发重推导，OPEN
  在前使输出先解决决定性剩余步骤、FINAL 更早进入输出流。门（配对 15）：
  E 终答形成 ≥7/15（前沿 6）且 E 截断 ≤8/15（前沿 9）；接受：net ≥ +2 零反转
  → 前移；net +1 零反转且双机制改善 → 复现窗后再前移。硬底线：任何
  correct→incorrect 反转 → 拒绝。反斥：形成 ≤6 且截断 ≥9（无效应）或形成升但
  net ≤0 且 ≥1 反转（风险兑现）。臂 `v2hd_hs_of` = v2hd_hs + 该开关。
- 迭代 5 结果（FSDF-ITER-AB-005，15/15 对）：`fsdf_handoff_open_first_e_v1`
  net +1 零反转，双机制计数改善（E 终答形成 1→3、截断 14→12）但未达机制门
  （≥7 / ≤8）——按规则进入确认复现窗（FSDF-ITER-AB-006 同臂同题重跑）：
  复现（net ≥0 且机制改善再现）则前沿前移至 v2hd_hs_of，否则前沿不变。
  基线臂本窗截断 14/15 为历史最差，run 方差极大。
- 迭代 6 确认窗结果（FSDF-ITER-AB-006，15/15 对）：复现失败——net −1（两例
  correct→invalid），机制计数走差（形成 4→3、截断 8→10，基线臂 8/15 为历史最好）。
  `fsdf_handoff_open_first_e` 记为方差内效应（两窗合计净 0），**前沿保持 v2hd_bs_hs**。
  累积证据：有效杠杆均为结构/构成类（E 预算、E 输入构成）；措辞/加字段/渲染顺序类
  全部反斥或方差内。
- 迭代 7 候选登记：`fsdf_finish_handoff_share_v2`（share 模式下移除最后的叙事块
  A 约束摘要，E 上下文 = 分支 + 纯进度交接；装配上限 4600→6050，总 6500 不变）。
  假设：E 全预算自延展由残余叙事诱发重分析——移除后更多 DERIVED/CHECKS 存活，
  E 续做已完成工作而非重新推导 → 截断减少 → P2a fail-closed UNKNOWN 减少 →
  invalid 池转化。选择依据：E 预算 +1024 的预期delta（~1 题）在噪声内，D 是
  危险捐出方（迭代 3 截断脆弱）。门：E 截断 ≤ 前沿 −2（机制）；前移条件
  net ≥ +2 零反转，或 net ≥ +1 且截断 −2 零反转。反斥：构成验证通过但
  截断 ≥ 前沿 −1 且 net ≤ 0（重推导邀请假设死亡）；或反转 ≥2 且集中于
  约束敏感题。臂 `v2hd_hs_sv2` = v2hd_hs + 该开关（隐含 share 组成）。
- 迭代 7 结果（FSDF-ITER-AB-007，14/30 对，2 run hard-stop 跳过）：
  `fsdf_finish_handoff_share_v2` 反斥条款命中（截断 10 vs 前沿臂 7，需 ≤6；
  net −1 且含 aime-2024-I-8 correct→incorrect 反转）——**重推导邀请假设证伪，
  前沿不变**。构成类杠杆穷尽（选中思路/A 摘要/渲染顺序均反斥或方差内）；
  E 截断对叙事内容不敏感（前沿臂本窗 7/14 为历史最低，纯方差）。
  剩余未试杠杆：自 A/B/C 捐出的二次预算重分配（A/B/C 2048→1536 各捐 512 →
  E 8192→9728，D 保持 4096）。
- 迭代 8 候选登记：`fsdf_e_budget_up_v1`（仅 E 生成预算 8192→9728；总 18432→19968，
  +8%，首次非预算中性移动）。决定性依据：逐阶段 finish_reason 遥测（迭代 4-7 四窗
  汇总，A 113/118、B 117/118、C 117/118、D 111/118 全部 length 截断）——**没有任何
  阶段有可捐出余量**，A/B/C 捐出变体被数据预否决；E 终答形成受生成预算限制
  （迭代 1 唯一前移杠杆）。门：机制 = 候选臂 E 截断 ≤ 前沿臂（同窗）−2 且
  E 终答形成 ≥ 前沿 +1 且 net ≥ +1；安全 = 零 correct→incorrect 反转、
  P95 ≤ 900s；前移需确认窗复现（截断 ≤ 前沿 −1、net ≥ 0、零反转）。
  反斥：截断 delta > −1 或 net ≤ 0 → 无复跑否决；P95 > 900s → 安全中止。
  成本报告义务：本候选为首次非预算中性移动，token 成本 +8% 须在报告中明示。
  臂 `v2hd_hs_eu` = v2hd_hs + 该开关（含 share 组成与预算交换）。
- 迭代 8 结果（FSDF-ITER-AB-008，13 配对对，3 run hard-stop 跳过）：
  `fsdf_e_budget_up_v1` 反斥条款干净触发（E 截断率 64% vs 69% 零改善；net −1）
  ——无复跑否决，前沿不变。科学结论：E 截断率对生成预算完全不敏感
  （4096→8192 曾有效，8192→9728 零效应，收益在 8192 饱和）；预算杠杆双向穷尽
  （A/B/C/D 94-100% length 无余量可捐）。前沿 token 上限保持 18432。
- 迭代 9 候选登记：`fsdf_deep_candidate_fallback_v1`（程序侧、仅 E 失败时生效：
  `_select_answer_v2` 在 deepen-ok、无 FINAL_D、无弃答后，若 CANDIDATE_D 为
  content 态（单一、非占位、闭合）按显式来源 `deep_candidate` 采纳）。VOID 门
  通过：可转化池（E-UNKNOWN ∧ CANDIDATE_D=content）逐窗 4-11/15，从未低于 3。
  依据：二值计分下错误候选与 UNKNOWN 同分（弱单调）；提示词/预算/构成杠杆
  已穷尽。门：接受 = net ≥ +1 且 ≥2 次 deep_candidate 转化且零不当反转，
  双窗确认后前移；结构性反斥 = 任何 correct→incorrect 翻转（实现 bug 自动反斥）。
  反斥：net ≤ 0 或转化 < 1 → 宣告 E 失败池惰性，循环达局部最优。臂
  `v2hd_bs_hs_dcf` = v2hd_bs_hs + 该开关。
- 迭代 10 候选登记：`fsdf_thinking_off_v1`（client 级思考开关：候选臂
  thinking_mode=False，基线臂=服务端默认；其余全部相同）。**探针证据（单题
  AIME、2048 预算）**：思考默认 = length/2048 tokens/零协议字段；思考关闭 =
  stop/178 tokens/全部字段产出——思考在输出流内消耗同一份 completion 预算，
  是全阶段 94-100% 截断与"E 截断对预算不敏感"的统一解释。机制门：候选臂
  E 截断 ≤ 3/15（对照历史 ~9-14）且 A-D 截断大幅下降；能力门：net ≥ +1 零反转
  （二值计分下思考关闭只会把被截断的 run 变为有输出的 run）。
  反斥：截断不降（思考开关对该模型无效）→ 记录并回到 deep_candidate 线。
  迁移性注意：官方路径 client 由平台提供，思考开关能否设置需单独评估；
  本轮先在本地诊断窗确证因果。臂 `v2hd_bs_hs_tkoff` = 前沿 + 思考关闭
  （client 级 kwarg，经 ARM_THINKING_MODE 表；不含于 SUBMISSION_CONFIG）。
- 迭代 9 结果（FSDF-ITER-AB-009，15/15 对）：deep_candidate 触发 0 次——可转化池
  （4/15）全部集中在 **D 协议失败的 run**（候选臂协议失败率 11/15，思考默认模式
  挤占 D 的可见输出），候选按设计正确排除协议失败 D；net +1 为方差。前沿不变。
  关键产出：D 协议失败率本身是思考模式的牺牲品 → 强化迭代 10（思考关闭）优先级；
  VOID 门后续应按协议状态分层。
- 迭代 10 结果（FSDF-ITER-AB-010，15/15 对，循环末轮）：`fsdf_thinking_off_v1`
  机制门决定性通过——思考关闭后全阶段截断基本消失（A/B/C stop 14-15/15、E 1/15、
  时长 4.7×下降），用户假设（思考在输出流内消耗 completion 预算=截断唯一根源）
  证实。但分数杠杆否定：invalid→incorrect ×7、correct→incorrect ×2、correct 净增 0
  ——截断是 fail-closed 保护，关思考把"不知道"变成"错着说"。前沿不变，
  **循环按用户指示于本轮结束**。迁移性警示已记录（官方平台 client 思考开关
  可控性未知）。
- 迭代 11 候选登记：`fsdf_skill_routes_v1`（宿主按题型+关键词预筛的解题路线层：
  目录 ≤3 条注入 D 的 user 提示，D 可在目录内声明 SELECTED_SKILL 改选（非法 ID
  回退宿主预选）；路线正文=输入要求/执行步骤/检查条件/预期产物，资源为仓库相对
  路径 math_routes.json；路由 0 模型调用，解析/调用数/预算不变；无匹配→前沿行为）。
  与被永久排除的方法卡 RAG 的实质差异：卡片不是参考知识而是程序化执行步骤，且
  产物映射到既有 handoff 工作状态字段。三臂窗（arms v2hd_bs_hs / v2hd_bs_hs_tkoff /
  v2hd_hs_sr）：a=前沿（思考默认）、b=前沿+思考关、c=前沿+思考关+技能路由；
  b-vs-c 为同思考设置下的单变量技能对比（满足研究笔记的单变量纪律），
  a-vs-b 为思考效应配对测量，a-vs-c 为用户指定的组合比较。反斥：c 相对 b
  正确数净减或 SELECTED_SKILL 声明率 <1/3（正文无操作价值）→ 技能路线反斥；
  b 确认思考效应（截断大幅下降+净 ≥0）则思考关成为后续基线。
- 迭代 11 结果（FSDF-ITER-AB-011，三臂 45/45 run）：思考关三重确认（截断全阶段
  基本消失、时长 5.3×、correct 仍在噪声带、incorrect 爆炸 13/15）；技能路由层
  tkoff-vs-sr 净 +1（弱信号），SELECTED_SKILL 声明 0 次（可选声明不触发模式再现），
  路由层唯一客观变化 D 截断 2→3。前沿不变。官方 canary 回归（7/112）待用户决策
  是否恢复 v1。下一轮（迭代 12）：按用户"设计强制 harness、把限制拉高"的指示，
  实现 `fsdf_skill_harness_v1`（D 系统提示=路线执行脚本、每步强制"第N步:"输出、
  程序侧完成度遥测；思考关），臂 v2hd_hs_tkh = 思考关 + 强制 harness。
- 迭代 12 候选登记：`fsdf_skill_harness_v1`（强制 harness，按用户指示"把限制
  拉高"：D 系统提示 = 宿主预选路线的执行脚本——"是路线执行器，不是自由解题者"、
  不得跳步/改序/自由发挥，每步强制"第N步:"输出行，程序侧统计完成度
  （harness_steps_completed/expected）；E 获路线核查附录。思考关（用户前提：
  "思考关掉的话模型会很笨，必须把限制拉高"——关思考后 4096 预算几乎全部可用于
  内容，迭代 3"加字段必截断"的前提不再成立）。门：机制 = 候选臂
  harness_steps_completed/expected 完成率（结构性遥测，噪声免疫）+ D 协议失败率
  不高于基线臂；能力 = net ≥ 0 零反转（方向性）+ correct 数；确认窗规则同前。
  反斥：完成率 < 50% 且 net < 0 → 强制 harness 在该模型上不可行，记录后回到
  deep_candidate 线。臂 `v2hd_hs_tkh` = v2hd_hs + skill_harness，思考关
  （ARM_THINKING_MODE）。基线臂 `v2hd_bs_hs_tkoff`（同前沿配置、思考关、无 harness，
  迭代 11 已测 1/13/1——本窗重跑作同窗基线）。
