# FSDF-ITER-AB-005 配对回归窗口结果（迭代第 5 轮）

方法：同题配对双臂，唯一变量 = `fsdf_handoff_open_first_e_v1`（仅 E 侧 handoff
渲染顺序：OPEN 提到 DERIVED 之前）。基线 `v2hd_bs_hs`（前沿）vs 候选 `v2hd_hs_of`。
15 题配对，workers=3，hard-stop 75 min。git_head `48198ea`。30/30 run 完成。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 进入确认复现窗（前沿暂不变）`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd_bs_hs（前沿） | 1 | 0 | 14 | 1/15 | **14/15** | 464.3s / 567.9s |
| v2hd_hs_of（OPEN 前置） | 2 | 1 | 12 | 3/15 | 12/15 | 433.4s / 500.2s |

- 配对矩阵：invalid→correct 1（hle-6720f01e936e8e4575f4f3f4）、invalid→incorrect 1、
  correct→correct 1、invalid→invalid 12。净增 +1、零反转。
- 机制门未达（形成 3/15 < 7、截断 12/15 > 8），但双机制计数均改善（1→3、14→12）。
- 基线臂本窗截断 14/15 为历史最差（前沿配置此前 9-11）——run 方差极大。

## 判定与下一步

按预注册规则："net +1、零反转且双机制改善 → 复现窗后再前移"。迭代 6 为同臂同题
确认复现窗（FSDF-ITER-AB-006）：若净增 ≥0 且机制改善复现，前沿前移至 `v2hd_hs_of`；
否则前沿保持 `v2hd_bs_hs` 并记录该候选为方差内效应。

## 边界

诊断窗口；无能力结论；`SUBMISSION_CONFIG` 不改动。本地 native/contract 为本地
近似判定，非官方 judger。
