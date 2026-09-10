# 已排除方案与实验处置注册表（截至 2026-08-27）

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

## 三、2026-08-27 当前战役

| 方向 | 证据/状态 | 处置与不得重复项 |
| --- | --- | --- |
| 方法卡 RAG | 双轮正确率下降且延迟上升 | `REJECTED`：永久排除；不得作为融合组件复活 |
| P3/refine 历史证据恢复 | 144 对配对 b=12/c=4，p=0.0768；未达显著晋升口径 | `ARCHIVED`：协议修复不等于分数收益；重启需新假设与同窗预注册 |
| exact_g / GR 成本前沿 | 首筛失败；唯一复测触发对称 10% VOID。两窗描述性准确率无差异，调用约 C0 的 25%，墙钟约 1/3 | `ARCHIVED`，该设计线终止；不得继续复测或直接解锁 GR |
| P1 `current_salvage` | 2026-08-27 complex48 两轮中三份 arm-report 超过 10% model_error，public112 未产出；salvage 实际触发 0/96 | `OPEN / NO_VALID_CONCLUSION`：本次窗口 `ARCHIVED_VOID`；见 [`p1_salvage_result_2026-08-27.md`](experiments/p1_salvage_result_2026-08-27.md)，不得自动补跑或晋升 |
| P3′ `hetero_k5` | C0 k5 上限内最多 1 Alternative + 4 Direct；首次健康探针 3/3 model_error，未完成 A/B | `DEPLOYED_UNVALIDATED_CANARY`：用户明确批准绕过本地门，runtime `18f4f5a`；见 [`hetero_k5_direct_release_2026-08-27.md`](experiments/hetero_k5_direct_release_2026-08-27.md)，回滚 `242c480` |

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

## 五点五、V4-HARD20-DUAL-001（2026-09-03）

| 候选 | 实验结果 | 处置 |
|---|---|---|
| `condition_checked_selection_v1`（KCV） | official-like hard20，20 题：native 2/1/17，0 model error，平均 3.50 calls | 与 PS-C 配对仅净胜 1 题；exact sign test p=1.0000；成本约为 PS-C 的 2.12×；`EXPLORATORY_NO_WINNER / NO_PROMOTION` |
| `plan_solve_compact_v1`（PS-C） | official-like hard20，20 题：native 1/2/17，0 model error，平均 1.65 calls | 成本占优但正确数低于 KCV，未满足优先候选净胜 2 题与显著性门；`EXPLORATORY_NO_WINNER / NO_PROMOTION` |

本窗不含官方基线臂，不能产生超过 `hetero_k5 @ 25f99b5` 的因果结论。不得据此进入
`core120` 或申请 official canary；若重启必须提出实质变化、新 method ID 和新预注册，
不得追加本窗第二轮追求显著性。

## 五点六、V5-HARD20-TYPED-CAPSULE-001（2026-09-03）

| 窗口 | 结果 | 处置 |
|---|---|---|
| 首轮（`retry=0`） | 20/20 请求未执行 HTTP 调用，全部 request error | `VOID_RUNNER_CONFIGURATION`；不作为能力结论 |
| 合规重跑（`retry=1`） | 20/20 完成、0 model error；typed answer 4/20（20%）、native correct 2/20、invalid 17/20、平均 1.85 calls | `EXPLORATORY_NO_GO / NO_PROMOTION`；形成率、correct、卫生、成本门均失败；不启动 baseline matched 复验，不修改 `SUBMISSION_CONFIG` |

完整工件：`docs/experiments/V5-HARD20-TYPED-CAPSULE-001-RETRY/`。官方发布面继续锁定
`hetero_k5 @ 25f99b5`（GitCode `34bc353`）。

## 五点七、CAUSAL-MCP-ENGINEERING-SMOKE-001（2026-09-04）

| 方向 | 结果 | 处置 |
|---|---|---|
| `causal_lens_shadow_v1` | 12/12 代表例通过；零模型调用；输出可序列化 | `OPEN / ENGINEERING_SMOKE_PASS / NO_CAPABILITY_CONCLUSION`；可继续做默认关闭的工程接入，不证明数学答案收益 |
| `causal_analyzer_stdio_demo` | 真实 `initialize → tools/list → tools/call` 通过；3 个工具注册；受限输入失败结构化；1.56s；0 孤儿进程 | `OPEN / ENGINEERING_SMOKE_PASS / NO_CAPABILITY_CONCLUSION`；未解锁 P4 正式门、统计算法能力或官方路径 |

完整工件：`docs/experiments/CAUSAL-MCP-ENGINEERING-SMOKE-001/`。本轮明确没有运行真实
模型、PC/OLC/DirectLiNGAM 能力 A/B、P4 的 500+200 正式门或 P5 双轮交错 A/B；不能据此
修改 `SUBMISSION_CONFIG`、提交仓库或默认指针。

## 五点八、CAUSAL-MCP-ALGO-SMOKE-001/002（2026-09-04）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAUSAL-MCP-ALGO-SMOKE-001` | PC、DirectLiNGAM、OLC 共 9/9 执行成功；后审发现 OLC 邻接矩阵未映射到 `data.edges` | `ENGINEERING_PARTIAL / NO_CAPABILITY_CONCLUSION`；保留缺陷证据，不作为完整 Demo fidelity 或能力结论 |
| `CAUSAL-MCP-ALGO-SMOKE-002` | OLC 边投影修复后的同协议独立复验：9/9 成功、0 超时、0 非法输出、0 孤儿进程；PC/DirectLiNGAM 各 2 边，OLC 各 4 边；17.027s | `ENGINEERING_SMOKE_PASS / NO_CAPABILITY_CONCLUSION`；仍不解锁 P4/P5 或官方路径 |

两个窗口均使用确定性合成 CSV、零模型调用；完整工件分别位于
`docs/experiments/CAUSAL-MCP-ALGO-SMOKE-001/` 和
`docs/experiments/CAUSAL-MCP-ALGO-SMOKE-002/`。

## 六、当前允许队列

0. `btcs_v1`：真实帧解析 6/7（85.7143%），低于 95% 预注册门，保持
   `ARCHIVED_VOID / NO_CAPABILITY_CONCLUSION`，不得原样复跑。
0a. `btcs_frame_v2`：离线结构门通过；独立 workers=1 资源资格窗仅 1/3 成功、
    2 timeout，状态为 `VOID_RESOURCE_HEALTH / NO_CAPABILITY_CONCLUSION`。
    fidelity 未启动；不得继承 v1 结果或修改安全门。2026-09-02 用户明确授权绕过
    本地晋升顺序进入 official trial，部署状态为 `DEPLOYED_UNVALIDATED_CANARY`；
    该发布动作不追认资源门或能力门通过，回滚锚为 `e9df37e`。

1. P1 首次回归已按 VOID 归档；方法仍为 `OPEN`，任何健康复测都须新预注册且次数有限。
2. hetero 已由用户直接发布为未验证 canary；官方结果前不追加第二个运行时变量，不把发布动作
   反写为本地 PASS。若补本地 A/B，仍须新健康窗口且不得与官方评测并行。
3. 联网调研只进入候选池；按
   [`math_agent_capability_methods_2026-08-27.md`](research/math_agent_capability_methods_2026-08-27.md)
   的排序逐个做代码缝隙与预算审计，再写单方法预注册。
4. 只有独立通过的单方法才可进入融合；优先考虑“能力方法 + 已证明的成本控制”，不融合两个
   尚未验证的能力方法。
5. 官方候选始终从 `b8b78aa` 对照面构造聚焦单变量 diff；本地 main/实验分支不得直接推送。

## 六点九、FSDF-V1-CODE-ACCEPTANCE-001（2026-09-04）

