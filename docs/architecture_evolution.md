# 数学推理智能体架构演进总表

更新时间：2026-10-05

本表回答“每个版本的架构是什么、解决什么问题、现在是否还在默认路径”。
它记录的是架构家族和关键版本，不把每个温度、token、题集或单题 A/B 变体伪装成
新架构。实验数字、VOID/NO-GO 判定和逐题工件仍以
[`docs/excluded_approaches.md`](excluded_approaches.md) 与
[`docs/experiments/`](experiments/) 为准。

## 状态口径

| 状态 | 含义 |
| --- | --- |
| `CURRENT` | 当前 checkout 或官方接口仍可到达的运行路径；不等于能力已验证 |
| `CANARY` | 曾经被授权搭载或发布，保留回滚锚；能力证据可能不足 |
| `DEFAULT_OFF` | 代码和测试保留，但默认构造不启用 |
| `CODE_ACCEPTED` | 零模型结构、预算、接口或卫生门通过；不产生数学能力结论 |
| `ARCHIVED` | 实验已封卷，保留用于复核，不应原样复跑 |
| `REJECTED` / `NO_GO` | 已有证据不支持晋升，除非新假设、新编号和新预注册 |

## 当前架构（2026-10-05）

当前活动分支为 `codex/arm-v214-cfr`，GitCode 发布面将采用本协议对应的 CFR 提交，
`43a02da` 作为回滚锚，运行时核心仍保持
`ReasoningAgent(client, solve)` 的赛事接口：

```text
official client
    ↓
ReasoningAgent / SUBMISSION_CONFIG
    ↓ 题型与答案形态分类
ConstraintFitOrchestrator
    ├─ SubmissionGateway（bank-off）
    ├─ HostRouter → Direct / Deep
    ├─ ARM v2.1.4 CFR
    │   ├─ Primary → Challenger
    │   ├─ Targeted Repair（仅具体可修复异议）
    │   └─ Fresh Review（精确对齐且 PASS 才替换）
    └─ FSDF legacy fallback（显式历史对照）
    ↓
HostParser / TypedParser / EvidenceLedger / conservative selection
    ↓
final_response + compact trace
```

当前提交 profile 的边界：

- Constraint-Fit Harness、Deep lane 和 ARM v2.1.4 CFR 在正式配置中可达；hybrid router、
  FSDF fallback、答案库、RAG 和 Skill 均关闭；
- temporary answer bank 默认关闭；已移除 reference RAG、reference Skill 和 method-card RAG
  运行时及其大型资源，避免默认发布树携带无效实验闭包；
- `final_response`、JSON 序列化、调用预算和 fail-closed 是硬接口；
- Deep formation、Direct/endpoint health 等历史窗口没有转化为数学能力结论。

本轮 repo-hygiene 只做了内部 seam 整理：
[`answer_parsing.py`](../reasoning_agent/answer_parsing.py) 承载纯答案解析，
[`harness_contracts.py`](../reasoning_agent/harness_contracts.py) 承载合同、候选和 typed parser；
它们不改变默认路由。

## 主线谱系

