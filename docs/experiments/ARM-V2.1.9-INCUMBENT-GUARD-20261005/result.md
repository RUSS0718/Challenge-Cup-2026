# ARM-V2.1.9-INCUMBENT-GUARD-20261005 — result

状态：`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

Z01–Z10 完成 10 轮、25 条配对记录、50 条臂记录；两臂均无 model error。候选与基线除
`arm_harness_version` 外配置相同，题集为与 X/Y 窗口不重叠的 OlymMATH、AIME 和 HLE
Math 题目。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 | guard 激活 | finalizer 激活 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.1.9-incumbent-guard` | 6 | 15 | 4 | 50 | 2.00 | 0 | 25 / 25 | 0 |
| 基线 `cfr-external-pressure` | 2 | 17 | 6 | 50 | 2.00 | 1 | — | — |

候选每一次 guard 激活都使用原 CFR `challenger` backend；没有一次 compact finalizer
激活。因此本窗验证了“完整 incumbent 保留原 Challenger”的触发门，但没有验证缺失/
不完整 Primary 的收束收益。

## 分题集结果

| 题集 | 候选 correct/incorrect/invalid | 基线 correct/incorrect/invalid | 候选截断 | 基线截断 |
| --- | --- | --- | ---: | ---: |
| OlymMATH（Z01/Z03） | 3/7/0 | 1/8/1 | 0 | 1 |
| AIME（Z05） | 2/3/0 | 1/4/0 | 0 | 0 |
| HLE Math（Z07/Z09） | 1/5/4 | 0/5/5 | 0 | 0 |

## 逐题转移与门判定

| 候选 \ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 1 | 4 | 1 |
| incorrect | 1 | 13 | 1 |
| invalid | 0 | 0 | 4 |

逐题转移包含 4 个 `incorrect → correct`、1 个 `invalid → correct`，但也有 1 个
`correct → incorrect`。候选相对基线少 2 个 invalid、多 4 个 correct；这些是本地配对
描述，不能抵消安全门失败，也不能当作官方能力提升。

- **VOID 门：通过但有边界记录。** SymPy 可导入，两臂 0 model error，三套题集 SHA、
  题数和普通 manifest 字段一致；manifest 记录 `working_tree_dirty=true`，因此严格
  clean-tree 晋级校验不适用，本窗不产生发布资格。
- **激活门：通过。** guard 激活 `25/25`；候选所有 guard 请求均为 `challenger`。
- **安全门：不通过。** 出现 1 个 `correct → incorrect`；平均调用数均为 `2.00`。
- **探索收益门：仅作描述。** correct 增加 4、invalid 减少 2，但安全门失败后不计
  入收益晋级。
- **成本门：通过。** 候选与基线均为 50 次模型调用，平均 2.00 次/题。

因此 v2.1.9 保持默认关闭并登记为 `NO_GO`。不修改 `SUBMISSION_CONFIG`、正式 selector、
GitCode main 或官方作品。完整范围、哈希、配置差异、逐题转移和有界 telemetry 见
[`comparison.json`](comparison.json)；原始 answers、report、manifest 和 trace 仍在被
忽略的 `artifacts/arm-v219-incumbent-guard-20261005/`。