| 方向 | 结果 | 处置 |
|---|---|---|
| `fork_select_deepen_finish_v1` | T01–T37 代码验收通过；BTCS 互斥组合在当前基线不可构造，按 N/A 记录；零真实模型调用 | `CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

该结果只证明 FSDF 的结构、预算、接口、上下文压缩、降级、trace 卫生和并发隔离契约，
不产生数学能力或正确率结论。代码验收本身不授权默认切换；本轮之后用户已另行授权将
`SUBMISSION_CONFIG` 切换为 FSDF 默认并发布到 GitCode，仍不得将其表述为能力提升。
完整工件见 `docs/experiments/FSDF-V1-CODE-ACCEPTANCE-001/`。

## 六点十、FSDF-RELIABILITY-V2-CODE-ACCEPTANCE-001（2026-09-05）

| 候选 | 证据 | 处置 |
|---|---|---|
| `fsdf_diagnostics_v2`（P0） | 34 项 v2 验收 + 8 项运行器报告验收；开关前后同 ScriptedClient 序列请求与终答完全一致 | `CODE_ACCEPTED / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`；仅作实验窗报告基座，不构成独立能力臂 |
| `fsdf_multiline_handoff_v2`（P1） | 多行交接、去重/冲突、字段/推导项粒度裁剪验收通过；默认关闭 | `CODE_ACCEPTED / DEFAULT_OFF / NO_CAPABILITY_CONCLUSION`；候选，需预注册过门 |
| `fsdf_final_confirmation_v2`（P2a） | 显式 UNKNOWN 不回退、冲突 fail-closed、仅显式完成结果可回退验收通过；默认关闭 | 同上 |
| `fsdf_finish_prompt_v2`（P2b） | 仅 E 收尾提示词变化、解析与预算不变验收通过；默认关闭 | 同上 |
| `fsdf_branch_probe_v1`（P3） | 仅登记假设（B/C 输出可检查中间进展），未实现未运行 | `REGISTERED_NOT_IMPLEMENTED`；启动需新预注册与用户授权 |

官方证据基线：FSDF v1 @ `de74934`（correct 14 / incorrect 61 / invalid 37）。
上述候选的运行门槛全部未冻结（对照面口径冲突、样本量、各门阈值见
`docs/experiments/FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`），在用户
确认前不得运行真实模型实验、不得合并为组合臂、不得修改 `SUBMISSION_CONFIG`。

## 六点十一、FSDF-V2-DIAG-SMOKE-001（2026-09-05）

| 臂 | 结果（本地 native，n=30/臂） | 处置 |
|---|---|---|
| `v1`（FSDF v1 锚点） | 7 correct / 18 incorrect / 5 invalid；错误答案主要来自未确认候选回退（deep_candidate 16 题中 12 错 3 对）；native↔contract 不一致 11/30 | 同窗口诊断锚，无新处置 |
| `v2`（FSDF-RELIABILITY-V2 合并探索臂 P0+P1+P2a+P2b） | 4 correct / 2 incorrect / 24 UNKNOWN；全部 correct/incorrect 均来自显式确认来源；native↔contract 不一致 1/30；成本不变（5.0 calls） | `DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION`；合并臂不可单变量归因，正确数 7→4 与 UNKNOWN 上升均为预期交换，不判定任何门 |

60 题（冻结池 ×20/集，种子 20260905）同窗交错、workers=3、128 分钟全部完成、0 顶层
错误。跨窗口对照 SMOKE-001（v1@150 题）仅作分布参考。门槛仍未冻结，正式双轮 A/B
须按 [`experiments/FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`](experiments/FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md)
独立臂执行；本窗口不修改 `SUBMISSION_CONFIG`、不发布。完整工件：
`docs/experiments/FSDF-V2-DIAG-SMOKE-001/`。

## 六点十二、FSDF-HANDOFF-FIRST-D-DIAG-001（2026-09-05）

| 臂（n=15/臂，唯一变量=D 阶段提示词） | 结果 | 处置 |
|---|---|---|
| `v2`（合并栈，旧 DEEPEN_PROMPT） | 交接完整率 9/15；不完整时整段缺席（每题平均缺 4.5 字段，27 实例）；correct 2（均 deep_final） | 同窗诊断锚 |
| `v2hd`（同栈 + `fsdf_handoff_first_d_v1`） | 交接完整率 9/15；失效限制为单字段（仅 6 实例，管理字段全存活）；correct 2（均 E 自产 finish_final）+ incorrect 2（deep_final） | `DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION` |

核心观察（v2 按审核修正）：完整率持平但失败形态改变——旧提示"深推后总结"的不完整
样本（6 个，其中 2 个 D 正常结束 stop、4 个截断 length）整段缺席字段更严重，新提示
管理字段前置使不完整样本每题仅缺 1 个字段（含 4 个 CANDIDATE_D UNKNOWN 诚实弃答
被过滤计入）；缺字段归因（截断 vs 未输出 vs 弃答）待同题配对窗口验证。E 直接形成
确认终答的信号首次出现（2/15，仅证明终答来源于 E，n 太小仅方向性）。正确数打平，
成本口径为预算不变（nearest-rank P95：504s vs 551s，n=15 等于最大值）。E 截断近
饱和（13/15 length；v2hd 11 个 UNKNOWN 中 10 个对应 E length）是更明确的瓶颈。
测量口径待细化（trace 不区分字段缺席与 UNKNOWN 合规弃答，Issue #16 已登记）。
门槛 UNFROZEN；不修改 `SUBMISSION_CONFIG`、不发布。工件：
`docs/experiments/FSDF-HANDOFF-FIRST-D-DIAG-001/`。

## 六点十三、FSDF v2hd_dre 全栈 canary 发布（2026-09-06，用户授权）

| 项 | 内容 |
|---|---|
| 部署内容 | `SUBMISSION_CONFIG` 打开全部六个 FSDF 候选开关：P0 诊断、P1 多行交接（含未闭合条目丢弃）、P2a 终答确认、P2b E 收尾提示、`fsdf_handoff_first_d_v1`（D 交接产物优先）、`fsdf_d_result_to_e_v1`（FINAL_D_FOR_CHECK 对 E 可见） |
| 授权 | 用户 2026-09-06 明确指示"直接把新实现的功能打开，然后传到 gitcode"；等同既有 `DEPLOYED_UNVALIDATED_CANARY` 先例（hetero_k5、btcs_frame_v2） |
| 证据边界 | 零模型验收 558 项通过；两个诊断窗口（60 题、30 题）仅分布级/配对诊断，均无能力结论；本发布不追认任何预注册门通过，不构成能力提升表述 |
| 预期行为变化 | P2a fail-closed 把"错误兜底"大量转为 UNKNOWN（本地诊断窗 correct 占比 23%→13%，分布级）；换取输出卫生（native↔contract 不一致 11/30→1/30）与阶段级可归因诊断 |
| 回滚锚 | gitcode main @ `de74934`（FSDF v1 官方评测版本）；回滚即把 main 重置回该提交 |
| 后续 | 同题配对窗口 FSDF-D-RESULT-TO-E-PAIRED-001（v2hd vs v2hd_dre）运行中，其结果不改变本次发布状态 |

## 六点十四、FSDF 迭代循环（FSDF-ITER-AB 系列，2026-09-06 结束）

| 轮次 | 候选（单变量，15 题同题配对窗） | 判定 |
|---|---|---|
| 0 | `d_result_to_e`（FINAL_D 对 E 可见） | 机制未激活（D 从不输出 FINAL_D），+1=方差 |
| 1 | `de_budget_swap`（D/E 预算对调） | 净 +2 零反转 → 前移 |
| 2 | `finish_compact_final`（E 紧凑提示） | 反斥（截断未降、形成未超前沿） |
| 3 | `mandatory_final_d`（强制前置 FINAL_D） | 反斥（激活 1/15<5；D 截断 15/15 恶化） |
| 4 | `finish_handoff_share`（删选中思路块，交接 4600） | 净 +3 零反转 → 前移 |
| 5+6 | `handoff_open_first_e`（OPEN 前置渲染）+确认窗 | 两窗净 0 → 方差内，不变 |
| 7 | `finish_handoff_share_v2`（再删 A 摘要，6050） | 反斥（截断 10 vs 7；c→incorrect 反转）→ 构成假设证伪 |
| 8 | `e_budget_up`（E 8192→9728，总 +8%） | 干净反斥（截断率对预算零敏感） |
| 9 | `deep_candidate_fallback`（E 失败采纳 content 态候选） | 机制 0 触发（可转化池集中于协议失败 D），+1=方差 |
| 10 | `thinking_off`（client 级思考关闭） | 机制门决定性通过（截断消失、4.7× 提速）但分数否定（inv→inc ×7、反转 ×2、净 0） |

循环结论（v2，含迭代 11/12）：**当前前沿 `v2hd_bs_hs` 为本轮探索暂时选中的配置
（同一 15 题底座，非独立确认集；"无收益"不等于科学穷尽）**；
迭代 11（三臂）：思考关三重确认（截断全阶段消失、5.3× 提速、correct 噪声带、
incorrect 爆炸 13/15）；技能路由层 tkoff-vs-sr 净 +1 弱信号、声明机制 0 触发。
迭代 12（强制 harness）：遵从达成（11/13 完成 4/4 步骤、E 截断 0/13）但
net −2 两例反转——技能弧线结论：技能机制改变行为形态，不改变难题正确率。
12 个窗口全部同 15 题底座，非独立确认集；预算双向穷尽、
构成类穷尽、措辞/顺序/加字段类全部反斥。机制性发现：截断=思考模式在输出流内消耗
completion 预算（client 级可消除，4.7× 提速），但消除截断不带来正确率——被截断池
大部分是 fail-closed 保护住的"不会做"。全部候选默认关；前沿仅存在于迭代分支，
`SUBMISSION_CONFIG`/gitcode main 维持 canary @ `507ebd3`。完整数据：
`docs/experiments/FSDF-ITER-AB-00{1..9}, FSDF-ITER-AB-010, FSDF-D-RESULT-TO-E-PAIRED-001`；
判定轨迹：`preregistration_draft.md` §7。重启任何候选须新预注册。

## 六点十五、FESF-V1-CODE-ACCEPTANCE-001（2026-09-06）

| 候选 | 证据 | 处置 |
|---|---|---|
| `fork_evidence_synthesize_finish_v1` + `exact-evaluation` + 单题 `SolveMemory` | 零模型 focused 187 项、全量 648 项（4 skipped）通过；Skill `quick_validate` 通过；`py_compile` 与 `git diff --check` 通过；默认 `SUBMISSION_CONFIG` 保持 FSDF v1 | `CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

