# 已排除方案与实验处置注册表（截至 2026-08-29）

> 目的：任何新会话、成员或联网调研在提出实验前先查此表，避免重复试错。
> 官方评测是最终裁决；本地数据只用于预筛。同窗口交错是能力比较的必要条件。
> 本文件从官方基线 `b8b78aa` 曾包含的归档恢复，并补入 2026-08-27 的最新处置。

## 状态与重启规则

| 状态 | 含义 | 是否允许重新实验 |
| --- | --- | --- |
| `REJECTED` | 机制或配置已有直接负证据 | 不允许原样复跑；只有关键机制、适用条件或证据前提发生可审计变化时，另立新方案 |
| `ARCHIVED` | 未检出显著收益、证据不足或窗口作废，但基础设施可能保留 | 不允许以相同协议反复抽样；若重启必须写明新假设与新预注册 |
| `SUPERSEDED` | 被后续方案覆盖 | 不再作为独立候选 |
| `BASELINE` | 当前对照或已部署配置，不代表已经证明能力提升 | 只作为比较锚，不重复宣传旧收益 |
| `OPEN` | 已有明确下一步且尚未裁决 | 按现有预注册继续，不得临场改口径 |

融合纪律：`REJECTED` 组件不得通过“方法融合”绕过否决；只有单方法在适用数据上独立过门，
才允许进入融合实验。融合必须保留调用/token 上限，并以新的单变量增量预注册，不能一次混入
多个未验证组件。

## 一、官方评测处置（配置级）

权威数字见 [`docs/experiments/官方评测记录.md`](experiments/官方评测记录.md)。

| 方案 | 官方结果 | 处置 |
| --- | --- | --- |
| 4k + k1（legacy 单调用） | 4.46%，相对历史 4k+k5 低约 5.4pt | `REJECTED` |
| 32k + k5 | 9/112，invalid 60；54/112 runner error；约 9h23m | `REJECTED`：同分但成本、时限与可靠性明显更差 |
| B1 + 4k（验证门控重试） | 9/112，invalid 37；约 1h16m | `SUPERSEDED`：由当前 C0 取代；没有正确数增益 |
| answer-first + k5 + 4k（`b8b78aa`，C0） | 9/112，invalid 20，截断率 88.7%，约 5h12m | `BASELINE`：降低 invalid，但没有证明核心正确率提升 |
| hetero_k5（`25f99b5`） | 12/112，invalid 17，0 runner error；约4h24m | `BASELINE`：当前最好健康官方锚；跨窗结果不是因果证明 |
| hetero + Re2（`7479d47`） | 11/112，invalid 27，10 runner error；约7h24m | `REJECTED`：正确率、错误和6h时限三条件均触发回滚 |
| hetero + refine + ARH（runtime `9311d8c`） | 官方结果待回收 | `DEPLOYED_UNVALIDATED_CANARY`：发布 tip `46c08dd`，回滚锚 `95d5700` |

结论：提高 token 上限、在 k1/k5/B1 间机械切换都没有突破隐藏集正确数平台。C0 保留为官方
对照，不应把 invalid 下降等价成分数收益。

## 二、本地 A/B 已否决或归档（机制级）

| 方案 | 本地证据 | 处置 |
| --- | --- | --- |
| 失败退避（model_error 后等 1s） | invalid 无降幅，并出现首个 incorrect | `REJECTED` |
| 终答冲突复算 | 触发频率过低，retry_count 与基线无差异 | `REJECTED`；触发思想已被验证门控覆盖 |
| 主调用温度 0.4 / 0.8（对照 0.6） | 均值在 ±1 内，无稳定增益 | `REJECTED` |
| 8k + k2 | 同窗 vs 4k+k5：净 -2，p=0.75 | `REJECTED` |
| 8k + k3 | 同窗 vs 4k+k5：净 0，p=1.0 | `REJECTED` |
| 8k + k1 + temp0 | 同窗 vs 8k+k2：净 -3，p=0.25 | `REJECTED` |
| k3 投票（4k） | 净 +5/192，p=0.405 | `ARCHIVED`：不显著 |
| k5 投票（4k） | 净 +5/192，p=0.267 | `ARCHIVED`：不显著；当前只作为 C0 组成部分 |
| k5 早退阈值 3→2 | 净 -1，p=1.0 | `ARCHIVED` |
| 长题 token 路由（证明/推导 6144） | complex48 为 25/48，低于基线 26/48 | `REJECTED` |
| 6144 条件 token 重试 | 结果不稳定 | `REJECTED` |
| 严格 salvage（boxed/末行兜底） | 公共集退化 | `REJECTED`；不得与当前“仅失败路径抢救”混同 |
| 数值题答案前置（单调用） | 2026-08-21 公共集由 74–77% 降至 37–44%，invalid 激增 | `REJECTED`：只否决单调用形态 |
| answer-first + 投票 | 本地曾过门，官方 C0 invalid 下降但 correct 仍为 9 | `BASELINE`：不再作为新提分点 |
| PoT/TIR-first | 最终机会协议阶段二 0/36 程序有效率 | `ARCHIVED` |
| 候选答案回代验证（模型生成约束程序） | 约束程序有效率 0/36；fail-closed 零误支持 | `ARCHIVED` |
| 确定性求解器（直接解题） | 232 题仅 4 题安全命中 | `ARCHIVED`：保持 opt-in |
| SymPy 受控证据 | 无默认收益证据 | `ARCHIVED`：保持 opt-in |

## 三、2026-08-29 当前战役

