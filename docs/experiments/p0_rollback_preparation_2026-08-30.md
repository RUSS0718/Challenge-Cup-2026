# P0 回滚准备（2026-08-30）——待用户授权执行

状态：**EXECUTED（2026-08-30 深夜，用户决策 PATH_A_LINEAR_REVERT）**。
执行记录：分支 `p0-rollback-46c08dd`（基于 gitcode tip 46c08dd）→ 恢复
`user_agent.py` 为 25f99b5 字节（blob e804506…，仅 runtime，21 行 diff 反转）
→ 提交 `019cc40` → **fast-forward push 至 gitcode main（无 force）** →
fetch 复核远端 tip=`019cc40`、blob 一致 → 离线接口冒烟（SUBMISSION_CONFIG
refine/ARH 关、三并发 solve、JSON、非空 final_response）通过。
PRE0 重构未发布（保留在本地 PRE0-8.30）。以下原始准备文本保留作档案。

## 1. 裁决回顾

官方 Run #7（`46c08dd`，hetero+refine+ARH 整栈）：correct 9（vs 健康锚 12）、
agent-stage error 1、7h14m——三门齐触 → `OFFICIAL_NEGATIVE_STACK /
ROLLBACK_TRIGGERED`。运营基线恢复目标：`hetero_k5 @ 25f99b5`
（`operational_baseline_hetero_k5_25f99b5.json`）。

## 2. 两条等价回滚路径（用户二选一）

### 路径 A：GitCode main 直接回到 `25f99b5`（原行为提交 `18f4f5a`）

- 操作（用户授权后）：
  1. 在 GitCode 提交仓库将 main 指到 `25f99b5`（或推一个 revert 提交，保持
     历史线性，推荐 revert 以免强制推送）；
  2. 核对远端 tip 与 `SUBMISSION_CONFIG` 与
     `operational_baseline_hetero_k5_25f99b5.json` 一致；
  3. 作品页面无需重新提交（评测按 main 最新拉取）。
- 优点：行为零差异（就是跑出 12/112 的那份代码）。
- 代价：丢失 `46c08dd` 之后的所有后续工作（本地 main/PRE0-8.30 不受影响，
  仅提交仓库回退）。

### 路径 B：当前代码线（PRE0-8.30）发布 hetero_k5 等价 profile

- 唯一 diff（`reasoning_agent/policy.py` 的 `SUBMISSION_CONFIG`）：
  - `enable_step_verification: True → False`
  - `enable_step_revision: True → False`
  - `p3_call_boost: 3 → 0`（有效调用上限 8 → 5）
  - `enable_answer_dual_form: True → False`
- 等价性依据：PRE0-PARITY-001 对 46c08dd 单体重签——11 个非豁免场景
  transcript 逐字节一致；两个已知分歧场景（reverify skipped/inconclusive）
  在 refine 关闭的 hetero_k5 profile 下**休眠不生效**；runner 臂
  `baseline_hetero` 即本 profile 的逐字段复刻（AA-004 的 96 solves 均在此
  路径上运行）。
- 优点：保留运行时修复（reverify fail-closed、僵尸遥测护栏、模块化），
  后续能力方法直接叠加。
- 代价：官方跑的代码与 12/112 那份不是同一 commit（等价性靠 PARITY +
  profile manifest 背书，而非同一份字节）。

推荐：**路径 B**（等价 profile），与后续 P1/P2 的连续性最好；若用户更看重
"逐字节同代码"，选路径 A。

## 3. 无论何路径的收尾清单（P0 完成条件对照）

| §7 P0 完成条件 | 状态 |
| --- | --- |
| GitCode/main 回到或等价于 `25f99b5` hetero_k5 行为，核对远端 tip | ✅ **已执行并验证**（远端 tip 019cc40，blob=e804506…=25f99b5 字节） |
| 官方评测记录/排除表/README 写入 9/92/11、818、7h14m 与整栈处置 | ✅ 本批提交完成 |
| 唯一 `operational_baseline_id=hetero_k5_25f99b5`，manifest 可重建 | ✅ profile 已冻结 |
| 没有未处置的官方 canary | ✅ 发4 = `OFFICIAL_NEGATIVE_STACK` 已处置（回滚执行本身待授权） |

## 4. 明确不做（未授权前）

- 不 push 任何远端、不动 GitCode 提交仓库、不改作品页面；
- 不本地修改 `SUBMISSION_CONFIG`（路径 B 的 diff 待批准后以独立提交落地）；
- 不启动 P1/P2 模型窗（§15 需用户明确 GO）。
