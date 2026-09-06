# FSDF-ITER-AB-010 配对回归窗口结果（迭代第 10 轮，循环末轮）

方法：同题配对双臂，唯一变量 = `fsdf_thinking_off_v1`（client 级思考开关：候选臂
thinking_mode=False，基线臂 = 服务端默认；其余全部相同）。基线 `v2hd_bs_hs`（前沿）
vs 候选 `v2hd_bs_hs_tkoff`。15 题配对，workers=3，hard-stop 75 min。git_head
`b7e78df`。30/30 run 完成，0 崩溃 0 顶层错误。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 机制门决定性通过 + 分数杠杆否定 / 前沿不变（循环按用户指示结束）`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断 | A/B/C/D 截断 | mean/P95 dur |
| --- | - | - | - | - | - | - | - |
| v2hd_bs_hs（思考默认） | 3 | 1 | 11 | 4/15 | 11/15 | 93-100% length | 472.0s / 571.9s |
| v2hd_bs_hs_tkoff（思考关） | 3 | **10** | **2** | **13/15** | **1/15** | **0-13%（基本消失）** | **100.9s** / 267.7s |

- 配对矩阵：**invalid→incorrect 7**、correct→incorrect 2（OlymMATH-HARD-61-EN、
  hle-6720f01e936e8e4575f4f3f4 两例反转）、invalid→correct 2（aime-2024-I-8、
  aime-9）、correct→correct 1、incorrect→incorrect 1、invalid→invalid 2。
- 净 correct **0**（3=3）；incorrect 1→10；invalid 11→2；时长降 4.7 倍。

## 双重判定

1. **机制门决定性通过（用户假设证实）**：思考关闭后全阶段截断基本消失
   （A/B/C stop 14-15/15，E 1/15），单题耗时降 4.7 倍——**思考模式（在输出流内
   消耗同一份 completion 预算）是截断的主因（探针与全阶段数据一致）**。截断率对预算不敏感之谜、
   提示词塑形无效之谜，全部由此解释。
2. **分数杠杆否定**：关思考把"被截断保护住的 run"变成"快速自信的错误答案"
   （invalid→incorrect ×7、correct→incorrect ×2），correct 净增 0。拒绝无效答案的规则提供保护，但截断本身也会破坏原本可能完成的答案；
   关思考后的能力取舍（本窗 2 例 correct→incorrect、2 例 invalid→correct）
   不能反推原模式下"必然无法解出"。另：候选臂存在 5 次阶段内部 timeout，
   "0 顶层错误"不等于无调用异常。按预注册反斥（≥1 correct→incorrect 反转 + net ≤ 0）→ 不入前沿。

## 对循环的总结意义

十轮迭代把杠杆空间测绘完毕：截断=思考模式的产物（环境级，可通过 client 开关
消除），但消除截断不带来正确率；真正的正确率瓶颈（难题本身不会做）未被任何
本地单变量杠杆触及。前沿 `v2hd_bs_hs` 保持不变；`SUBMISSION_CONFIG`（canary
六开关栈）保持 507ebd3 状态。

## 边界

诊断窗口；无能力结论。**迁移性警示**：官方平台 client 的思考开关可控性未知——
若平台默认思考开启，官方路径同样背负截断税；若讨论在官方路径关闭思考，需先
评估"快速错误答案"对计分口径的影响（纯 correct 计数下中性，任何精确率惩罚下
有害）。本地 native/contract 为本地近似判定，非官方 judger。
