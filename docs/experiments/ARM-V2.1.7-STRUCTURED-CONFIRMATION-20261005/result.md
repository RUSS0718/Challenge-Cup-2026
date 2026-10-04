# ARM v2.1.7 structured confirmation — result

状态：`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

V01–V10 完成预注册的 10 轮、50 条记录；两臂均 25 题、0 model error。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断率 | confirmation 激活 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.1.7-structured-confirmation` | 24 | 0 | 1 | 42 | 1.68 | 0.000 | 17 / 25 |
| 基线 `arm-v2.1.4-cfr` | 24 | 0 | 1 | 42 | 1.68 | 0.000 | — |

## 逐题配对转移

| 候选 \ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 24 | 0 | 0 |
| incorrect | 0 | 0 | 0 |
| invalid | 0 | 0 | 1 |

唯一的 invalid 是 `fresh_confirm_15`，两臂均输出等价集合表面 `\{-2,8\}`，因此没有
候选到基线的结果转移；这属于当前本地 judge 的表示规范差异，不是 v2.1.7 的差分。

## 门判定

- VOID 门：通过；两臂 0 model error，题集 SHA、范围和 manifest 均存在。
- 激活门：通过；候选 25 题中 17 题进入 `structured_challenger_confirmation`。
- 安全门：通过；确认请求上限 1,024 tokens，只接受 incumbent 等价值，平均调用数与基线相同。
- 探索收益门：失败；候选没有减少 invalid，也没有产生 correct/incorrect 净变化。

因此 v2.1.7 保持默认关闭，不修改 `SUBMISSION_CONFIG`、GitCode main 或官方 selector。它验证了
“确认已有值而不生成替代答案”的代码路径，但没有产生能力或 invalid 收益证据。机器版逐轮、
截断和成本字段见 [`comparison.json`](comparison.json)；原始 answers 和 trace 保留在被忽略的
`artifacts/arm-v217-structured-confirmation-20261005/`。
