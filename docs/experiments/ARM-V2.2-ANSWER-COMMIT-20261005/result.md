# ARM-V2.2-ANSWER-COMMIT-20261005 — result

状态：`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

Q01–Q10 完成预注册的 10 轮、25 条配对记录、50 条臂记录；候选和基线均为 0 model error。
两臂使用相同题目、相同 2,048/4,096 请求预算和 16,384 token 总预算；候选第一次请求的
25/25 条记录均带有 `primary_prompt_variant=answer_commit_first_v1`，第二次请求均继续使用
CFR Challenger。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.2-answer-commit` | 0 | 15 | 10 | 50 | 2.00 | 0 |
| 基线 `cfr-answer-commit-pressure` | 1 | 15 | 9 | 50 | 2.00 | 3 |

## 分题集结果

| 题集 | 候选 correct/incorrect/invalid | 基线 correct/incorrect/invalid | 候选截断 | 基线截断 |
| --- | --- | --- | ---: | ---: |
| OlymMATH（Q01/Q02） | 0/4/1 | 1/3/1 | 0 | 1 |
| OlymMATH（Q03/Q04） | 0/2/3 | 0/2/3 | 0 | 1 |
| AIME（Q05/Q06） | 0/4/1 | 0/4/1 | 0 | 1 |
| HLE Math（Q07/Q08） | 0/4/1 | 0/4/1 | 0 | 0 |
| HLE Math（Q09/Q10） | 0/1/4 | 0/2/3 | 0 | 0 |

## 逐题转移与门判定

| 候选 \ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 0 | 1 | 0 |
| incorrect | 0 | 14 | 1 |
| invalid | 0 | 0 | 9 |

候选相对基线没有产生 `incorrect → correct` 或 `invalid → correct`，出现 1 个
`correct → incorrect`，以及 1 个 `incorrect → invalid`。截断事件从 3 降到 0，但 invalid
从 9 增至 10，correct 从 1 降至 0；平均调用数保持 2.00。

- **VOID 门：通过。** SymPy 依赖已验证；10 个 manifest、题集 SHA、配对题数和 0 model error
  均完整。manifest 记录 `working_tree_dirty=true`，因此本地窗口不构成干净树发布资格，但不
  改写本次配对结果。
- **协议门：通过。** 候选 25/25 条记录带有 `answer_commit_first_v1`；两臂题目、首轮/次轮
  token 上限、总预算和调用数一致，gold 未传给模型。
- **安全门：不通过。** 存在 1 个 `correct → incorrect`。
- **探索收益门：不通过。** 截断减少 3 个，但 correct 下降 1 个且 invalid 增加 1 个；因此
  没有满足“correct 不下降”的预注册收益条件。
- **成本门：通过。** 两臂平均调用均为 2.00，候选增量为 0.00。

因此 v2.2 保持 `DEFAULT_OFF`，不修改 `SUBMISSION_CONFIG`、正式 selector、GitCode main 或
官方作品。完整逐轮、逐题转移、预算和协议审计见
[`comparison.json`](comparison.json)；原始 answers、report、manifest 和 trace 仍在被忽略的
`artifacts/arm-v220-answer-commit-20261005/`。

本地 runner、judge 和端点复放不能替代官方隐藏集评测；本结果不能宣称数学能力提升，也不能
因为截断减少就宣称有效率提升。
