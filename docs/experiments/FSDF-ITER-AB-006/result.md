# FSDF-ITER-AB-006 确认复现窗结果（迭代第 6 轮）

方法：同题配对双臂，与迭代 5 完全同臂同题重跑——基线 `v2hd_bs_hs`（前沿）vs
候选 `v2hd_hs_of`（OPEN 前置渲染）。15 题配对，workers=3，hard-stop 75 min。
git_head `48198ea`（与迭代 5 同代码）。30/30 run 完成。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 复现失败 → 候选记为方差内效应 / 前沿不变`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd_bs_hs（前沿） | 3 | 1 | 11 | 4/15 | 8/15（历史最好） | 416.7s / 594.4s |
| v2hd_hs_of（OPEN 前置） | 2 | 1 | 12 | 3/15 | 10/15 | 439.7s / 591.1s |

- 配对矩阵：invalid→correct 1、**correct→invalid 2**、correct→correct 1、
  incorrect→incorrect 1、invalid→invalid 10。**净增 −1**。

## 判定（按迭代 5 预注册规则）

- 复现条件"net ≥0 且机制改善再现"未满足：净增 −1；机制计数走差（形成 4→3、
  截断 8→10，且基线臂截断 8/15 为全部窗口历史最好）。
- **前沿保持 `v2hd_bs_hs`**；`fsdf_handoff_open_first_e` 记为方差内效应：
  两窗合计净效应 = +1 + (−1) = 0，与同配置 ±1-2 跨窗方差一致。

## 累积证据（供迭代 6 设计）

- 有效杠杆（结构/构成类）：E 预算（迭代 1）、E 输入构成（迭代 4，最强 +3 零反转）。
- 无效杠杆（措辞/加字段类）：E 提示措辞（迭代 2）、D 强制字段（迭代 3）、
  渲染顺序（迭代 5-6，两窗净 0）。
- 顽固瓶颈：E 截断 8-11/15（即使 8192 + 最佳构成）；invalid 池 ~9-12/窗；
  前沿配置跨窗 correct 1/3/4（±1-2 方差）；AIME 摇摆题持续翻转。

## 边界

诊断窗口；无能力结论；`SUBMISSION_CONFIG` 不改动。本地 native/contract 为本地
近似判定，非官方 judger。
