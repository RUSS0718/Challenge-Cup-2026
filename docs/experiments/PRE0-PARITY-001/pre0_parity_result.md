# PRE0-PARITY-001 结果：实验面与发布面行为签名

- 窗口 ID：`PRE0-PARITY-001`，类型 `STRUCTURAL_ONLY`（零模型调用）
- 运行时间：2026-08-30；attempt = 1（结构比较一次通过）
- 预注册：[`preregistration.md`](preregistration.md)（含 Amendment A1）
- 判定：**PASS**（13/13 场景 + facade 导出 + 双跑确定性）

## 1. 被测面

| 面 | 代码 | 实测 git 状态 |
| --- | --- | --- |
| RELEASE 发布面 | 主 checkout `user_agent.py`（单体） | main 46c08dd，`user_agent.py` 无未提交改动 |
| EXPERIMENT 实验面 | `.worktrees/main-integration-20260829` facade → `reasoning_agent/` 包 | 39fcd12 + 未提交 2b4ba30 语义恢复补丁（见 §3） |

## 2. 签名比较结果（13 场景）

11 个严格场景（L0、hetero 早共识、k5 跑满、model error 恢复、fallback、
verify all-clear、verify revise、reverify pass、reverify fail、ARH 双形态、
非数值输出）两面的以下字段**逐字节一致**：

- 有序 client transcript（每次调用的 messages SHA-256 + temperature + max_tokens）；
- 调用数；`final_response` 全文；`extracted_answer`；
- **完整 trace** 的规范化 JSON SHA-256（非摘要投影，全量 trace 一致）；
- 两面各自双跑签名完全一致（无隐藏非确定性）。

2 个预注册豁免场景（reverify skipped / inconclusive）：
transcript 完全一致（含 reverify 调用本身），分歧**方向精确符合**冻结语义：

| 场景 | 发布面（main，keep 语义） | 实验面（fail-closed） |
| --- | --- | --- |
| reverify_skipped | 保留修订 → 答案 "6" | 回滚 → 原答案 "5" |
| reverify_inconclusive | 保留修订 → 答案 "6" | 回滚 → 原答案 "5" |

facade 导出检查：`ReasoningAgent / AgentConfig / SUBMISSION_CONFIG /
classify_problem_type / extract_final_answer / normalize_answer / POLICY_PROMPT /
ANSWER_ONLY_POLICY_PROMPT` 全部可用，无缺失。

## 3. 过程发现与处置（Amendment A1 落实）

1. **发现**：集成分支在合并提交 `3bed2b7`（并在重构 `39fcd12` 中延续）把
   reverify 未决语义从工作分支 b2f01ec/2b4ba30 的 fail-closed 回滚**回归**为
   main 的"保留修订"——规范 §2 所述不一致在工作树上被合并动作扩散。
2. **处置**：按预注册 §3 冻结语义（= 2b4ba30 契约），以未提交补丁恢复实验面的
   回滚语义（skipped / inconclusive / 预算耗尽均回滚；预算耗尽补记
   `reverify: skipped` trace）；工作树测试
   `test_reverify_unavailable_keeps_revision_like_deployed_main` 同步改写为
   `test_reverify_unavailable_rolls_back_fail_closed`；工作树全量 442 测试通过。
3. **影响面**：AA/EXT 窗的 `baseline_hetero` 臂 refine 关闭，补丁处于休眠；
   该语义恢复是行为变更，必须随集成分支一起走发布评审，**不得**在无预注册下
   再次改回。

## 4. 结论与下游解锁

- 实验面（重构包）与发布面（单体）除预注册的 reverify 未决语义外行为完全
  一致——本地实验结论可迁移到提交配置；PRE0-AA-001 / PRE0-EXT-001 解锁。
- 语义处置建议（记录，不在本窗执行）：P0 §7.2 完成时，发布面应把 reverify
  未决语义对齐到 fail-closed（走 `refine_unknown_rollback_v1` 或直接契约修正），
  消除两面最后的预注册差异。
- 产物：`parity_scenarios.json`、`parity_result.json`、
  `signatures_{release,experiment}_run{1,2}.json`、
  `scripts/pre0_parity_harness.py`、`scripts/pre0_parity_runner.py`。

## 5. 明确不做

- 零模型调用；不 commit、不 push、不改 `SUBMISSION_CONFIG`；
  不在本窗内对两面做其他"顺手"对齐。
