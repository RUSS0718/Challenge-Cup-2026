# FSDF-D-RESULT-TO-E-PAIRED-001 配对诊断窗口结果（迭代第 0 轮）

方法：同题配对双臂，唯一变量 = `fsdf_d_result_to_e_v1`（D 的 FINAL_D 以
`FINAL_D_FOR_CHECK` 行对 E 可见）。基线 `v2hd` vs 候选 `v2hd_dre`，冻结池 ×5/集
（15 题），先臂逐题轮换，workers=3，hard-stop 75 min。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION / 候选机制未激活`

- 运行：29/30 对完成（`aime-29/v2hd_dre` 被 hard-stop 跳过）；**启动事故**：前 22 对
  因双进程重复运行各执行两次（见 `answers_raw_duplicate_run.jsonl`），分析按
  (item_id, arm) 去重取首条；0 顶层错误。
- manifest：git_head `fed4097`。

## 配对结果（native 判定，14 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd（基线） | 0 | 1 | 14 | 1/15 | 12/15 | 465.5s / 640.5s |
| v2hd_dre（候选） | 1 | 1 | 12 | 2/14 | 11/14 | 471.9s / 606.0s |

- 配对矩阵：invalid→invalid 12；**invalid→correct 1**（aime-2024-II-1）；incorrect→incorrect 1。
- correct 净增 +1、无反转——但见下条，这 +1 不能归因于候选机制。
- D 候选处置（相对基线终答）：同值 1 / 不同值 1 / 弃答 12。

## 关键发现：候选机制从未激活

- `d_candidate_visible_to_e` 在 **14/14** 个 v2hd_dre run 中均为 False：D 从未产出
  "唯一且有效"的 FINAL_D（`fsdf_handoff_first_d` 提示把 FINAL_D 设为可选，D 实际
  几乎不输出；D finish_reason = stop 10 / length 4）。
- 因此本窗口**实际测量的不是 FINAL_D 可见性**，而是同栈重跑方差；+1 correct 为噪声级。
- 锚定观测（E 照抄候选）无从发生（可见 0 次）。

## 供下一轮迭代的事实

1. **E 截断近饱和**：13-12/15 length；E 用满 4096 token 仍是首要瓶颈（符合用户
   "E 仍普遍用满 4096 再议阶段任务量/预算分配"的预案条件）。
2. **FINAL_D 产出率为零**：要让"明确结果交 E 核查"成为可测假设，需先让 D 稳定产出
   FINAL_D（如把"可以输出"改为"必须输出，无法确认写 UNKNOWN"）——这本身是一个
   独立单变量候选。
3. 成本：两臂 mean_calls 5.0，时长与 P95 见上表，预算未放宽。
4. 运行纪律：本次双进程事故后，后续迭代窗口统一由单次后台启动 + 完成监视器管理。

## 边界

诊断窗口，无能力结论、无晋升；v2hd 与 v2hd_dre 在本样本内行为等价（机制未激活），
前沿保持不变。本地 native/contract 为本地近似判定，非官方 judger。