独立 Luna 复核首轮发现的 A 路由、claim/evidence 绑定、冲突归一化和 D 损坏 fail-closed
问题均已修复并加入回归测试；后续 Luna max 只读复核进一步检查 canonical equation 绑定、
定义域、负幂、累计资源预算和 FINAL 卫生，最终结论为 PASS。Skill 真实可用性资格门以及
Q/W1/W2 真实模型窗口按用户指示暂缓；因此本条不产生数学正确率、Skill 能力或成本结论。
运行时不加载离线错题账本，未修改默认路径、未推送发布。

## 六点十六、FESF-SKILL-EXACT-EVAL-QUAL-001（2026-09-06）

| 窗口 | 证据 | 处置 |
|---|---|---|
| Q：`fesf_v1_tkoff_exact_eval`，24 题 | 24/24 `UNKNOWN`；120 次阶段 client error；24 次 D protocol failure；任务均在约 0 秒结束 | `VOID / MODEL_ENDPOINT_BLOCKED / NO_W1_W2` |

该结果是外部模型端点/网络连通性故障，不是 Skill 资格或数学能力结果。W1/W2 按 VOID
门停止。一次网络权限重跑请求被安全审查拒绝，未再次发送题目数据。

## 六点十六、FESF-LOCAL-DEFAULT-TEST-001（2026-09-06）

| 变更 | 范围 | 处置 |
|---|---|---|
| `SUBMISSION_CONFIG.enable_fesf_v1=True`、`enable_fesf_exact_eval=True` | 用户授权的本地新体系效果测试；FSDF v1 保留为显式回退臂，未推送 GitCode | `LOCAL_EXPLORATION_ONLY / NO_CAPABILITY_CONCLUSION / NO_RELEASE` |

该开关切换只改变当前工作树的本地默认路由，不把零模型工程验收升级为数学能力证据，
也不替代真实 Q/W1/W2 资格与能力窗。

## 六点十七、FESF-SKILL-EXACT-EVAL-QUAL-001-RETRY（2026-09-06）

| 窗口 | 结果 | 处置 |
|---|---|---|
| Q retry：`fesf_v1_tkoff_exact_eval`，24 题 | 3 correct / 15 incorrect / 6 invalid；5 个 D 协议失败；5 个 Skill 工具请求均为 `UNKNOWN`；24/24 完成，平均 5 calls、67.8s | `SKILL_QUALIFICATION_NO_GO / NO_W1_W2` |

该 Q 结果不满足资格门，且外部题组未预先人工标注 Skill 适用性，不能声称选择率通过。
按预注册规则不启动 W1/W2；结果不产生 FESF 数学能力结论，也不修改默认路径或发布。

## 六点十八、FESF-SKILL-EXACT-EVAL-QUAL-006（2026-09-07）

| 窗口 | 结果 | 处置 |
|---|---|---|
| Q retry：`fesf_v1_tkoff_exact_eval`，24 题 | 8 native correct / 7 incorrect / 9 invalid；适用题选择 10/12；不适用题 NONE 12/12；产物完整率 8/10=80%；工具执行成功率 8/8=100%；可用证据被 D 消费 6/8=75%；7 次阶段协议失败（31 次 client error） | `SKILL_QUALIFICATION_NO_GO / NO_W1_W2 / NO_RELEASE` |

本轮端点可完成部分请求，但证据消费门仍低于预注册的 80%，因此不能启动 W1/W2，不能形成 Skill 数学能力结论，也不能据此提交 GitCode。随后针对 Luna max 发现的 trace 脱敏边界补丁仅属于零模型工程修复，须重新验收后才能考虑发布。

## 六点十九、FESF-SKILL-EXACT-EVAL-QUAL-007（2026-09-07）

| 窗口 | 结果 | 处置 |
|---|---|---|
| Q retry：`fesf_v1_tkoff_exact_eval`，24 题目标 | 端点重试 5 次后仍不可用；20 分钟硬停前仅完成 16/24，16/16 `UNKNOWN`；80 次 client error、16 次 D protocol failure | `VOID / MODEL_ENDPOINT_BLOCKED / NO_W1_W2 / NO_RELEASE` |

本轮只用于验证零模型 trace 脱敏修复，不产生 Skill 或数学能力结论；W1/W2 未启动，未提交 GitCode。详见 `docs/experiments/FESF-SKILL-EXACT-EVAL-QUAL-007/result.md`。

## 六点二十、FESF-V1-CODE-ACCEPTANCE-002（2026-09-07）

