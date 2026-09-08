# 文档索引与归档边界

本索引把“当前使用”和“历史证据”分开。历史实验目录保留原路径，是为了让
`docs/excluded_approaches.md`、manifest 和报告中的引用继续可复核；它们不属于
运行时导入，也不应被当作当前方案。

## 当前应优先阅读

- [CONTEXT.md](../CONTEXT.md)：领域术语与当前默认配置语义。
- [excluded_approaches.md](excluded_approaches.md)：实验处置的单一事实源。
- [adr/](adr/)：已接受的架构决策。
- [CAR-001 规格](experiments/CAR-001-ADAPTIVE-CANDIDATE-FIRST-SPEC/preregistration.md)：
  当前 thinking-on 候选架构（默认关闭）。
- [POST-MAIN-EVAL-001](experiments/POST-MAIN-EVAL-001/result.md)：最近一次本地 smoke。
- [agents/](agents/)：仓库协作与 issue 约束。

## 历史实验证据（保留，不作为当前默认路径）

- `FSDF-ITER-AB-*`、`FSDF-V2-*`、`FSDF-RELIABILITY-V2-*`：FSDF 可靠性与迭代战役。
- `FESF-*`、`HOST-LOOP-*`：FESF、Claim DSL、Host Loop 和 skill 验收/资格窗。
- `BTCS-*`、`V4-*`、`V5-*`、`STATEFUL-*`：已归档协议与资源试验。
- `CAUSAL-MCP-*`、`ERROR-NOTEBOOK-*`：独立工程/错题本实验，不接入默认求解。
- 日期命名的 `docs/experiments/*2026-08*` 与 `*2026-08-29*`：早期探索、否决或发布记录。

上述目录中的 `result.md`、`report.json`、`run_manifest.json` 和逐题记录属于审计材料，
即使方案已 `REJECTED`/`ARCHIVED` 也不删除。

## 已归档的旧总结

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
