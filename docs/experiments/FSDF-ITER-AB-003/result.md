# FSDF-ITER-AB-003 配对回归窗口结果（迭代第 3 轮）

方法：同题配对双臂，唯一变量 = `fsdf_mandatory_final_d_v1`（DEEPEN_PROMPT_MFD：
CANDIDATE_D 后立即强制 FINAL_D、置于 DERIVED 之前）。基线 `v2hd_bs`（前沿）vs
候选 `v2hd_bs_mfd`。15 题配对，workers=3，hard-stop 75 min。git_head `e2b0eeb`。
30/30 run 完成，0 崩溃 0 顶层错误。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 机制激活门失败 → 候选被预注册反斥 / 前沿不变`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断 | D 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - | - |
| v2hd_bs（前沿） | 4 | 1 | 10 | 5/15 | 10/15 | — | 386.3s / 422.3s |
| v2hd_bs_mfd（强制 FINAL_D） | 4 | 2 | 9 | 6/15 | 10/15 | **15/15** | 372.5s / 426.7s |

- 配对矩阵：invalid→correct 1、correct→invalid 1、invalid→incorrect 1、
  correct→correct 3、incorrect→incorrect 1、invalid→invalid 8。净增 0。
- **机制激活门（M1）失败**：deep_final 有值仅 **1/15**（预注册门槛 ≥5）。
- 安全门（M2）形式上通过：无 correct→incorrect 反转（但有 correct→invalid 与
  invalid→incorrect 各 1，对消）。

## 关键发现

1. **强制输出字段加剧截断**：MFD 臂 D 截断 15/15（每题都被 4096 截断），交接
   absent 字段实例 42（vs 基线 34）——在预算不变的 D 上增加强制输出项，挤占了
   推导与后续字段的预算，交接产物反而恶化。prompt 级"要求更多字段"与"预算约束"
   在 D=4096 下不可兼得。
2. deep_final 路径仅 1 次激活（hle-6720f01e936e8e4575f4f3f4），未能转化足够
   E-failed run。
3. 前沿配置 v2hd_bs 跨三轮窗 correct：3 / 2 / 4（均值 ~3，摇摆题持续翻转）——
   方差观察进一步确认。

## 边界

诊断窗口；无能力结论；前沿保持 `v2hd_bs`，`SUBMISSION_CONFIG` 不改动。
本地 native/contract 为本地近似判定，非官方 judger。