| 范围 | 证据 | 处置 |
|---|---|---|
| Q-007 后的零模型修复验收 | Luna max 只读复核 PASS；58 项定向测试、全量 656 项测试通过（4 skipped）；`py_compile` 与 `git diff --check` 通过 | `PASS_LUNA_MAX / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

本条只确认 trace 脱敏、Skill metadata 边界和既有 guard 未回归；不改变 Q-006 的资格 NO-GO 或 Q-007 的端点 VOID，不启动 W1/W2，不发布 GitCode。

## 六点二十一、FESF-SKILL-EXACT-EVAL-QUAL-008（2026-09-07）

| 窗口 | 结果 | 处置 |
|---|---|---|
| Q retry：`fesf_v1_tkoff_exact_eval`，24 题 | 24/24 `UNKNOWN`；120 次阶段 `model_error`、24 次 D 协议失败；无任何有效模型响应 | `VOID / MODEL_ENDPOINT_BLOCKED / NO_W1_W2 / NO_RELEASE` |

Q-008 与 Q-007 的端点故障模式一致，不能估计 Skill 资格指标；W1/W2 未启动，未提交 GitCode。详见 `docs/experiments/FESF-SKILL-EXACT-EVAL-QUAL-008/result.md`。

## 六点二十二、HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-001（2026-09-07）

| 范围 | 证据 | 处置 |
|---|---|---|
| Host intake、bounded obligation、三个 verifier adapter、离线错题本、opt-in FESF bridge | 本地 F0–F5 硬门通过：55 个 intake/obligation case、96 个 verifier oracle、300 fuzz、定向 253 / 全量 697 测试、零远程调用、默认开关关闭 | 本地门不能单独晋升。独立复核 P0：复合分母上 false `EXACT`。整窗 `NO_GO / DEFAULT_OFF / ZERO_REMOTE_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

不得把本窗表述为代码验收通过，不得打开 `enable_host_intake` /
`enable_bounded_obligation_extractor`，不得把 verifier 接入默认路径。修复定义域
假设后必须新建 `...-001-RETRY` 并重新冻结 hash。工件：
`docs/experiments/HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-001/`。

后续独立重冻均为 `NO_GO / DEFAULT_OFF / ZERO_REMOTE_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`：

| 窗口 | 关闭的旧 finding | 新否决 |
|---|---|---|
| `...-001-RETRY` | adapter 复合分母 false `EXACT` | P1：`(x-1)/(x-1)` 被标 `COVERED` |
| `...-001-RETRY2` | 复合分母 `COVERED` | P1：`max != 0` 子串覆盖 `1/x` |
| `...-001-RETRY3` | 标识符子串 `COVERED` | P0：`x**(0-1)` false `EXACT`；P1：`x != 0.5` 覆盖 `1/x` |
| `...-001-RETRY4` | 计算型负幂 EXACT 与 ASCII `0.5` 前缀 | P1：`0点5` / 全角小数仍覆盖 `1/x` |

RETRY4 是 2026-09-07 的停止点：本地 F0–F5 通过，工程测试通过，独立复核 P1，总体 `NO_GO`，默认路径未启用，远程模型调用 0，不发布、不提交 GitCode。继续给 `_NONZERO_RE` 补 Unicode 例外不能形成稳定验收边界。

下一轮只允许一次结构性修复：把非零断言收成白名单全文匹配（`x != 0` / `x ≠ 0` / `x 非零`），然后只开一个受控窗 `HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-RETRY5`。不得改 verifier、bridge、错题本或实验门槛。若 RETRY5 仍有 P1，不再开 RETRY6，撤销自动 `COVERED`，符号分母全部默认 `OPEN`。决策全文见根目录 `DEVLOG.md`。

工件：`docs/experiments/HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-001-RETRY{,2,3,4}/`。

## 六点二十三、HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-RETRY5（2026-09-07）

| 范围 | 证据 | 处置 |
|---|---|---|
| 严格白名单非零断言，单次受控重试 | 本地 F0–F5 通过：75 intake/obligation、109 oracle、300 fuzz、定向 255 / 全量 699；独立复核无新 P0，P1：`x*y != 0` 覆盖 `1/y` | `NO_GO / DEFAULT_OFF / ZERO_REMOTE_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

不再开 RETRY6。自动 COVERED 已撤销，符号分母义务一律 `OPEN`。默认开关未启用，未发布。下一步是 claim DSL，不是继续补文本匹配。工件：`docs/experiments/HOST-LOOP-FOUNDATIONS-CODE-ACCEPTANCE-RETRY5/`。

Host Loop 基础件当前内部状态为
`SAFE_DEGRADED / DEFAULT_OFF / NO_CAPABILITY_CONCLUSION`：intake 与关键词义务抽取可用但默认关闭；符号分母不自动 COVERED；三类 verifier 独立存在尚未在线接入；错题本离线存在；默认提交路径未改变。不得把 RETRY 系列失败表述为整个 Host Loop 失败，也不得继续 foundations 全绿追逐。

## 六点二十四、FESF-CLAIM-DSL-CODE-ACCEPTANCE-001（2026-09-07）

| 范围 | 证据 | 处置 |
|---|---|---|
| Claim DSL parser / binding / evidence ledger / adapter 调用 | 定向 71、全量 709（4 skipped）；`py_compile` 与 `git diff --check` 通过；默认路径不导入 DSL；探针无 false EXACT/REFUTED、无 UNKNOWN 升级、无错绑 | `CLAIM_DSL_CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

Terra medium 复核因额度不可用；探针清单由本会话只读执行。未接入 FESF，未改 `SUBMISSION_CONFIG`，未发布。下一窗才是独立开关 `enable_fesf_claim_dsl` 的 opt-in 接入验收。工件：`docs/experiments/FESF-CLAIM-DSL-CODE-ACCEPTANCE-001/`。

## 六点二十五、FESF-CLAIM-DSL-INTEGRATION-CODE-ACCEPTANCE-001（2026-09-07）

