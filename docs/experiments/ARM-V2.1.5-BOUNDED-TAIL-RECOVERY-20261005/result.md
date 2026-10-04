# ARM-V2.1.5 bounded-tail recovery — result

状态：`ENGINEERING_NOT_ACTIVATED / NO_CAPABILITY_CONCLUSION`

## 结论

B01–B10 完成了预注册的 10 轮、50 题 local replay。候选臂
`arm-v2.1.5-bounded-tail` 与基线 `arm-v2.1.4-cfr` 的聚合结果完全相同：

| 臂 | correct | incorrect | invalid | 模型错误 | 模型调用 |
|---|---:|---:|---:|---:|---:|
| 候选 | 7 | 9 | 9 | 0 | 46 |
| 基线 | 7 | 9 | 9 | 0 | 46 |

候选臂的 `bounded_tail_confirmation` 激活次数为 **0**。因此激活门未通过，
本轮不能判断该机制对能力、invalid 或成本的影响，也不能晋升、修改
`SUBMISSION_CONFIG` 或宣称官方能力提升。

## 逐题配对转移

下表按同题候选臂 → 基线臂统计 50 条记录：

| 候选 \\ 基线 | correct | incorrect | invalid |
|---|---:|---:|---:|
| correct | 6 | 1 | 0 |
| incorrect | 1 | 8 | 0 |
| invalid | 0 | 0 | 9 |

方向性不平衡为候选胜出 1 题、落败 1 题；双侧精确 McNemar 描述性检验为
`p=1.0`。唯一的 `incorrect → correct` 是 B01 的
`OlymMATH-HARD-49-ZH`，唯一的 `correct → incorrect` 是 B05/B06 的
`2024-II-11`；两者都没有触发 bounded-tail confirmation。

## 为什么没有激活

- B03 候选臂的 `OlymMATH-HARD-70-ZH` 在第二次普通调用上出现
  `finish_reason=length`，但主响应已经完整，未满足“主响应截断 + 明确最终答案标记”的门。
- B06 是基线臂，`2024-II-11` 的主响应才出现截断；其候选臂对应题目没有同样的触发条件。
- 50 条候选记录中没有 `answer_complete_reason=answer_complete_truncated_tail` 的可用主候选，
  所以没有发送过 1,024-token 确认请求。

这说明本轮验证了候选路径没有擅自扩大触发范围，但没有验证确认请求在真实端点上的收益。

## 处置与下一步

本轮登记为 `ENGINEERING_NOT_ACTIVATED / NO_CAPABILITY_CONCLUSION`，并保持默认关闭。
下一步只允许执行独立的 length-pressure activation probe，先验证触发、预算上限、
UNKNOWN/冲突的 fail-closed 行为，再决定是否值得重新注册真实端点窗口。探针预注册见
[`ARM-V2.1.5 activation probe`](../ARM-V2.1.5-LENGTH-PRESSURE-ACTIVATION-PROBE-20261005/preregistration.md)。

本文件和 B01–B10 的 manifest 都标记为 `local_replay`；完整答案、raw trace 和逐轮报告留在
被忽略的 `artifacts/` 目录，不代表官方隐藏集成绩。
