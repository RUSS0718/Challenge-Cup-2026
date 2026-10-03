# GRH v1.3 验收审查

日期：2026-10-03  
审查方式：只读子智能体审查 + 本地工件核对  
结论：**NOT READY / FAIL，不得晋升默认提交路径**

## 已确认通过的局部范围

- v1.3 checkout 基于 v1.1 release commit `43a02da`。
- v1.2 工作区未被删除、重置或覆盖；它只作为证据和可挑选补丁来源。
- P0 ledger 与 P1 host replay 均为无模型调用的离线工件，记录数为 221/221。
- ledger/replay 没有把 gold 传入 solver 或 recovery path。
- `capability_conclusion` 保持为 `NONE`，因此当前实现没有把 host hygiene 直接宣称为数学能力。

这些结果只能证明离线产物和部分 host 恢复路径存在，不能证明 invalid→correct 的数学能力提升。

## 阻断性问题

在审查中发现并修复了一个安全问题：`recover_response()` 原先在 `RecoveryAction.UNKNOWN` 时仍返回解析出的候选，导致报告把 3 个 `R2/S3 candidate_conflict` 行计入 `unknown → correct`。修复后，这 3 行必须保持 `unknown`；因此原报告的 9 个救回最多只能计为 6 个安全 host replay 救回。修复由 `tests/test_grh_v13.py::test_conflicting_candidate_is_fail_closed` 覆盖。

1. **真实实验虽然完成，但不能按预注册验收。** `artifacts/GRH-V13-REAL-AB-20261003-run1/run_manifest.json` 现在有 221/221 条记录和 `report.json`，但此前运行过程中曾处于未完成状态，runner 仍没有在缺 telemetry、运行错误或 wall-clock breach 时统一写 VOID。完成状态本身不能补齐这些验收缺口。
2. **硬时限实现不安全。** wall-clock 超限后取消 pending futures，但 `ThreadPoolExecutor` context 退出默认等待，可能把 6 小时硬截止拖过。
3. **指标语义不完整。** runner 只统计 `unknown → ...`，把 invalid、health error 和 unknown 混在一起，没有文档要求的四个核心转移：`invalid→correct`、`invalid→incorrect`、`correct→incorrect`、`correct→invalid`。
4. **telemetry 不足以验收。** 当前报告没有平均/P95 latency、requested/completion token 汇总、timeout/health error、response length、finish_reason=length、truncation-before-final、candidate 完成率等字段；缺失 telemetry 按预注册应直接 VOID。
5. **预算声明与实际 profile 不一致。** manifest 写入 `max_model_calls=3`，resolved `SUBMISSION_CONFIG` 的 `max_model_calls` 为 5；这会使成本门无法审计。
6. **没有 dev/holdout/regression 分层。** 当前真实 runner 直接读取整套 221，无法证明 invalid-holdout 的 zero-damage 或 valid-regression 的 correct-damage 门。
7. **P3/P5 尚未做。** 没有两轮独立、同端点交错的 finalizer、verification 或 adaptive 机制实验，因此不能判定双轮 Net Correct Gain、损伤、成本和 P95 门。

## 处置

- 当前真实运行只能作为未完成实验保留；完成前不写能力结论。
- P0/P1 保留为 host hygiene / evidence-preservation 结果，不进入默认提交配置。
- 下一次运行前必须先修 runner：硬 VOID、完整 telemetry schema、九格转移矩阵、预算一致性和固定 seed 分层；随后重新预注册并重跑。
- 在 P3 两轮机制实验全部通过前，不修改 `SUBMISSION_CONFIG`、默认 profile 或官方候选。