| 范围 | 证据 | 处置 |
|---|---|---|
| Claim DSL opt-in 接入 FESF | 定向 228、全量 716（4 skipped）；默认关闭预算/终答不变；lazy import；错误绑定 fail-closed | `CLAIM_DSL_INTEGRATION_CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

`SUBMISSION_CONFIG.enable_fesf_claim_dsl` 保持 False。未启动真实模型资格窗、W1/W2 或 GitCode 发布。符号分母仍为 OPEN。工件：`docs/experiments/FESF-CLAIM-DSL-INTEGRATION-CODE-ACCEPTANCE-001/`。

## 六点二十六、FESF-CLAIM-DSL-QUAL-001（2026-09-07）

| 窗口 | 结果 | 处置 |
|---|---|---|
| 健康探针 3 次 + 24 题 `fesf_v1_tkoff_claim_dsl` | 探针 3/3 ok；资格窗顶层 0 model_error，但 84 次阶段 HTTP/timeout，C 失败 16/24，Claim DSL 事件 0 | `VOID / STAGE_ENDPOINT_UNHEALTHY / NO_W1_W2 / NO_CAPABILITY_CONCLUSION` |

机制未激活，不能估计绑定率或错误证据。不启动能力窗，不发布。工件：`docs/experiments/FESF-CLAIM-DSL-QUAL-001/`。

## 六点二十七、FESF 官方 NO_GO 与 FSDF v1 前向回退（2026-09-08）

| 提交/路径 | 官方证据 | 处置 |
|---|---|---|
| `921afad`：FESF v1 + exact eval + Claim DSL + 临时答案路由 | 112 题：2 correct / 1 incorrect / 109 invalid；541 次生成请求中 452 次截断（约 83.5%）；总 token 2,014,135；runner completed；墙钟约 7 小时 22 分 | `OFFICIAL_NO_GO / TRUNCATION_AND_TIME_GATE_FAIL / NO_INCREMENTAL_RETRY` |
| FSDF v1 回退路径 | 已有官方锚 `de74934`：14 correct；本次只做前向配置回退，不删除后续实现 | `RESTORED_BASELINE` |

附件无逐题 trace，因此不能精确拆分 109 个 invalid 的来源；大量截断与 FESF 的严格协议、
候选闸门和 fail-closed 行为一致，但属于机制解释而非逐题证明。官方公开 client 不提供可由
`ReasoningAgent` 可靠控制的 thinking 开关，后续正式路径不得依赖本地 `thinking_mode=False`。

回退配置只启用 `enable_fork_select_deepen_finish=True`。FESF、exact eval、Claim DSL、Host
intake、bounded obligation、临时答案路由和所有 FSDF v2/迦代候选均关闭；代码保留供显式
实验配置使用。

## 六点二十八、CAR-001-ADAPTIVE-CANDIDATE-FIRST（2026-09-08）

| 候选 | 当前状态 | 处置 |
|---|---|---|
| `car_001`：thinking-on 自适应候选优先 | 已完成架构质询与预注册；F0–F3 尚未运行；默认配置未改 | `OPEN / PREREGISTERED_NOT_RUN / NO_CAPABILITY_CONCLUSION` |

设计为“1 次短候选 → 条件第 2 候选 → 至多 1 次短裁决/恢复”，单题最多 3 次调用、
2048/2048/4096、软/硬截止 10/15 分钟；首版单题内部串行，仅 runner 3 workers 交错。
候选冲突保留双方，先做有限规范化/精确等价/数值检查，无法判定再短裁决。skill 只作
软建议，verifier/Claim DSL 只作 shadow；本地错题本可沉淀，正式评测只能读冻结版本，
运行期间不得写回。完整规格见 `docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-SPEC/`。

RPM=200、TPM=2M 只用于缩短交错实验和提高吞吐，不放宽单题 20 分钟、整轮 6 小时或
单题调用/token 上限。F0 零模型门通过后依次执行 F1（6+6 健康）、F2（24 配对探索）、
F3（48 fresh A/B）；每窗先判 VOID，再判能力/卫生/成本。不得把本登记视为数学能力
通过、官方候选或 `SUBMISSION_CONFIG` 修改授权。

## 六点二十九、CAR-001 F0 代码门（2026-09-08）

| 范围 | 证据 | 处置 |
|---|---|---|
| `adaptive_candidate_first_v1` 宿主 relay、候选解析、恢复/裁决上限、互斥路由与 trace 卫生 | 12 项定向测试通过；全量 736 项中 732 通过、4 skipped；`py_compile` 与 `git diff --check` 通过；零真实模型调用 | `CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION` |

F0 只确认代码契约。F1 仍需使用 thinking-on 官方默认 client 做 baseline/CAR 各 6 题健康
探针；F2/F3 未启动。CAR 不得写入 `SUBMISSION_CONFIG`，不自动提交或推送 GitCode。
完整工件见 `docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-SPEC/` 的
`result.md`、`report.json` 与 `run_manifest.json`。

## 六点三十、CAR-001 F1 thinking-on 健康探针（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-001`：FSDF v1 vs CAR-001，6 题配对、3 workers | 12/12 任务完成，但两臂均无成功模型响应；FSDF 6/6、CAR 6/6 在阶段调用中出现 connectivity/ConnectionError | `VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION` |

初始 runner 把 fail-closed `UNKNOWN` 误记为顶层 `status=ok`，已依据逐题 stage trace 重分类并
修复统计器；修复没有追加模型调用。`finish_reason`/completion token 为空，不产生截断或正确率结论。
按停止规则不启动 F2/F3；端点恢复后只能用修复后的 runner 开新编号健康窗。工件见
`docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-001/`。

## 六点三十一、CAR-001 F1-002 thinking-on 健康探针（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-002`：FSDF v1 vs CAR-001，6 题配对、3 workers | 12/12 任务完成；FSDF 6/6、CAR 4/6 至少一个阶段 timeout；总耗时约 1771 秒 | `VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION` |

端点已可间歇返回成功响应（FSDF 5/6、CAR 5/6 至少有成功阶段；CAR 2/6 任务完整返回），
但阶段级超时率超过预注册健康门；部分成功响应仍有 `finish_reason=length`。thinking 保持
官方默认，不能据此得出截断、正确率或 CAR 能力结论。F1-002 的失败集中在健康/延迟层，
不启动 F2；后续必须先做单请求或更小 probe，再新编号 F1。工件见
`docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-002/`。

## 六点三十二、CAR-001 恢复 probe（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-001-ADAPTIVE-CANDIDATE-FIRST-RECOVERY-PROBE-001`：idx 6000，FSDF v1 vs CAR-001 | 最小请求约 0.81s 成功；CAR 1 次调用约 112s、无阶段错误；FSDF A/B/C 成功但 D/E timeout、总耗时约 542s | `PARTIAL_RECOVERY / DO_NOT_REOPEN_F1 / NO_CAPABILITY_CONCLUSION` |

端点已从完全连接失败恢复为可间歇响应，但 thinking-on 阶段延迟仍不稳定，FSDF 基线
未通过单题健康条件。不能据此重开 F1-003 或进入 F2；后续若端点持续稳定，需新编号
probe/F1，并使用修复后的 runner。工件见
`docs/experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-RECOVERY-PROBE-001/`。

## 六点三十三、CAR-001 F1-003 完整窗口（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-003`：6+6、3 workers | 运行约 23.5 分钟后人工安全终止；当时脚本尚未写入逐题结果 | `VOID / MANUAL_HARD_STOP / NO_DURABLE_TASK_RECORDS / NO_CAPABILITY_CONCLUSION` |

本窗不推断任何模型结果，也不进入 F2。后续若继续，必须先为 runner 增加全局硬截止并
让已完成任务增量落盘，再新编号预注册；不得重复相同的无界批量窗口。

## 六点三十四、CAR-001 F1-004 完整窗口（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-001-ADAPTIVE-CANDIDATE-FIRST-F1-HEALTH-004`：6+6、3 workers、window hard-stop 1200s | 12/12 任务约 942 秒完成；FSDF 6/6、CAR 2/6 至少一个阶段 timeout；所有任务有 durable records | `VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION` |

本窗没有触发 partial hard stop，但确认启动即写 manifest/report、bounded active futures、
增量 checkpoint 和 F1 fail-fast 均生效。CAR 平均调用约 1.83、FSDF 5.0；这是健康/成本
观察，不是能力结论。按错误率门不启动 F2；后续若继续必须重新做请求级 probe，并新编号
窗口，不得修改默认配置。

## 六点三十五、POST-MAIN-EVAL-001（2026-09-08）

| 窗口 | 结果 | 处置 |
|---|---|---|
| GitCode `main` @ `bd16a3f`，OlymMATH/AIME/HLE 各 1 题，FSDF v1、thinking-on 默认 | 1 correct / 0 incorrect / 2 invalid；平均 5 次调用、445.5s；阶段级 client error 5 次 | `LOCAL_SMOKE_ONLY / NO_CAPABILITY_CONCLUSION` |

本地近似判定为 33.33%，native/contract 一致；两道 invalid 均为 D/E timeout 后的
fail-closed UNKNOWN。该 3 题 smoke 不是赛事隐藏集成绩，不修改默认配置；完整记录见
`docs/experiments/POST-MAIN-EVAL-001/`。

## 六点三十六、CAR-002-DUAL-CANDIDATE-CONSENSUS（2026-09-08）

| 候选 | 当前状态 | 处置 |
|---|---|---|
| `adaptive_dual_candidate_consensus_v1` | 规格已确认；P1/P2 最小实现与零模型代码门已通过；P3+ 未运行；默认配置未改 | `OPEN / CODE_ACCEPTED / NOT_RUN / NO_CAPABILITY_CONCLUSION` |

CAR-002 相对 CAR-001 的唯一机制增量是：对短终答适用题，在首个合法候选形成后仍强制生成
互盲候选 B；A/B 可证明等价时返回，否则最多一次短裁决。能力、健康、hard smoke 和正式
A/B 均硬性关闭 `temporary_answer_bank`；submission simulation 与经另行授权的线上配置保持
答案库开启，两种 accuracy 必须分栏。首版不加入 Python/SymPy 在线选择、领域 router、并行
模型调用或策略注册表重构。完整计划见
`docs/experiments/CAR-002-DUAL-CANDIDATE-CONSENSUS-SPEC/preregistration.md`。

