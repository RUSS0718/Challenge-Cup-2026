# FSDF-ITER-AB-011 三臂配对回归窗口结果（迭代第 11 轮）

方法：同题配对三臂（15 题 × 3 = 45 run，先臂逐题轮换），workers=3，hard-stop
110 min。git_head `8a2309f`。45/45 run 完成，0 崩溃 0 顶层错误。
臂：`v2hd_bs_hs`（前沿，思考默认）/ `v2hd_bs_hs_tkoff`（前沿+思考关）/
`v2hd_hs_sr`（前沿+思考关+`fsdf_skill_routes_v1` 路由层）。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 思考关三重确认（截断消除、correct 无增益） / 技能路由弱信号 / 前沿不变`

## 三臂结果（native 判定，15 对/两两比较）

| 臂 | correct | incorrect | invalid | E 终答形成 | E 截断 | A/B/C/D 截断 | mean dur |
| --- | - | - | - | - | - | - | - |
| v2hd_bs_hs（前沿） | 2 | 1 | 12 | 3/15 | 11/15 | 12/15/15/4 | 453.4s |
| v2hd_bs_hs_tkoff（思考关） | 1 | 13 | 1 | 14/15 | 0/15 | 1/1/1/2 | 85.0s |
| v2hd_hs_sr（思考关+技能路由） | 2 | 13 | 0 | 15/15 | 0/15 | 0/0/0/3 | 85.7s |

两两配对：前沿 vs tkoff net −1；前沿 vs sr net 0；**tkoff vs sr net +1**
（incorrect→correct ×1，技能层的弱正向信号，n=15 在噪声带内）。

## 关键发现

1. **思考关三重确认**：截断在全部阶段基本消失（tkoff 臂 A/B/C/D/E = 1/1/1/2/0），
   时长 5.3×下降；但 correct 仍在噪声带（1-2），incorrect 爆炸（13/15）——
   无思考模型在难题上产出"快速完整但错误"的解答。correct→incorrect 反转再现
   （1 例）。
2. **技能路由的声明机制再次零触发**（SELECTED_SKILL 0 次，与迭代 0/9 的"可选
   声明不触发"模式一致）；分数上 tkoff vs sr 净 +1 为弱信号。路由层唯一的客观
   变化：D 截断 2→3（路线正文要求更多输出）。
3. **逐阶段截断全景**（修复对齐后首次完整）：前沿臂 A 12/B 15/C 15/D 4/E 11；
   思考关臂全部 ≤2。思考默认模式下 B/C 阶段 100% 截断——计划叙述从未完整产出。
4. **待用户决策**：官方 canary（v2hd_dre）确认回归 7/112（correct 减半）；另一
   窗口建议恢复 v1 为正式对照——发布状态变更未执行，等用户明确授权。

## 边界

诊断窗口（n=15/臂配对）；无能力结论；`SUBMISSION_CONFIG` 不改动。本地
native/contract 为本地近似判定，非官方 judger。
