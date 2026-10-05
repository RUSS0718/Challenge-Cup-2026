# 文档索引与归档边界

本索引把“当前使用”和“历史证据”分开。历史实验目录保留原路径，是为了让
`docs/excluded_approaches.md`、manifest 和报告中的引用继续可复核；它们不属于
运行时导入，也不应被当作当前方案。

## 当前应优先阅读

- [当前发布状态](current_release.json)：由 `scripts/show_repo_state.py` 生成，包含 selector、Git ref、运行工件和 runtime hash 检查。
- [实验处置注册表](experiment_registry.json)：机器可查询的近期方案状态；完整历史仍以 `excluded_approaches.md` 为准。
- [代理经历审查](research/codex_agent_experience_audit_2026-10-05.md)：最近十次任务的检索热点、过时文档风险和治理落地记录。
- [CONTEXT.md](../CONTEXT.md)：领域术语与当前默认配置语义。
- [ARM v2.1.4 CFR 发布协议](releases/arm-v2.1.4-cfr-20261004/protocol.md)：当前正式 selector、
  Challenger/Repair/Review 门和官方复评边界。
- [ARM v2.1.7 structured confirmation](experiments/ARM-V2.1.7-STRUCTURED-CONFIRMATION-20261005/result.md)：
  默认关闭的 incumbent-only Challenger 配对结果和处置。
- [ARM v2.1.8 external length-pressure](experiments/ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-20261005/result.md)：
  首次窗口的 VOID 审计记录；纠正后的结果见 [window 002](experiments/ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002-20261005/result.md)。
- [ARM v2.1.8 external length-pressure replication](experiments/ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-REPLICATION-20261005/result.md)：
  使用不重叠外部题目的独立 Y 窗口；安全门未通过，保持默认关闭。
- [ARM v2.1.9 incumbent guard](experiments/ARM-V2.1.9-INCUMBENT-GUARD-20261005/preregistration.md)：
  Z01–Z10 已完成，guard 激活但出现安全门损害；保持 `NO_GO / DEFAULT_OFF`，结果见
  [result](experiments/ARM-V2.1.9-INCUMBENT-GUARD-20261005/result.md)。
- [ARM v2.2 answer-commit-first](experiments/ARM-V2.2-ANSWER-COMMIT-20261005/preregistration.md)：
  针对官方 `length`/`invalid` 风险的 Q01–Q10 新预注册窗口，候选默认关闭。
- [architecture_evolution.md](architecture_evolution.md)：从赛事模板到当前 Harness 的架构谱系、版本状态和证据边界。
- [official_evaluations/](official_evaluations/)：按北京日期归档官方原始日志与 agent 分析。
- [excluded_approaches.md](excluded_approaches.md)：实验处置的单一事实源。
- [adr/](adr/)：已接受的架构决策。
- [CAR-001 规格](experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-SPEC/preregistration.md)：
  当前 thinking-on 候选架构（默认关闭）。
- [ARM-Harness v2 技术设计](9.28/v2/ARM-Harness%20v2%20技术设计文档.md) 与
  [详细实现文档](9.28/v2/ARM-Harness%20v2%20详细实现文档.md)：v2 架构及实现方案。
- [ARM-Harness v2 完成情况归档](9.28/v2/ARM-Harness%20v2%20完成情况归档.md)：
  2026-09-28 的 ARM 隔离诊断与结果质量审计完成状态、证据边界和后续实验入口。
- [POST-MAIN-EVAL-001](experiments/POST-MAIN-EVAL-001/result.md)：最近一次本地 smoke。
- [agents/](agents/)：仓库协作与 issue 约束。

## 历史实验证据（保留，不作为当前默认路径）

- `FSDF-ITER-AB-*`、`FSDF-V2-*`、`FSDF-RELIABILITY-V2-*`：FSDF 可靠性与迭代战役。
- `FESF-*`、`HOST-LOOP-*`：FESF、Claim DSL、Host Loop 和 skill 验收/资格窗。
- `BTCS-*`、`V4-*`、`V5-*`、`STATEFUL-*`：已归档协议与资源试验。
- `CAUSAL-MCP-*`、`ERROR-NOTEBOOK-*`：独立工程/错题本实验，不接入默认求解。
- 日期命名的 `docs/experiments/*2026-08*` 与 `*2026-08-29*`：早期探索、否决或发布记录。
- `architecture_evolution.md` 只做版本导航；不要用它替代实验报告中的逐题结果、manifest 或处置结论。

上述目录中的 `result.md`、`report.json`、`run_manifest.json` 和逐题记录属于审计材料，
即使方案已 `REJECTED`/`ARCHIVED` 也不删除。

## 已归档的旧总结

- [invalid_rescue_round3_2026-10-04.md](archive/invalid_rescue_round3_2026-10-04.md)：
  invalid rescue 第三轮综合归档。全量回放出现正确损失，因此 43a02da 保留为回滚锚；相关
  实验代码和大型参考资源已从发布树移除。当前正式路径见 CFR 发布协议。
- [P0-提交总结-2026-07.md](archive/legacy/P0-提交总结-2026-07.md)：已移出根目录，
  仅用于历史追溯。
- [TODO_LIST-2026-07.md](archive/legacy/TODO_LIST-2026-07.md)：已移出根目录，早期任务
  仅用于追溯；当前待办以实验规格和 `docs/excluded_approaches.md` 为准。
- [answering_system_contextual_reconstruction_v1.md](archive/legacy/answering_system_contextual_reconstruction_v1.md)：
  已关闭且未验证的历史架构说明。

## 可归档候选（当前未移动）

以下是未跟踪的草稿/图片，移动前仍需确认是否要保留原路径，因为部分 manifest 记录了
它们的路径或 hash：

- `agent_architecture_technical_proposal_draft_2026-09-04.md`
- `causal_mcp_upgrade_plan_2026-09-04.md`
- `docs/architecture/`
- `docs/TEMPORARY-100-MATCHER-UPDATE.md`

以上候选仍暂留原路径；移动前需同步更新 manifest 中的路径/hash 引用。