执行顺序固定为零模型门 → 资源 preflight/健康窗 → fresh hard10 机制 smoke → 重验
`external70_v1` → `confirm30_v2` → submission simulation → 另行授权晋升。任一健康/能力门失败
即停止，不自动修改 prompt、预算、默认配置或追加同协议样本。本登记不授权真实模型调用、
代码实现、commit、push 或官方提交。
本次仅完成用户明确授权的代码实现与零模型验收；未启动真实模型窗口、未修改默认配置、未 commit/push。

## 六点三十七、CAR-002-CODE-ACCEPTANCE-REVERIFY（2026-09-08）

原始 `CAR-002-DUAL-CANDIDATE-CONSENSUS-CODE-ACCEPTANCE-001` 工件保留不覆盖；独立复验发现
路径互斥、P3b 对照臂/健康门、report 实际配置和补充证据缺口，建议状态为
`P1_IMPLEMENTED_PARTIAL / P2_NO_GO / P3_BLOCKED / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`。

修正后新建 `CAR-002-DUAL-CANDIDATE-CONSENSUS-CODE-ACCEPTANCE-002`，完成零模型复验：
定向 214/214，全量 763 total（759 passed、4 skipped），并记录五个源文件的 Git blob 与
SHA-256。该复验仍只产生 `CODE_ACCEPTED / NO_CAPABILITY_CONCLUSION`，不解除 P3 阻断。

## 六点三十八、CAR-002-P3-RESOURCE-QUALIFICATION（2026-09-09）

| 阶段 | 结果 | 处置 |
|---|---|---|
| P3a 单请求 preflight | 3/3 成功，0 timeout，0 client error，最大延迟 6.774s | `PASS / NO_CAPABILITY_CONCLUSION` |
| P3b `car_001 vs car_002` 健康窗 | 12/12 durable records；两臂 0 阶段错误；CAR-002 B 6/6 尝试、5/6 有效；约 419s | `P3_HEALTH_PASS / NO_CAPABILITY_CONCLUSION` |

P3 仅证明资源与协议健康，不提供能力正确率。P3 工件见
`docs/experiments/CAR-002-DUAL-CANDIDATE-CONSENSUS-P3A-PREFLIGHT-001/` 与
`docs/experiments/CAR-002-DUAL-CANDIDATE-CONSENSUS-P3B-HEALTH-001/`。

## 六点三十九、CAR-002-P4-FRESH-HARD10（2026-09-09）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-002-DUAL-CANDIDATE-CONSENSUS-HARD10-001`：MathArena AIME 2026 fresh hard10，`car_001 vs car_002` | 20/20 记录；0 模型错误；CAR-002 B 10/10 尝试、2/10 有效；Oracle@2=2/10；等价 pair=1；paired `b=0,c=3`；约 1349s | `VOID / NO_GO / NO_P5 / NO_CAPABILITY_CONCLUSION` |

本窗满足记录完整、健康、B 尝试率、单题与窗口时限门，但失败于 CAR-002 有效 B、
Oracle@2、等价 pair 数和 paired 净值门。按停止规则不运行 P5，不在同一 hard10 上调 prompt、
补跑或改预算。`external70_v1` 与 `hard15` registry 当前 checkout 仍缺失，隔离核验保持未核项。
工件见 `docs/experiments/CAR-002-DUAL-CANDIDATE-CONSENSUS-HARD10-001/`。

## 六点四十、CAR-002B-CANDIDATE-FORMAT-SMOKE（2026-09-09）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-002B-CANDIDATE-FORMAT-SMOKE-001`：新冻结 set_b AIME 2024 short-answer smoke，`car_001 vs car_002b_format_first` | 20/20 durable records；答案库关闭；B 10/10 尝试、2/10 有效；B 10/10 `finish_reason=length`；8/10 无 `CANDIDATE` 标记；2 个阶段 timeout；Oracle@2=5/10；等价 pair=0；paired `b=0,c=2`；约 1720s | `NO_GO / NO_P5 / NO_CAPABILITY_CONCLUSION` |

该窗只改变了候选 system prompt 的 format-first 变量，未放宽 parser、未改变预算或静态
hint。诊断表明主失败是模型在 2048 completion 上限前没有形成 `CANDIDATE` 标记，
不是已确认的括号、超长值或多标记 parser 误拒。不得在同一 10 题上继续调 prompt 或补跑，
不得进入 P5；若继续，必须提出新的可归因假设、新冻结集和新编号。工件见
`docs/experiments/CAR-002B-CANDIDATE-FORMAT-SMOKE-001/`。

## 六点四十一、CAR-002C-ENDPOINT-COMPATIBILITY-PROBE（2026-09-09）

| 窗口 | 结果 | 处置 |
|---|---|---|
| `CAR-002C-ENDPOINT-COMPATIBILITY-PROBE-001`：新冻结 OlymMATH English hard10，终答 marker 兼容性探针 | 10/10 请求完成；0 model error；10/10 `finish_reason=length`；CANDIDATE/FINAL/最终答案 marker 均 0；唯一结构完整终答 0/10；10 次调用 | `ARCHIVED / NO_GO / NO_P5 / NO_CAPABILITY_CONCLUSION` |

该探针未发现可用的显式终答协议，说明当前 thinking-on 端点在 2048 completion 上限下的
可见终答形成能力不足。CAR-002 方向停止，不建立 CAR-002C，不复跑 P4/P4B，不放宽
parser，不进入 P5，不修改默认配置。工件见
`docs/experiments/CAR-002C-ENDPOINT-COMPATIBILITY-PROBE-001/`。

## 六点四十三、FSDF-HEALTH-RECOVERY-001（2026-09-09）

| 窗口 | 结果 | 处置 |
| --- | --- | --- |
| 新冻结 12 题、单臂 FSDF v1、3 workers、2400s hard stop | P0 通过；P2 3/3 成功；P3 12/12 durable、0 top-level error、0 skip、0 client error、2 protocol failures、2/60 stage failures | `HEALTH_PASS / NO_CAPABILITY_CONCLUSION / NO_BUDGET_DECISION` |

该窗只证明 FSDF v1 五阶段在扩大后的窗口容量下具备资源/协议健康；未运行 budget-swap arm，
未使用 correct/invalid/截断数据，未进入 P4/P5。该健康结果不授权直接重跑 budget swap；
是否创建新的 budget-swap 预注册需另行决定。完整工件见
`docs/experiments/FSDF-HEALTH-RECOVERY-001/`。

## 六点四十四、FSDF-DE-BUDGET-SWAP-CONFIRM-002（2026-09-09）

| 方案 | 状态 | 处置 |
| --- | --- | --- |
| `fsdf_de_budget_swap_confirm_v2`：新 P0、P2、两臂 P3 健康窗后再进入 fresh hard10 | `VOID / P3_HEALTH_UNHEALTHY / NO_P4 / NO_CAPABILITY_CONCLUSION` | P0/P2 通过；两臂 6/6 durable、0 skip、0 top-level error；baseline `4/30`（4 client error），candidate `9/30`（5 client error、4 protocol failure），2400s 未触发 |

该方案不是旧 `FSDF-DE-BUDGET-SWAP-CONFIRM-001` 的重跑。健康恢复窗的 2 个 protocol failures
仅作为诊断背景，不进入预算/能力证据。P3 失败后未进入 P4/P5。完整规格与结果见
`docs/experiments/FSDF-DE-BUDGET-SWAP-CONFIRM-002-SPEC/preregistration.md` 和
`docs/experiments/FSDF-DE-BUDGET-SWAP-CONFIRM-002/`；默认配置保持不变。

### 系列收束

