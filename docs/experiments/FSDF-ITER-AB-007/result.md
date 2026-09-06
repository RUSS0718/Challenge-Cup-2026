# FSDF-ITER-AB-007 配对回归窗口结果（迭代第 7 轮）

方法：同题配对双臂，唯一变量 = `fsdf_finish_handoff_share_v2`（share 模式下移除
最后的叙事块 A 约束摘要，E 上下文 = 分支 + 纯进度交接，装配上限 4600→6050）。
基线 `v2hd_hs`（前沿 v2hd_bs_hs）vs 候选 `v2hd_hs_sv2`。15 题配对（2 run 被
hard-stop 跳过，28/30 对），workers=3。git_head `85eba30`。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 预注册反斥触发（假设证伪） / 前沿不变`

## 配对结果（native 判定，14 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd_hs（前沿） | 3 | 1 | 10 | 4/14 | **7/14（历史最低）** | 483.7s / 641.1s |
| v2hd_hs_sv2（v2 构成） | 2 | 2 | 10 | 4/14 | 10/14 | 518.6s / 595.3s |

- 配对矩阵：invalid→correct 1（OlymMATH-HARD-75-ZH）、**correct→invalid 1、
  correct→incorrect 1（aime-2024-I-8 反转）**、correct→correct 1、invalid→invalid 9、
  incorrect→incorrect 1。净增 **−1**。

## 判定：预注册反斥触发

- 机制门失败：E 截断 10 vs 前沿臂 7（需 ≤ 6）——移除全部叙事块后截断不降反升。
- 反斥条款命中："构成验证通过但截断 ≥ 前沿 −1 且 net ≤ 0" ✓ → **重推导邀请假设
  证伪**。E 的全预算自延展不是由残余叙事诱发的；"纯进度交接"反而略差（候选臂
  mean 时长 +35s）。
- 前沿保持 `v2hd_bs_hs`。累计证据更新：**构成类杠杆已穷尽**（选中思路、A 摘要、
  渲染顺序全部反斥或方差内），唯一两次前移均为 E 侧生成预算/构成中的预算部分。

## 边界

诊断窗口；无能力结论；`SUBMISSION_CONFIG` 不改动。本地 native/contract 为本地
近似判定，非官方 judger。
