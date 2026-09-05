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