`FSDF-ITER-AB-001` 的历史正向信号属于含 v2 组件的诊断窗口；纯 v1 budget-swap 确认
窗口 `CONFIRM-001` 因容量型 health failure 作废，`HEALTH-RECOVERY-001` 只证明单臂
FSDF v1 在扩大窗口后可运行，`CONFIRM-002` 在双臂无 skip 的条件下仍以 baseline
`4/30`、candidate `9/30` stage failures 失败。系列最终状态为
`ARCHIVED_VOID / HEALTH_PROTOCOL_NO_GO / NO_CAPABILITY_CONCLUSION`；不再对同一预算
变量追加 P3/P4/P5。未来若重启，必须提出新的协议机制假设、新 method ID 和新冻结证据。

## 六点四十二、FSDF-DE-BUDGET-SWAP-CONFIRM-001（2026-09-09）

| 窗口 | 结果 | 处置 |
| --- | --- | --- |
| 纯 FSDF v1、答案库关闭、D/E `8192/4096` vs `4096/8192`；P2 3 次 preflight、P3 6+6 健康窗 | P0 代码门通过；P2 3/3 成功；P3 12/12 durable records，但 baseline/candidate stage-slot failures 为 15/30 与 17/30，candidate 含 3 client error、4 protocol failure | `VOID / P3_HEALTH_UNHEALTHY / NO_P4 / NO_CAPABILITY_CONCLUSION` |

该窗口因 P3 健康门失败按预注册停止，未启动 fresh hard10、`external70_v1` 或 confirm30；不产生预算交换的数学能力结论，不修改 `SUBMISSION_CONFIG`，不提交或发布。完整工件见
`docs/experiments/FSDF-DE-BUDGET-SWAP-CONFIRM-001/`。后续若重启，必须提出新的健康假设与新编号，不能在本窗口上补跑或挑选指标晋升。

## 六点四十七、MATH-HARNESS-V1 FIT-AUDIT 与 CODE-ACCEPTANCE（2026-09-10）

| 阶段 | 结果 | 处置 |
| --- | --- | --- |
| `MATH-HARNESS-FIT-AUDIT-001` | 公开 client、官方构造、3-worker/20-minute 约束、bank 隔离、状态/预算账本、fail-closed、trace 卫生和 FSDF legacy 边界完成审计；0 远程模型调用 | `FIT_PASS / NO_CAPABILITY_CONCLUSION` |
| `MATH-HARNESS-CODE-ACCEPTANCE-001` | Harness 相关 249 项回归、`py_compile`、官方 client/ReasoningAgent 构造 smoke 和最小 solve 契约通过；0 远程模型调用 | `CODE_ACCEPTED_TARGETED_SCOPE / NO_CAPABILITY_CONCLUSION` |

全量 discover 仍受仓库既有 `tests/test_causal_demo.py` 对未声明依赖 `mcp` 的导入阻断，未被
纳入 Harness gate；没有通过扩大 `requirements.txt` 来掩盖该环境问题。新 Harness、typed
tools、hybrid router 和答案库的默认提交路径均未打开，`SUBMISSION_CONFIG`、main、远程仓库
和赛事提交均未修改。完整工件见
`docs/experiments/MATH-HARNESS-FIT-AUDIT-001/` 与
`docs/experiments/MATH-HARNESS-CODE-ACCEPTANCE-001/`。

下一步只能按 Issue #17 冻结顺序进入 endpoint preflight；该阶段需要用户/端点授权，不能用
本地 scripted client 结果替代真实端点健康或能力证据。

## 六点四十八、MATH-HARNESS-ENDPOINT-PREFLIGHT-001（2026-09-10）

| 阶段 | 结果 | 处置 |
| --- | --- | --- |
| `MATH-HARNESS-ENDPOINT-PREFLIGHT-001` | 新来源 AIME 题集；bank-off；official-default thinking；每题单次普通自由格式请求，`max_tokens=4096`；已记录 3/10 请求，其中 2 次 600 秒 timeout；唯一可抽取候选 1/10，低于 8/10 门槛 | `ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION` |

该窗没有要求 `CANDIDATE`/`FINAL` marker，也没有保存完整 response；3 次真实端点调用均计入记录。第 2 次 timeout 已使预检不可通过，按停止规则提前收口，未启动 `MATH-HARNESS-HEALTH-001`、机制 A/B 或能力 A/B。Harness 不进入默认路径，FSDF 保持 legacy/线上回滚路径。完整工件见
`docs/experiments/MATH-HARNESS-ENDPOINT-PREFLIGHT-001/`。

## 六点四十九、MATH-HARNESS-ENDPOINT-PREFLIGHT-002（2026-09-10）

| 阶段 | 结果 | 处置 |
| --- | --- | --- |
| `MATH-HARNESS-ENDPOINT-PREFLIGHT-002` | 对 001 的一次独立、有限重试；完整抽取请求已记录 5/10，其中 1 次 600 秒 timeout、1 次 `finish_reason=length` 且无候选；唯一可抽取候选 3/10，低于 8/10 门槛 | `ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION` |

该结果确认当前 official-default thinking 端点在本 Harness 的普通复杂题请求上仍不满足预检健康/抽取条件；不再重试，不进入 `MATH-HARNESS-HEALTH-001`、机制 A/B 或能力 A/B。默认路径继续保持 FSDF，完整工件见
`docs/experiments/MATH-HARNESS-ENDPOINT-PREFLIGHT-002/`。

## 六点五十、MATH-ENDPOINT-DIRECT-PROBE-001（2026-09-10）

| 诊断 | 结果 | 解释 |
| --- | --- | --- |
| 裸 `InternChatClient.chat` 直连当前端点 | 纯文本 3/3、基础 `1+1` 3/3 成功；0 timeout、0 client error；平均延迟 5.633 秒，最大 8.497 秒 | 简单请求的本地 client 与远程端点链路正常 |

该诊断绕过 `ReasoningAgent`、Constraint-Fit Harness、HostParser 和答案库，仅使用公开
`client.chat(messages, temperature, max_tokens)`。结合 `MATH-HARNESS-ENDPOINT-PREFLIGHT-001/002`
中复杂题分别出现 600 秒 timeout，当前最合理的定位是远程服务在复杂 thinking 请求上的推理/排队长尾，
而不是本地 parser 或 Harness 计算；仍无法仅凭客户端数据区分模型服务、网关排队或中间网络设备。
该诊断不产生数学能力结论，不修改默认路径。完整工件见
`docs/experiments/MATH-ENDPOINT-DIRECT-PROBE-001/`。

## 六点五十一、MATH-HARNESS-112-DIAGNOSTIC-001~005（2026-09-10）

| 窗口 | 结果 | 处置 |
| --- | --- | --- |
| `MATH-HARNESS-112-DIAGNOSTIC-001` | 用户授权的 bank-off 112 题诊断；23/112 后因候选边界问题停止，1 correct、22 invalid、0 model error | `DIAGNOSTIC_STOPPED / NO_CAPABILITY_CONCLUSION` |
| `MATH-HARNESS-112-DIAGNOSTIC-002` | RHS 规范化校正窗；2/112 后发现数学定界符残留并停止，0 correct、2 invalid | `DIAGNOSTIC_STOPPED / NO_CAPABILITY_CONCLUSION` |
| `MATH-HARNESS-112-DIAGNOSTIC-003` | 统一 scalar RHS 入口校正；18/112，8 correct、1 incorrect、9 invalid、0 model error | `DIAGNOSTIC_STOPPED / NO_CAPABILITY_CONCLUSION` |
| `MATH-HARNESS-112-DIAGNOSTIC-004` | 数学定界符校正；7/112，6 correct、1 invalid、0 model error | `DIAGNOSTIC_STOPPED / NO_CAPABILITY_CONCLUSION` |
| `MATH-HARNESS-112-DIAGNOSTIC-005` | 完成 112/112；60 correct、2 incorrect、50 invalid、0 model error、0 timeout；候选形成 101/112；184 次逻辑调用 | `DIAGNOSTIC_COMPLETE / NO_CAPABILITY_CONCLUSION` |

