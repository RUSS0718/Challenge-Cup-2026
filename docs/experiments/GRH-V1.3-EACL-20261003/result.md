# GRH v1.3 EACL host replay — result

状态：`NO_GO / NO_CAPABILITY_CONCLUSION`

范围：`local_replay`，固定 221 题回放和冻结 evaluator。该窗口不是官方隐藏集评测。

## 结果

与 GRH v1.1 R3 配对比较时，EACL 的逐题结果为：

| 架构 | correct | incorrect | invalid |
|---|---:|---:|---:|
| GRH v1.1 R3 | 106 | 10 | 105 |
| EACL | 106 | 12 | 103 |

invalid 减少 2，但 incorrect 增加 2，净 correct 增益为 0。EACL 把部分长尾截断问题显式化为
`no_closed_candidate` 或 `unresolved_conflict`，这属于控制平面诊断改善，不等于 solver 能力提升。

## 处置

不晋升为默认路径，不修改 `SUBMISSION_CONFIG`，不把 host replay 的数字写成官方成绩。若重启，
必须提出新的单变量假设、重新预注册题集和 evaluator，并保留正式基线作为同窗对照。
