# ARM-V2.1.8 external length-pressure window 002 — result

状态：`EXPLORATORY_GO / REPLICATION_REQUIRED / NO_PROMOTION`

## 聚合结果

纠正后的 X01–X10 完成 10 轮、50 条记录；两臂均 0 model error。SymPy 预检通过，候选
与基线除 `arm_harness_version` 外配置相同，Primary/普通第二次请求预算为 1,024/4,096。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 | finalizer 激活 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.1.8-external-pressure` | 5 | 15 | 5 | 50 | 2.00 | 0 | 3 / 25 |
| 基线 `cfr-external-pressure` | 3 | 17 | 5 | 50 | 2.00 | 3 | — |

候选 finalizer 触发 3 次：`primary_missing` 1 次、`primary_incomplete` 2 次；没有
`primary_truncated` 触发。题集覆盖 OlymMATH、AIME 和 HLE Math 三套冻结外部池，范围是
`local_replay`，不是官方隐藏集评测。

## 分题集结果

| 题集 | 候选 correct/incorrect/invalid | 基线 correct/incorrect/invalid | 候选截断 | 基线截断 |
| --- | --- | --- | ---: | ---: |
| OlymMATH | 3/6/1 | 2/7/1 | 0 | 1 |
| AIME | 2/3/0 | 1/4/0 | 0 | 2 |
| HLE Math | 0/6/4 | 0/6/4 | 0 | 0 |

## 逐题转移与门判定

| 候选 \\ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 3 | 2 | 0 |
| incorrect | 0 | 15 | 0 |
| invalid | 0 | 0 | 5 |

候选相对基线有 2 个 `incorrect → correct`，没有 `correct → incorrect`，invalid 数相同；
截断事件减少 3 个，平均调用数不增加。逐题、触发原因、配置预检和转移见
[`comparison.json`](comparison.json)，完整运行工件见
`artifacts/arm-v218-external-length-pressure-002-20261005/`。

- VOID 门：通过；SymPy 预检通过，两臂 0 model error，题集哈希和 manifest 字段齐全。
- 激活门：通过；候选 `3 / 25` 题触发 finalizer。
- 安全门：通过；每题最多一次 finalizer，硬上限 2,048 token，且无 correct→incorrect 损失。
- 探索收益门：通过；invalid 未增加，incorrect 减少 2，截断事件减少 3。
- 成本门：通过；两臂平均调用均为 2.00。

该结果只允许进入新的独立 paired 复验，不能直接修改 `SUBMISSION_CONFIG`、正式 selector、
GitCode main 或发布指针。v2.1.8 仍保持默认关闭；本地窗口的收益不能外推为官方能力提升。