005 的全体题准确率为 60/112（53.57%），已判定题准确率为 60/62（96.77%）；平均调用
1.643、P95 调用 4、请求 token 661504、平均/P95/最大耗时 35.22/114.26/212.22 秒。
实际 completion token 与 finish reason 未通过公开 `client.chat` 字符串契约提供，分别记录为
unknown/missing。112 题仅是公开 regression/calculation 诊断，不能解除 endpoint preflight
NO_GO、不能替代 HEALTH/机制 A/B/能力 A/B，且未修改 `SUBMISSION_CONFIG` 或默认 FSDF 路径。
完整工件见 `docs/experiments/MATH-HARNESS-112-DIAGNOSTIC-001/` 至
`docs/experiments/MATH-HARNESS-112-DIAGNOSTIC-005/`。

## 六点五十二、MATH-HARNESS-EVAL112-SMOKE-001（2026-09-10）

| 窗口 | 结果 | 处置 |
| --- | --- | --- |
| `MATH-HARNESS-EVAL112-SMOKE-001` | 团队自建 `eval_112.json` 前 10 题；最新 Harness、3 workers、bank-off；10/10 记录；0 correct、0 incorrect、10 invalid；0 model error、0 timeout；19 次远程逻辑调用 | `SMOKE_COMPLETE / NO_CAPABILITY_CONCLUSION` |

该 smoke 完整验证了 10 题路径，但未形成可判分答案；其中 9 题形成候选，候选多为未完成
推导、复杂表达式或非标量结论，另 1 题无候选。按用户设定不再扩大测试。gold 只在宿主
侧评分，不进入 Agent；`temporary_answer_bank` 全程关闭。该结果不是官方成绩，不解除
Harness endpoint preflight NO_GO，也不修改默认配置。完整工件见
`docs/experiments/MATH-HARNESS-EVAL112-SMOKE-001/`。

## 六点五十三、MATH-CONTRACT-ROUTER-CODE-001（2026-09-10）

| 阶段 | 结果 | 处置 |
| --- | --- | --- |
| 双轴 `ProblemContract` / Router 零模型代码门 | 11 个 contract case、231 项 Harness/UserAgent/Deep/formation-runner 回归通过；direct/deep 分离、typed answer shape、低置信 mixed 回退和 metadata 隔离通过；0 远程调用 | `CODE_ACCEPTED_DEFAULT_OFF / NO_CAPABILITY_CONCLUSION` |

该门只验收路由契约，不实现 Deep 执行或真实模型形成；`SUBMISSION_CONFIG`、FSDF 和原 bounded
lane 未改变。下一步按新 spec 进入 `MATH-TYPED-PARSER-CODE-001`，必须先完成七个原 smoke
非 `UNKNOWN` 输出的负例回归。工件见 `docs/experiments/MATH-CONTRACT-ROUTER-CODE-001/`。

## 六点五十四、MATH-TYPED-PARSER-CODE-001（2026-09-10）

| 阶段 | 结果 | 处置 |
| --- | --- | --- |
| typed parser 零模型代码门 | 六类正例 6/6 `typed_complete`；原 smoke 七类非 UNKNOWN 负例 0/7 被误接收；相关 Harness/UserAgent/Deep/formation-runner 回归 231 项通过；0 远程调用 | `CODE_ACCEPTED_DEFAULT_OFF / NO_CAPABILITY_CONCLUSION` |

该门只确认 typed completeness 能区分完整答案、推导片段、截断和结构不匹配，不产生数学
能力结论。下一步按新 spec 进入 `MATH-DEEP-FORMATION-PROBE-001`；必须使用 fresh 6 题、
bank-off，并执行前三题 typed-complete=0 的立即停止门。工件见
`docs/experiments/MATH-TYPED-PARSER-CODE-001/`。

## 六点五十五、MATH-DEEP-FORMATION-PROBE-001（2026-09-10）

| 窗口 | 结果 | 处置 |
| --- | --- | --- |
| Deep typed-answer formation | fresh 公开 OlymMATH 题首 3/6；3/3 `deep_primary` 在固定 1200 秒单题边界 timeout；typed-complete 0/6；0 次 review/continuation/critic；bank-off、3 workers | `NO_GO / NO_CAPABILITY_CONCLUSION` |

前三题均无 model 返回，故立即触发预注册的 `first_three_typed_complete_zero` 停止门，
后三题未发请求。每题只发出 1 次 `deep_primary`，请求 8192 tokens；没有答案库命中、
没有 route violation，输出仍保持非空 `UNKNOWN` 契约。该结果证明本窗的 Deep formation
健康门未通过；它不能区分远程模型推理、服务排队或网关层 timeout，也不产生数学能力
结论。按 spec 不启动 `MATH-DEEP-TRAJECTORY-SMOKE-001`、Deep ability A/B、Hybrid 或
submission promotion。完整工件见 `docs/experiments/MATH-DEEP-FORMATION-PROBE-001/`。

## 六点五十六、MATH-HARNESS-SUBMISSION-OVERRIDE（2026-09-11）

用户明确授权将 Constraint-Fit Harness、Deep lane、FSDF hybrid fallback 与
`temporary_answer_bank` 开启并提交到远端。该配置覆盖 formation 的 `NO_GO` 结论，
但不把 formation 失败转化为能力通过，也不补写 trajectory/ability A/B 证据；提交
profile 的 bank 命中与模型路径仍须分开解读。当前配置为：Harness=on、Deep=on、
hybrid=on、bank=on。该项是显式发布授权，不是实验晋升结论。

## 六点四十六、COD-NUMERIC-QUAL-001（2026-09-09）

| 候选 | 结果 | 处置 |
|---|---|---|
| `current_cod_numeric` vs `current_c0` | C0/legacy clean path；10 个新 OlymMATH numeric + 3 个非数值 parity；13/13 每臂 durable、0 任务 skip、0 顶层错误；P1 3/3 通过 | `ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION` |

CoD candidate 的 numeric native correct 为 `0/10`，baseline 为 `1/10`，出现 1 个
`correct→incorrect`；平均 completion token 为 baseline 的约 102.0%，P95 wall-clock
为约 119.4%，未达到预注册的 60% token / 70% 时延目标。`invalid + error` 未增加，
native/contract 在本窗一致；这些均为本地 smoke 证据，不是官方能力结论。

按停止规则不启动第二轮 A/B，不调 CoD prompt，不接入 FSDF，不修改
`SUBMISSION_CONFIG`。若继续探索低成本路线，必须另立 `Re2` 的新 method ID、预注册和
冻结题组；不得与 CoD 并行运行。完整工件见
`docs/experiments/COD-NUMERIC-QUAL-001/`。

## 六点四十五、FSDF-PROTOCOL-STABILITY-QUAL-001（2026-09-09）

| 臂 | 结果 | 处置 |
|---|---|---|
| `fsdf_protocol_v1` vs `fsdf_multiline_handoff_v2` | 新冻结 OlymMATH hard10、同题 paired、10/10 每臂 durable、0 skip、0 顶层错误；v1 阶段 timeout 4、candidate 阶段 timeout 5 + D protocol failure 2 | `DIAGNOSTIC_ONLY / HEALTH_NOT_CLEAR / NO_CAPABILITY_CONCLUSION` |

两臂均 5 calls、E `finish_reason=length` 10/10。candidate D→E 缺失事件 7/10（v1 4/10），E 终答形成 3/10（v1 7/10）；candidate 的两个协议失败均为 D `invalid_response`。native/contract 为本地近似判定，不能作为官方能力结论。按健康优先停止，不启动 fresh hard/能力窗口，不在同一题组调 Prompt、补跑或晋升。完整工件见
`docs/experiments/FSDF-PROTOCOL-STABILITY-QUAL-001/`。
