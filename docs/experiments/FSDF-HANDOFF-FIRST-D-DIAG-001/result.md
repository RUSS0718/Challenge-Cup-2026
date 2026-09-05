# FSDF-HANDOFF-FIRST-D-DIAG-001 快速诊断窗口结果

方法：同窗交错双臂，唯一变量为 D 阶段 system prompt——
`v2` = FSDF-RELIABILITY-V2 合并栈（P0+P1+P2a+P2b，旧 DEEPEN_PROMPT）；
`v2hd` = 同栈 + `fsdf_handoff_first_d_v1`（DEEPEN_PROMPT_V2：交接产物优先，
SELECTED_BRANCH/CANDIDATE_D/OPEN/CHECKS/RISK 在前，DERIVED 以"第N步:"完整条目
持续交付，各字段只出现一次）。候选登记见
[`../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`](../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md) §6。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION`

- 运行：30 题（3 个冻结外部难题池 × 10，种子 20260905，round-robin 各 15 题），
  workers=3，hard-stop 75 min；实际 4168.1s（≈69.5 min）30/30 全部完成，0 任务崩溃、
  0 顶层错误。manifest：git_head `e7a35e4`，arm 开关快照见 run_manifest.json。

## 验收观测（用户定义口径：交接完整率、E 终答形成率、正确数；不以格式通过率为唯一标准）

| 指标 | v2（旧 D 提示） | v2hd（交接产物优先） |
| --- | --- | --- |
| 交接完整率（finalize 无缺失字段） | 9/15（60%） | 9/15（60%） |
| 不完整题目的缺失字段实例总数 | **27**（每题平均 4.5 个字段） | **6**（每题 1 个字段） |
| 缺失字段分布 | DERIVED/OPEN/CHECKS/RISK 各 6、CANDIDATE_D 3（整段交接缺席） | DERIVED 2、CANDIDATE_D 4 |
| correct | 2（来源：deep_final 2） | 2（来源：**finish_final 2**） |
| incorrect | 0 | 2（来源：deep_final 2） |
| invalid/UNKNOWN | 13 | 11 |
| mean_calls / mean_dur | 5.0 / 416s | 5.0 / 397s |
| 阶段协议失败 / 阶段 client 异常 | 2 / 2 | 1 / 0 |

## 主要诊断观察

1. **完整率数字相同（60% vs 60%），失败形态根本不同**：v2 的交接失败是灾难性的——
   6 个不完整题平均整段缺席 4.5 个字段（"深推完没空间写总结"，尾部截断吞掉全部
   handoff）；v2hd 把管理字段前置后，同样的 6 个不完整题每个只缺 1 个字段，E 在
   失败场景下仍然拿到 OPEN/CHECKS/RISK。这直接支持"最后留一块写 handoff 不可靠"
   的判断，也说明**完整率指标需要细化**：trace 目前不区分"字段缺席"与"字段=UNKNOWN
   合规弃答"（v2hd 的 4 个 CANDIDATE_D 缺失大概率是新提示明确允许的诚实弃答，
   被占位符过滤后计入缺失）。后续若细化，应在诊断增量里分开记录，属独立改动。
2. **E 终答形成率出现方向性信号**：v2 臂的 2 个 correct 全部是 D 的 FINAL_D 在 E
   失败后被采纳（E 自己没有形成确认终答）；v2hd 臂出现 2 个 E 直接给出的确认终答
   （finish_final）且全部 correct——E 在使用交接内容继续推进并确认答案。n=15 不足以
   下结论，但方向与实验假设一致。
3. **正确数打平（2=2），incorrect 出现 0→2**：v2hd 的 2 个 incorrect 来自 deep_final
   （D 新协议给出了显式 FINAL_D 但推导错误，E 失败后按 P2a 规则被采纳）。显式完成
   标记提高了可采纳性，也把 D 的错误结论带进了终答——这正是"程序不能仅凭 RESULT/
   FINAL_D 字段认定数学上已证明"的体现；P2a 的冲突/弃答处理不受影响。
4. **成本不变**：两臂 mean_calls 均 5.0，时长 416s vs 397s（v2hd 略短），调用与 token
   上限未放宽；协议失败率 2/15 vs 1/15 与历史量级一致。
5. **与 FSDF-V2-DIAG-SMOKE-001 的参考对照**（同 v2 栈、不同窗口、50 题/池）：本窗口
   v2 臂 correct 2/15（13%）vs 上窗口 4/30（13%），构成一致，窗口间无异常漂移迹象。

## 边界与未做事项

- n=15/臂，仅方向性诊断，无统计功效；两臂共享 v2 合并栈，单变量是 D 提示文本，
  但 v2 栈本身未经单变量过门，本结果不构成任何能力结论。
- 门槛 UNFROZEN；本窗口不判定能力门、不修改 `SUBMISSION_CONFIG`、不推送、不发布。
- 逐条目增量交付协议（每完成一个局部步骤交付一个完整条目、程序侧增量确认）的
  进一步改造不在本实验内，须独立预注册。
- 本地 native/contract 为本地近似判定，非官方 judger 等价实现。
