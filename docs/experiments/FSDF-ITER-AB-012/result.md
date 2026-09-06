# FSDF-ITER-AB-012 配对回归窗口结果（迭代第 12 轮，技能弧线末轮）

方法：同题配对双臂，唯一变量 = `fsdf_skill_harness_v1`（强制 harness：D 系统提示 =
宿主预选路线的执行脚本，每步强制 `第N步:` 输出，程序侧完成度遥测，E 获路线核查
附录）。基线 `v2hd_bs_hs_tkoff`（思考关、无 harness）vs 候选 `v2hd_hs_tkh`（思考关
+ harness）。15 题配对（2 run 随进程终止丢失），workers=3。git_head `b7e78df`。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 强制遵从达成但正确率反斥 / 前沿不变`

> 运行事故说明：26/30 run 后 runner 进程被外部终止（无 traceback，4 个在途 run
> 丢失）；report 由已保存记录重算，13/15 对完整。

## 配对结果（native 判定，13 对）

| 臂 | correct | incorrect | invalid | E 终答形成 | E 截断 | 步骤完成 | mean/P95 dur |
| --- | - | - | - | - | - | - | - |
| tkoff（思考关，无 harness） | 3 | 9 | 1 | 12/13 | 1/13 | — | 90.6s / 280.1s |
| tkh（强制 harness） | 2 | 10 | 1 | 12/13 | **0/13** | 11/13 完成 4/4 | 82.4s / 331.2s |

- 配对矩阵：**correct→incorrect 2**（OlymMATH-HARD-58-ZH、aime-9）、
  incorrect→incorrect 6、incorrect→invalid 1、correct→correct 1、invalid→incorrect 1。
- 净 correct **−2，两例反转**。按预注册接受条件（net ≥ 0 零反转）未达成 → 候选反斥。

## 关键发现

1. **强制遵从达成**：13 个 run 中 11 个完成全部 4/4 路线步骤（软提示下声明机制
   0 触发；强制 harness 下模型逐步执行路线）——"把限制拉高让模型遵从 skill"在
   合规层面成功。
2. **但遵从不产生正确率**：harness 臂 correct 2 vs 基线 3，两例反转表明刚性路线
   有时破坏了自由求解能答对的题；E 截断 0/13（harness 输出更紧凑）但无 correct
   收益。技能弧线（迭代 11 软提示、迭代 12 强制）结论一致：**技能机制改变行为
   形态，不改变难题的正确率**。
3. 附带观察：harness 臂 handoff 缺字段 5（vs 基线 0）——路线脚本输出更紧凑但
   字段合规略降；时长 82s vs 91s 相当。

## 边界

诊断窗口；无能力结论；`SUBMISSION_CONFIG` 不改动。本地 native/contract 为本地
近似判定，非官方 judger。技能弧线（迭代 11-12）此后如需重启，须按研究笔记的
结构门/机制门/能力门重新预注册。
