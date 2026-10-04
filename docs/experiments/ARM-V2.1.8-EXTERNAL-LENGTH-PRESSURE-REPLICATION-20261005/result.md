# ARM-V2.1.8 external length-pressure replication — result

状态：`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

Y01–Y10 共完成 10 轮、50 条配对记录；两臂均无 model error。SymPy 预检通过，题集
哈希、范围字段和运行 manifest 齐全；候选与基线除 `arm_harness_version` 外配置相同。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 | finalizer 激活 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.1.8-external-pressure` | 3 | 15 | 7 | 50 | 2.00 | 0 | 3 / 25 |
| 基线 `cfr-external-pressure` | 3 | 15 | 7 | 50 | 2.00 | 2 | — |

候选 finalizer 触发 3 次：`primary_missing` 2 次、`primary_incomplete` 1 次；没有
`primary_truncated` 触发。候选把截断事件减少了 2 个，但 invalid、incorrect、correct
和平均调用数均未改善。

## 分题集结果

| 题集 | 候选 correct/incorrect/invalid | 基线 correct/incorrect/invalid | 候选截断 | 基线截断 |
| --- | --- | --- | ---: | ---: |
| OlymMATH | 2/5/3 | 1/6/3 | 0 | 1 |
| AIME | 1/4/0 | 2/3/0 | 0 | 0 |
| HLE Math | 0/6/4 | 0/6/4 | 0 | 1 |

## 逐题转移与门判定

| 候选 \\ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 2 | 1 | 0 |
| incorrect | 1 | 14 | 0 |
| invalid | 0 | 0 | 7 |

逐题转移包含 1 个 `incorrect → correct` 和 1 个 `correct → incorrect`。候选每题最多
触发一次 finalizer，实际硬上限为 2,048 token，平均调用与基线相同；但存在
`correct → incorrect`，因此不能把截断下降视为无损收益，安全门不通过。invalid 未下降，
故本窗不能确认 v2.1.8 的可迁移能力收益。

- VOID 门：通过；SymPy 可导入，两臂 0 model error，三套题集 SHA、题数和 manifest
  范围字段一致。
- 激活门：通过；候选 `3 / 25` 题触发 finalizer。
- 安全门：不通过；存在 1 个 `correct → incorrect`，即使同时有 1 个反向转移也不能
  当作无损。
- 探索收益门：不通过；invalid 没有减少，只有截断事件减少 2 个，且安全门已失败。
- 成本门：通过；两臂平均调用均为 2.00。

该独立复验没有支持晋升。v2.1.8 保持默认关闭，不修改 `SUBMISSION_CONFIG`、正式
selector、GitCode main 或发布指针。完整逐题、触发原因、哈希和配置预检见
[`comparison.json`](comparison.json)；原始 answers、report、manifest 和 trace 保留在
被忽略的 `artifacts/arm-v218-external-length-pressure-replication-20261005/`。