| 时期 / 版本 | 架构家族与核心机制 | 状态 | 代码 / 证据锚点 |
| --- | --- | --- | --- |
| 2026-06 | 赛事模板与 bounded reasoning agent：公开 `client.chat`、本地 JSONL runner、基本答案抽取 | `ARCHIVED` | `82722ef`、`9bc2a04` |
| 2026-07-29 | P0/P1 稳定化：预算、题型感知、答案优先 Prompt、时间收敛、多根答案规范化、112 题回归 | `ARCHIVED_BASELINE` | `7980b6b`、`7f040dc`、`031621a` |
| 2026-07-30 | P2 heterogeneous reasoners + P3-lite verify/revise + AnswerJudge/评测指标 | `DEFAULT_OFF` | `6af5142`、`34bfe96`、`47e2076` |
| 2026-08 | C0 / adaptive voting / verification-gated retry：4k+k5、B1 单次恢复、截断/冲突/卫生检查 | `ARCHIVED` / 部分机制保留 | `db3e974`、`3dd3b48`、`e345a45` |
| 2026-08 | 8k/k2、legacy 4k+k5、thinking-off、temperature、token ladder 等成本/资源基线 | `ARCHIVED` | `2660b46`、`be340db`、`c6950a8` |
| 2026-08 | Deterministic solver、SymPy/substitution、numeric CoD、strict salvage、TIR/PoT | `DEFAULT_OFF` / `ARCHIVED` / `REJECTED` | `1559a36`、`789ba3c`、`2660b46`；处置见排除表 |
| 2026-08-27 | `hetero_k5`：C0 调用预算内增加 Alternative 候选，形成官方 canary 锚 | `CANARY` / `DEPLOYED_UNVALIDATED` | `18f4f5a`、`25f99b5`、`archive/codex/b1-4k-canary` |
| 2026-08-28–29 | hetero + refine(P3)、Re2 reread、CoD numeric、ARH 双形态、GSA 聚合 | `CANARY` / `ARCHIVED` / 回滚 | `1e9e53d`、`d9203f0`、`dd27b68`、`97759a6`、`019cc40` |
| 2026-09-01–03 | BTCS Frame v2：严格 `FINAL/EVIDENCE/BODY` 帧、候选共识与受限仲裁；随后官方负结果回滚 | `ARCHIVED` / `NO_GO` | `30f3aeb`、`55f80e5`、`34bc353`；`BTCS-FRAME-V2-*` |
| 2026-09-03 | Stateful tail completion：前四路无答案时，第五槽续写尾段 | `DEFAULT_OFF` / `NO_PROMOTION` | `40a411a`；`STATEFUL-TAIL-V1-*` |
| 2026-09-04 | FSDF v1：`Analyze → B/C Fork → D Select/Deepen → E Finish`，最多 5 次调用，保留 legacy fallback | `CURRENT` / `CODE_ACCEPTED` / `NO_CAPABILITY_CONCLUSION` | `1afdbe7`、`de74934`、`FSDF-V1-CODE-ACCEPTANCE-001` |
| 2026-09-05–06 | FSDF v2 reliability 迭代：handoff、D/E 预算、FINAL_D、compact finish、skill route/harness | `ARCHIVED` / 多数 `NO_GO` | `FSDF-ITER-AB-001..012`、`FSDF-RELIABILITY-V2-*` |
| 2026-09-06–08 | FESF：evidence synthesis、SolveMemory、exact evaluation、Host Loop、Claim DSL、Skill adapter | `DEFAULT_OFF` / 官方 `NO_GO` | `ddc8bd0`、`921afad`、`90ee852`、`FESF-*`、`HOST-LOOP-*` |
| 2026-09-08 | CAR-001：thinking-on adaptive candidate-first，候选梯度、短恢复、有限裁决 | `DEFAULT_OFF` / 健康窗 `VOID` | `bd16a3f`、`CAR-001-ADAPTIVE-CANDIDATE-FIRST-*` |
| 2026-09-08–09 | CAR-002：两个互盲短候选 + 一致性选择；代码门、P3 健康窗通过，但 hard10 未过能力门 | `DEFAULT_OFF` / `NO_P5` | `CAR-002-DUAL-CANDIDATE-CONSENSUS-*` |
| 2026-09-10–11 | MATH-HARNESS-V1：ProblemContract、双轴 HostRouter、Evidence Ledger、typed parser、Deep lane、预算/观察/回退 | `CURRENT` / `CODE_ACCEPTED` / health `NO_GO` | `e6ea4e8`、`MATH-HARNESS-*`、`MATH-CONTRACT-ROUTER-CODE-001` |
| 2026-09-12–16 | reference RAG、18 学科 Skill、MCP/knowledge layers：作为可插拔上下文层接入，随后因无默认收益而归档并从发布树移除 | `ENGINEERING_ONLY` / `ARCHIVED` | `45ba13a`、`b218003`、`9edb5d4`、`1507d3a`、`ca15d39` |
| 2026-09-16 | HENG-only / COT+PoT：Issue #19 公开 client 契约、migration hardening、fallback budget 的独立 profile/A-B | `EXPERIMENTAL` / 非默认 | `fca3d2b`、`archive/codex/pre-cot-pot-20260916`、`HENG-COT-*` |
| 2026-09-21 | repo-hygiene 内部重构：解析和 Harness contracts 拆为深模块，保留旧导出 facade | `CURRENT` / 行为保持 | `codex/repo-hygiene-cleanup` |
| 2026-10-04 | GRH v1.1 / 119 回退锚与 invalid rescue 第三轮归档；删除默认关闭的 RAG/Skill 实验闭包 | `ARCHIVED` / `ROLLBACK_ANCHOR` | `43a02da`、`docs/archive/invalid_rescue_round3_2026-10-04.md` |
| 2026-10-04 | ARM v2.1.4 CFR：Primary → Challenger → 具体异议 Targeted Repair → 精确 Fresh Review | `CURRENT` / `DEPLOYED_EVALUATED_NO_PROMOTION` / `CODE_ACCEPTED` | `docs/releases/arm-v2.1.4-cfr-20261004/` |
| 2026-10-05 | ARM v2.1.7 incumbent-only structured confirmation | `EXPLORATORY_NO_GO` / `DEFAULT_OFF` | `docs/experiments/ARM-V2.1.7-STRUCTURED-CONFIRMATION-20261005/` |
| 2026-10-05 | ARM v2.1.8 compact finalizer：独立外部长度压力复验 | `EXPLORATORY_NO_GO` / `DEFAULT_OFF` | `docs/experiments/ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-REPLICATION-20261005/` |
| 2026-10-05 | ARM v2.1.9 incumbent guard：完整 incumbent 保留 CFR Challenger，收束器只处理缺失/不完整输出 | `NO_GO` / `DEFAULT_OFF` | `docs/experiments/ARM-V2.1.9-INCUMBENT-GUARD-20261005/` |
| 2026-10-05 | ARM v2.2 answer-commit-first：第一次请求先提交唯一答案，再进行最多四行核对；第二次仍走 CFR Challenger | `EXPLORATORY_NO_GO` / `DEFAULT_OFF` | `docs/experiments/ARM-V2.2-ANSWER-COMMIT-20261005/` |