| 方向 | 证据/状态 | 处置与不得重复项 |
| --- | --- | --- |
| 方法卡 RAG | 双轮正确率下降且延迟上升 | `REJECTED`：永久排除；不得作为融合组件复活 |
| P3/refine | 历史144对 b=12/c=4，p=0.0768；新W2/W2b各净+1、零败但仅complex48 | `DEPLOYED_UNVALIDATED_CANARY` 组件：取得用户授权的搭载资格，不是正式能力通过 |
| exact_g / GR 成本前沿 | 首筛失败；唯一复测触发对称 10% VOID。两窗描述性准确率无差异，调用约 C0 的 25%，墙钟约 1/3 | `ARCHIVED`，该设计线终止；不得继续复测或直接解锁 GR |
| P1 `current_salvage` | 2026-08-27 complex48 两轮中三份 arm-report 超过 10% model_error，public112 未产出；salvage 实际触发 0/96 | `OPEN / NO_VALID_CONCLUSION`：本次窗口 `ARCHIVED_VOID`；见 [`p1_salvage_result_2026-08-27.md`](experiments/p1_salvage_result_2026-08-27.md)，不得自动补跑或晋升 |
| P3′ `hetero_k5` | C0 k5 内1 Alternative +4 Direct；官方Run #5为12/112、0 runner error | `BASELINE`：保留为官方最好健康锚；本地正式因果门仍未完成 |
| ARH | complex48单窗25:25、双臂零error/invalid、零调用增量；官方靶是invalid池 | `DEPLOYED_UNVALIDATED_CANARY` 组件：本地只证明未明显回退，不能单独归因官方变化 |
| GSA package v0 | 单窗22→25，b=3/c=0，p=0.125；同时改变hetero、投票与调用结构 | `OPEN / EXPLORATORY_POSITIVE`：须按总规范重做k4_sc matched control和严格3+1 |

`exact_g` 的低成本属于可供未来新设计引用的机制观察，不构成旧 G/GR 重新运行的授权。若未来
把“低调用门控”与一个已独立过门的能力方法融合，必须作为新候选重新预注册，并保留 C0 和
能力单方法两个对照以分离成本效应与能力效应。

## 四、流程级排除（长期有效）

| 做法 | 处置与教训 |
| --- | --- |
| 跨时间窗口比较实验结果 | `REJECTED`：窗口漂移会制造假增益/假回退；必须同窗口交错 |
| 用 public112 校准隐藏题型 | `REJECTED`：112 题当前全被识别为 calculation，不能覆盖证明、解释和长题 |
| `--total-timeout-seconds 0` 当模型验收 | `REJECTED`：这是零模型调用的结构检查 |
| 未过预注册门直接改 `SUBMISSION_CONFIG` | `REJECTED`：一切晋升必须经过预注册、报告和用户确认 |
| VOID 后挑选好看指标继续晋升 | `REJECTED`：VOID 先于所有能力/成本门，不得事后豁免 |
| 同时运行两个共享端点实验窗 | `REJECTED`：会互相污染延迟与错误率，实验必须串行 |
| 为公开题 idx/题面/答案写特判 | `REJECTED`：违反赛事普适性与隐藏集约束 |
| 未独立过门就融合多个候选 | `REJECTED`：无法归因，也会扩大官方变更风险 |

## 五、GitHub Issue 状态防漂移

截至 2026-08-27，以下 Issue 仍显示 OPEN，但其标签/正文早于当前仓库证据。后续 agent 不得
只看 `ready-for-agent` 标签就重新执行，必须以本表和链接报告为准：

| Issue | 当前事实 | 本地处置 |
| --- | --- | --- |
| [#5 B1 晋升评审](https://github.com/RUSS0718/Challenge-Cup-2026/issues/5) | B1 已进入官方 Run #3，correct 仍为 9，随后被 C0 取代 | stale-open；按 `SUPERSEDED` 处理 |
| [#11 PoT rescue](https://github.com/RUSS0718/Challenge-Cup-2026/issues/11) | 解锁条件未满足；PoT/TIR 最终机会实验程序有效率 0/36 | stale-open；保持 `ARCHIVED`，不执行 |
| [#12 TIR 最终处置](https://github.com/RUSS0718/Challenge-Cup-2026/issues/12) | 所需最终处置已经落入归档，且 #11 未解锁 | stale-open；不得再次领取 |
| [#13 runner 护栏](https://github.com/RUSS0718/Challenge-Cup-2026/issues/13) | 短超时保护、熔断、诊断字段已有实现与测试记录 | stale-open；视为已完成，不重复实现 |
| [#14 弱点修复包](https://github.com/RUSS0718/Challenge-Cup-2026/issues/14) | 子方法已有逐项结果；答案先行+k5 已成为 C0，其余见本表处置 | stale-open；不得整包重跑 |

关闭或改标签属于外部协作动作，需团队确认；在此之前，本节承担防重复执行的护栏。

## 六、当前允许队列

1. 先执行总规范的 Pre-P0 评测可信度校准；未过门前不启动新的能力方法窗。
2. 当前 hetero+refine+ARH 只作未验证 canary；先回收官方日志并按预写条件保留或回滚。
3. GSA 只能按新 method ID、严格3+1和matched control重证，现有单窗不得直接搭载。
4. P1 首次回归已按 VOID 归档；任何健康复测都须新预注册且次数有限。
5. 联网调研只进入候选池；按
   [`math_agent_capability_methods_2026-08-27.md`](research/math_agent_capability_methods_2026-08-27.md)
   的排序逐个做代码缝隙与预算审计，再写单方法预注册。
6. 只有独立通过的单方法才可进入融合；优先考虑“能力方法 + 已证明的成本控制”，不融合两个
   尚未验证的能力方法。
7. 官方候选相对当时最强健康锚构造聚焦单变量 diff；本地实验分支不得直接推送。
