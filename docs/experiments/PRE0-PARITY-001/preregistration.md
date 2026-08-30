# PRE0-PARITY-001 预注册：实验面与发布面行为签名

- 窗口 ID：`PRE0-PARITY-001`
- 类型：`STRUCTURAL_ONLY`，**零模型调用**
- 预注册冻结时间：2026-08-30（场景构造与运行之前）
- 上位规范：`math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6、§2

## 1. 假设与动机

本地实验在集成分支 `codex/main-integration-20260829`（39fcd12，`reasoning_agent/`
包 + facade）上运行；官方发布面是 main 的单体 `user_agent.py`（46c08dd 工作树，
`user_agent.py` 本身无未提交改动）。两者之间隔着一个重构提交与一个 refine
复核 fail-closed 修复（2b4ba30）。若实验面的行为签名与发布面不一致，实验结论
无法迁移到提交配置。本窗口用 FakeClient 全路径场景量化两面的行为差异。

## 2. 两个被测面（冻结定义）

| 面 | 代码位置 | 入口 |
| --- | --- | --- |
| RELEASE 发布面 | 主 checkout 根目录 `user_agent.py`（单体，git 状态须确认无未提交改动） | `ReasoningAgent(client, config)` |
| EXPERIMENT 实验面 | `.worktrees/main-integration-20260829`（39fcd12）`user_agent.py` facade → `reasoning_agent/` 包 | 同上 |

## 3. reverify 未决语义冻结（先于运行，规范 §6 通过门要求）

- 冻结语义 = **实验面行为**：refine 复核（reverify）返回 skipped / inconclusive
  时**回滚**修订、恢复原答案（与文档声称的 fail-closed 一致）。
- 记录事实 = 发布面行为：skipped / inconclusive 时**保留**修订（main 46c08dd 实测，
  规范 §2 已指认其与文档不一致）。
- 自本预注册起，后续发布不得在无预注册的情况下改变该语义；P0 §7.2 的
  `refine_unknown_rollback_v1` 判读以本冻结为准。该差异是本窗唯一预注册允许的
  行为差异。
- **Amendment A1（2026-08-30，运行前）**：构造场景时实测发现集成分支在
  3bed2b7/39fcd12 已把 reverify 未决语义**回归**为 main 的"保留"行为（合并时
  取了 main 侧实现，丢失 b2f01ec/2b4ba30 的 fail-closed 回滚）。按本节冻结语义，
  实验面以**未提交补丁**恢复 2b4ba30 语义（skipped/inconclusive/预算耗尽均回滚；
  预算耗尽补记 `reverify: skipped` trace）。补丁记入本窗 manifest；AA/EXT 窗的
  baseline_hetero 臂 refine 关闭，不受影响。

## 4. 场景矩阵（13 个，全部 FakeClient 驱动）

| # | 场景 | 配置要点 | FakeClient 剧本要点 |
| --- | --- | --- | --- |
| 1 | `l0_direct` | baseline_hetero | 简单算术题面，首答即收敛 |
| 2 | `hetero_early_consensus` | baseline_hetero | 3 票一致早停 |
| 3 | `k5_full` | baseline_hetero | 5 票互异跑满 |
| 4 | `model_error_recovery` | baseline_hetero | 首调用抛端点错误，后续正常 |
| 5 | `fallback_all_rejected` | baseline_hetero | 全部候选不可抽取 → fallback |
| 6 | `verify_all_clear` | +refine | 校验器 `ALL_OK:COMPLETE` |
| 7 | `verify_revise` | +refine | 校验器报错 → revise 换答案 |
| 8 | `reverify_pass` | +refine | revise 后复核干净 |
| 9 | `reverify_fail` | +refine | 复核再报错 → 回滚 |
| 10 | `reverify_skipped` | +refine | 复核调用失败（None） |
| 11 | `reverify_inconclusive` | +refine | 复核输出畸形（False） |
| 12 | `arh_dual_form` | +refine+ARH | 数值题，终答双形态 |
| 13 | `non_numeric_output` | baseline_hetero | proof 型题面，无数值答案句式 |

- baseline_hetero 配置 = 实验 runner 冻结臂：`numeric_prompt + adaptive k5/3 +
  4096 + policy_prompt + heterogeneous`，`max_model_calls=5`；"+refine" =
  `enable_step_verification/revision + p3_call_boost=3`；ARH =
  `enable_answer_dual_form`。两面用同一场景规格各自构建 `AgentConfig`
  （实验面多出的默认关开关全部保持默认关闭）。
- FakeClient：确定性强脚本 client，按调用序回放响应/异常，记录每次调用的
  `(prompt_sha256, temperature, max_tokens)`；同一 FakeClient 类注入两个面。

## 5. 签名与比较门

每个场景×每个面记录：`call_count`、有序 `calls[{prompt_sha256, temperature,
max_tokens}]`、`final_response` 全文与 SHA-256、`extracted_answer`、
`trace_summary_sha256`（trace 仅保留 step/status/reason 的规范化 JSON 哈希）、
`finish_kind_sequence`。

**通过门**：13 个场景中，除场景 10、11（reverify 未决，按第 3 节冻结语义豁免
final_response 与 trace 摘要的 diff，但**调用数与复核前 transcript 仍必须一致**）
外，其余 11 个场景两面的全部签名逐字段一致；任何其他不一致 → 本窗 FAIL。

附加强制项：实验面 facade 导出面检查（`ReasoningAgent`、`AgentConfig`、
`SUBMISSION_CONFIG`、`classify_problem_type`、`extract_final_answer`、
`normalize_answer` 等与 main 导出清单一致）。

## 6. VOID 与停止条件

- 任一非豁免签名不一致 → 记录差异首因（定位到提交），本窗 FAIL；
  Pre-P0 停止模型窗（AA/EXT 不得开跑），先处置差异再整窗重测（attempt 计数
  落结果文档）。
- 零模型调用；不 commit、不改 `SUBMISSION_CONFIG`、不在本窗内"顺手"对齐
  两面代码——差异处置是独立任务。

## 7. 产物

`parity_scenarios.json`（场景与剧本）、`signatures_release.json`、
`signatures_experiment.json`、`pre0_parity_result.md`。
