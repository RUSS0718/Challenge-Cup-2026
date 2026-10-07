# FSDF-ITER-AB-001 配对回归窗口结果（迭代第 1 轮）

方法：同题配对双臂，唯一变量 = `fsdf_de_budget_swap_v1`（D/E 预算对调
8192/4096 → 4096/8192，总 18432 与 5 次调用不变）。基线 `v2hd`（当前前沿）vs
候选 `v2hd_bs`。15 题（冻结池 ×5，种子 20260905），先臂逐题轮换，workers=3，
hard-stop 75 min。git_head `0a9bdfd`。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 前沿前移（配对证据支持）`

- 运行：30/30 run 全部完成，0 任务崩溃、0 顶层错误，单进程。

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd（前沿，swap 前） | 1 | 0 | 14 | 1/15 | 13/15 | 429.5s / 573.0s |
| v2hd_bs（预算对调） | 3 | 1 | 11 | 4/15 | 10/15 | 453.1s / 590.5s |

- 配对矩阵：invalid→invalid 11、**invalid→correct 2**（aime-2024-I-8、aime-9）、
  correct→correct 1、invalid→incorrect 1。
- **correct 净增 +2，无 correct→incorrect 反转**。
- E 终答形成 1→4，E 截断 13→10：与"E 截断为天花板约束"假设方向一致。
- 成本：mean 429→453s、P95 573→591s（E 生成了更多内容，符合预期，E 为末阶段无
  跳过暴露）；总 token 与调用上限未放宽。

## 观察与风险

1. **D 侧交接退化可量化**：候选臂 absent 字段实例 29（vs 22）、conflict 13（vs 0）
   ——D 被压到 4096 后截断更频繁，但 E 结果仍改善；若进一步压 D 需警惕交接质量。
2. **E 截断仍 10/15**：8192 也没有让 E 停下来，"纯天花板"解释被削弱，任务量/压缩
   杠杆（让 E 少写推导、紧凑确认）成为下一候选方向。
3. 上轮候选 `fsdf_d_result_to_e` 保持关闭（机制未激活已归档），未参与本窗。

## 边界

诊断窗口（n=15 配对，方向性证据）；无能力结论；本次"前沿前移"仅指迭代循环内的
实验基线选择，**不修改 `SUBMISSION_CONFIG`、不推送 gitcode main**（canary 状态
维持在 507ebd3 的六开关栈）。本地 native/contract 为本地近似判定，非官方 judger。
