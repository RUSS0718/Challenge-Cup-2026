# FSDF-HANDOFF-FIRST-D-DIAG-001 快速诊断窗口结果（v2，含审核修正）

方法：同窗交错双臂，唯一变量为 D 阶段 system prompt——
`v2` = FSDF-RELIABILITY-V2 合并栈（P0+P1+P2a+P2b，旧 DEEPEN_PROMPT）；
`v2hd` = 同栈 + `fsdf_handoff_first_d_v1`（DEEPEN_PROMPT_V2：交接产物优先，
SELECTED_BRANCH/CANDIDATE_D/OPEN/CHECKS/RISK 在前，DERIVED 以"第N步:"完整条目
持续交付，各字段只出现一次）。候选登记见
[`../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`](../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md) §6。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION`

> v2 修正说明（2026-09-05 审核）：本版按用户审核修正了三处口径——缺字段归因降级为
> 假设（附 D finish_reason 数据）、跨窗对照题量更正（20 题/池）并撤回"无漂移"表述、
> 成本口径改为"预算不变"并补 nearest-rank P95。原观察中"27→6 缺失字段实例"保留为
> 有效的描述性观察，但不再解释为"同样的失败题被新提示修好"。

- 运行：30 题（3 个冻结外部难题池 × 10，种子 20260905，round-robin 各 15 题），
  workers=3，hard-stop 75 min；实际 4168.1s（≈69.5 min）30/30 全部完成，0 任务崩溃、
  0 顶层错误。manifest：git_head `e7a35e4`，arm 开关快照见 run_manifest.json。

## 题源构成（两臂独立题集，无同题配对）

| 题源 | v2 | v2hd |
| --- | - | - |
| OlymMATH | 4 | 6 |
| AIME | 4 | 6 |
| HLE | 7 | 3 |

两臂没有任何同题配对，题源构成也不平衡；跨臂比较只能是分布级描述。

## 验收观测（用户定义口径：交接完整率、E 终答形成率、正确数；不以格式通过率为唯一标准）

| 指标 | v2（旧 D 提示） | v2hd（交接产物优先） |
| --- | --- | --- |
| 交接完整率（finalize 无缺失字段） | 9/15（60%） | 9/15（60%） |
| 不完整题目的缺失字段实例总数 | **27**（每题平均 4.5 个字段） | **6**（每题 1 个字段） |
| 缺失字段分布 | DERIVED/OPEN/CHECKS/RISK 各 6、CANDIDATE_D 3（整段交接缺席） | DERIVED 2、CANDIDATE_D 4 |
| correct | 2（来源：deep_final 2） | 2（来源：**finish_final 2**） |
| incorrect | 0 | 2（来源：deep_final 2） |
| invalid/UNKNOWN | 13 | 11 |
| mean_calls / mean_dur / nearest-rank P95 | 5.0 / 416s / **504.13s** | 5.0 / 397s / **551.44s** |
| D 阶段 finish_reason=length（按成功调用序对齐） | 5/15 | 3/15 |
| E 阶段 finish_reason=length | 13/15（另 2 题 E client 异常） | 13/15 |
| 阶段协议失败 / 阶段 client 异常 | 2 / 2 | 1 / 0 |

注：n=15 时 nearest-rank P95 数学上等于最大值，估计很不稳定，仅作记录不作结论。
缺失字段存在多种可能来源：模型未输出、UNKNOWN 被占位符过滤、协议失败、解析丢弃、
D 尾部截断；上表 D finish_reason 数据说明 v2 的 6 个不完整样本中 2 个 D 正常结束
（stop）、4 个截断（length），v2hd 的 6 个不完整样本 D 全部 stop——**尾部截断不是
唯一甚至不是 v2hd 的主要来源**。v2hd 的 4 个 CANDIDATE_D"缺失"大概率是新提示明确
允许的诚实弃答（"无法确定写 UNKNOWN"）被占位符过滤所致；当前 trace 不区分"字段
缺席"与"字段=UNKNOWN 合规弃答"，该口径细化属独立诊断改动（已在 Issue #16 登记）。

## 主要诊断观察（修正后）

1. **"27→6 缺失字段实例"是有效的描述性观察，但不能解释为"同样的失败题被新提示
   修好"**：两臂无同题配对、题源构成失衡（见上表），且 v2 的不完整样本中 2 个 D
   正常结束（stop），说明缺字段并非全部来自尾部截断。管理字段前置后不完整样本
   每题缺失字段更少，这一形态差异成立，归因待配对窗口验证。
2. **E 终答形成率出现方向性信号，但证据有限**：v2 臂的 2 个 correct 全部是 E 未形成
   被采纳的有效终答后（E 调用本身成功返回，非 client 异常）采纳 D 的 FINAL_D；
   v2hd 臂出现 2 个 E 直接给出的确认终答（finish_final）且全部 correct——这只能
   证明终答来源于 E，尚不能证明 E 依赖交接内容完成了新增推导。
3. **正确数打平（2=2），incorrect 出现 0→2**：v2hd 的 2 个 incorrect 来自 deep_final
   （D 新协议给出了显式 FINAL_D 但推导错误，按 P2a 规则被采纳）。显式完成标记提高
   了可采纳性，也把 D 的错误结论带进了终答——程序不能仅凭 RESULT/FINAL_D 字段认定
   数学上已证明。incorrect 增加不直接降低以正确数计分的成绩，也不能据不同题组断言
   能力退化；本窗未观察到正确率优势，v2hd 不晋升。
4. **更明确的瓶颈是阶段截断**：E 返回 length 的比例接近饱和（v2 13/15 + 2 次 client
   异常、v2hd 13/15），v2hd 的 11 个 UNKNOWN 中 10 个对应 E 截断。若下一窗口 E 仍
   普遍用满 4096 token，应依据配对诊断决定阶段任务量或预算分配，而不是继续叠加协议。
5. **成本口径**：调用数与 token 上限不变（"预算不变"）；实测时长 v2 均值 416s、
   v2hd 均值 397s，P95 见上表（n=15 口径下等于最大值），不据此宣称实际成本不变。
6. **跨窗参考对照**（同 v2 栈、不同窗口、20 题/池，共 60 题）：本窗口 v2 臂 correct
   2/15（13%）与上窗 4/30（13%）构成相近；两窗正确率恰好相同**不能证明没有窗口
   漂移**，此对照仅为描述性参考。

## 边界与未做事项

- n=15/臂，仅方向性诊断，无统计功效；两臂共享 v2 合并栈，单变量是 D 提示文本，
  但 v2 栈本身未经单变量过门，本结果不构成任何能力结论。
- "截断后程序只保留完整条目"在本窗运行时**尚未验收**：程序可控制自身字符裁剪，
  但不能识别模型响应本已截断；半截公式会原样进入 E 且诊断无标记。该验收缺口与
  字段状态细化已作为 Issue #16 第一步落地（零模型）。
- 门槛 UNFROZEN；本窗口不判定能力门、不修改 `SUBMISSION_CONFIG`、不推送 main、
  不发布。逐条目增量交付协议与条目结束标记须独立预注册。
- 本地 native/contract 为本地近似判定，非官方 judger 等价实现。
