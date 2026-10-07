# FSDF-ITER-AB-009 配对回归窗口结果（迭代第 9 轮）

方法：同题配对双臂，唯一变量 = `fsdf_deep_candidate_fallback_v1`（程序侧、仅
E 失败时生效：P2a 在 deepen-ok、无 FINAL_D、无弃答后采纳 content 态
CANDIDATE_D，来源 `deep_candidate`）。基线 `v2hd_bs_hs`（前沿）vs 候选
`v2hd_bs_hs_dcf`。15 题配对，workers=3，hard-stop 75 min。git_head `3ffaaa6`。
30/30 run 完成。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 机制未激活（可转化池集中于协议失败 D） / 前沿不变`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | D 协议失败 |
| --- | - | - | - | - | - | - |
| v2hd_bs_hs（前沿） | 2 | 1 | 12 | 3/15 | 10/15 | — |
| v2hd_bs_hs_dcf（候选回退） | 3 | 2 | 10 | 5/15 | 9/15 | **11/15** |

- 配对矩阵：invalid→correct 1（hle-6720f01e936e8e4575f4f3f4，摇摆题）、
  correct→correct 2、incorrect→incorrect 1、invalid→incorrect 1、invalid→invalid 10。
- 净增 +1、零反转——但 **deep_candidate 触发 0 次**，+1 为方差。

## 关键发现：可转化池集中在协议失败的 D

- 候选臂 D 协议失败率 **11/15**（思考默认模式下 D 的可见输出被思考挤占/截断，
  SELECTED_BRANCH 不可解析）；4 个可转化 run（E-UNKNOWN ∧ CANDIDATE_D=content）
  **全部是 protocol_failed**。
- 候选按设计只对协议成功的 D 生效（"协议失败 D 的原文不绕过来源有效性检查"），
  因此 0 触发——门控行为正确，但激活前提（deepen=ok ∧ pool）在思考默认模式下
  几乎不共存。
- VOID 门的历史数据（池 4-11/窗）未区分协议状态——后续 VOID 门应按协议状态分层。

## 判定

净增 +1 在噪声内（±1-2）且机制未激活 → 前沿不变（`v2hd_bs_hs`）。本窗的最大
产出是确认：**D 协议失败率本身是思考模式的另一个牺牲品**，强化迭代 10
（思考关闭）的优先级。

## 边界

诊断窗口；无能力结论；`SUBMISSION_CONFIG` 不改动。本地 native/contract 为本地
近似判定，非官方 judger。
