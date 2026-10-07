# 历史归档

这里存放不再作为当前方案入口的历史总结、草稿和决策背景。归档内容保留用于追溯，
不参与运行时导入，也不代表当前默认配置。

当前已归档：

- `invalid_rescue_round3_2026-10-04.md`：invalid rescue 第三轮（EACL、proof gate、surface
  serializer、binary decision、R2/R5 审计）的结果、回退理由和代码清理边界；正式路径继续使用
  43a02da 作为回滚锚，当前正式路径改由 `docs/releases/arm-v2.1.4-cfr-20261004/` 记录。
- `legacy/P0-提交总结-2026-07.md`：2026 年 7 月 P0 阶段总结，已被后续 FSDF/FESF
  和官方评测记录取代。
- `legacy/TODO_LIST-2026-07.md`：早期开发任务清单，已被当前实验登记和排除表取代。
- `legacy/answering_system_contextual_reconstruction_v1.md`：已关闭的 Contextual
  Answer Reconstruction 方案说明。

实验报告仍按原实验 ID 保留在 `docs/experiments/`，以免破坏 manifest、hash 和
`docs/excluded_approaches.md` 的引用链。