## FSDF v2 迭代子谱系

这些不是 12 个彼此独立的默认架构，而是同一 FSDF v1 主线上的单变量候选：

| 迭代 | 变量 | 处置摘要 |
| --- | --- | --- |
| 0 | `d_result_to_e` | D 的 FINAL_D 是否作为 E 待检查候选 |
| 1 | `de_budget_swap` | D/E 预算对调；曾出现前移信号，未形成发布结论 |
| 2 | `finish_compact_final` | 紧凑 E 收尾；机制门未显示可靠收益 |
| 3 | `mandatory_final_d` | 强制 D 提前终答；激活率/截断表现反斥 |
| 4 | `finish_handoff_share` | 减少选中思路块并增大交接预算 |
| 5+6 | `handoff_open_first_e` + 确认窗 | 未形成稳定增益 |
| 7 | `finish_handoff_share_v2` | 截断/反转证据反斥 |
| 8 | `e_budget_up` | 增加 E 预算；对截断不敏感 |
| 9 | `deep_candidate_fallback` | E 失败时采纳 D 内容态候选；触发机制不足 |
| 10 | `thinking_off` | 截断改善但答案质量交换，未晋升 |
| 11 | `fsdf_skill_routes` | 路由卡作为软/受限上下文；默认关闭 |
| 12 | `fsdf_skill_harness` | 强制 route execution script；FSDF 技能弧收束 |

具体窗口与处置必须回到 [`docs/excluded_approaches.md`](excluded_approaches.md)，
不要只引用这个摘要表。

## 并行工程层（不是默认数学求解架构）

| 层 | 作用 | 当前边界 |
| --- | --- | --- |
| BCOMP bounded completion | 观察 client 生命周期、completion token、durable records | 工程诊断，不改变答案选择 |
| Error Notebook / temporary answer bank | 本地错误经验和显式 bank-on gateway | bank-off 默认隔离；不能混入能力结论 |
| Reference RAG / Skills | 提供参考题或软路线提示 | 已归档；代码和大型资源已从发布树移除 |
| Host Loop | intake、obligation、verifier adapter、evidence bridge | F0–F5 代码门不等于能力门，默认关闭 |
| Causal MCP / causal_lens | 独立因果分析 demo/工程 smoke | 不接入默认数学求解；`NO_CAPABILITY_CONCLUSION` |
| HENG/COT snapshots | 公开 client 迁移硬化与架构配对实验 | 只作实验/迁移证据，不是当前 submission profile |

## 版本判断规则

1. 分支名、代码存在和 canary 发布不等于能力晋升。
2. `CODE_ACCEPTED` 只证明结构、接口、预算或卫生；数学能力必须有适用冻结集和独立 A/B。
3. `VOID`、timeout、endpoint failure 保留在分母，不得改写成算法优劣。
4. 历史实现不删除；要重启必须创建新实验编号、新假设和新预注册。
5. 当前默认路径、实验候选、发布面和归档证据始终分开记录。

## 相关索引

- 当前术语和配置：[`CONTEXT.md`](../CONTEXT.md)
- 实验处置单一事实源：[`excluded_approaches.md`](excluded_approaches.md)
- 发布/分支/归档拓扑：[`branches_map.md`](branches_map.md)
- 证据目录：[`experiments/`](experiments/)
- ADR：[`adr/`](adr/)
