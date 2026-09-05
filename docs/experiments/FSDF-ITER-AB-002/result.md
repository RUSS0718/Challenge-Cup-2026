# FSDF-ITER-AB-002 配对回归窗口结果（迭代第 2 轮）

方法：同题配对双臂，唯一变量 = `fsdf_finish_compact_final_v1`（E 紧凑输出 +
得到可确认答案立即 FINAL 并停止；文本 FINISH_PROMPT_COMPACT_V2）。基线 `v2hd_bs`
（前沿）vs 候选 `v2hd_bs_cf`。15 题（冻结池 ×5，种子 20260905），先臂逐题轮换，
workers=3，hard-stop 75 min。git_head `3c23f62`。30/30 run 完成，0 崩溃 0 顶层错误。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 候选被预注册反斥条件证伪 / 前沿不变`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd_bs（前沿） | 2 | 1 | 12 | 3/15 | 11/15 | 384.6s / 433.1s |
| v2hd_bs_cf（紧凑提示） | 3 | 1 | 11 | 4/15 | 11/15 | 388.5s / 441.9s |

- 配对矩阵：invalid→correct 2（aime-2024-I-8、aime-9）、correct→correct 1、
  incorrect→incorrect 1、**correct→invalid 1**、invalid→invalid 10。
- correct 净增 +1、无 correct→incorrect 反转，但有 1 例 correct→invalid（真实损失）。

## 判定：预注册反斥条件触发，前沿不前移

设计时预登记的反斥条件："若 E 终答形成仍 ≤4/15 且截断 ~10/15 → 紧凑化指令被忽略，
提示词级任务塑造被证伪"。实际：E 终答形成 4/15（=前沿），截断 11/15（未降）——
**机制主指标未达成**；+1 净增在噪声量级内（见下），不足以覆盖 correct→invalid 损失。
前沿保持 `v2hd_bs`。

## 方法学观察（对后续迭代重要）

1. **同配置跨窗方差与候选效应同量级**：v2hd_bs 在迭代 1（3 correct）与本窗基线臂
   （2 correct）为同一配置同题重跑，差异 1 题；aime-2024-I-8 与 aime-9 两题在历次
   窗口中反复翻转。单窗净增 ±1-2 不能作为稳健结论，后续前沿前移需要跨窗复现或
   更大的净增。
2. D 侧字段冲突实例两臂差异大（18 vs 31），D 提示相同——进一步证明 run-to-run
   方差主要来自模型输出的随机性，而非臂间差异。
3. E 截断在 8192 下维持 ~11/15：任务自延展假设部分成立，但紧凑指令未降低截断率。

## 边界

诊断窗口；无能力结论；前沿不变意味着 `SUBMISSION_CONFIG`（canary 六开关栈）与
迭代基线均不改动。本地 native/contract 为本地近似判定，非官方 judger。
