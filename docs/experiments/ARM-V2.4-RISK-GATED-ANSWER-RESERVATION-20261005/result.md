# ARM-V2.4-RISK-GATED-ANSWER-RESERVATION-20261005 — result

状态：`VOID / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

U01–U10 完成预注册的 10 轮、25 条 paired records、50 条 arm records。两臂均为 0 model
error，平均调用均为 2.00；候选的 route-gated answer reservation 激活 25/25 次。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.4-risk-gated` | 0 | 21 | 4 | 50 | 2.00 | 2 |
| 对照 `cfr-v2.4-risk-pressure` | 1 | 22 | 2 | 50 | 2.00 | 0 |

候选没有减少 invalid 或截断，且正确数少 1。逐题转移为：20 条
`incorrect → incorrect`、1 条候选 `incorrect → correct` 的回退、2 条
`invalid → invalid`、2 条 `invalid → incorrect`。因此安全门和探索收益门均失败。

## 分题集结果

| 题集 | 候选 correct/incorrect/invalid | 对照 correct/incorrect/invalid |
| --- | --- | --- |
| OlymMATH（U01/U03） | 0/10/0 | 0/10/0 |
| AIME（U05） | 0/4/1 | 1/3/1 |
| HLE Math（U07/U09） | 0/7/3 | 0/9/1 |

## 门判定

- **VOID 门：不通过。** 题目配对、数据哈希和 0 model error 均完整，但 10 个 manifest 都记录
  `working_tree_dirty=true`；严格的 paired provenance 要求干净工作树，因此本窗口不能作为可复现
  能力比较证据。原始分数仅保留为诊断信号，不进入晋升判断。
- **激活门：通过。** 候选 25/25 条记录进入 `risk_gated_answer_commit`；所有外部冻结题都被路由为
  `structured/deep` 或低置信，因此没有真实端点上的 bypass 记录，bypass 只由代码测试覆盖。
- **安全门：不通过。** 出现 1 条候选 incorrect、对照 correct 的回退。
- **探索收益门：不通过。** invalid 从 2 增至 4，correct 从 1 降至 0，截断从 0 增至 2。
- **成本门：通过。** 两臂调用数和预算一致。

结论是 v2.4 保持 `DEFAULT_OFF`，不修改 `SUBMISSION_CONFIG`、正式 selector、GitCode main 或官方作品。
由于 VOID 门失败，不能把候选与对照的分数差异当作能力结论；在诊断层面，答案先行提示没有显示出
把“形成可判答案”转化为正确答案的证据，且候选的截断和 invalid 反而更高。后续窗口必须在干净
工作树上运行，并由汇总器先验证 manifest provenance，再判安全和收益门。

完整门判定、逐题转移、配置边界和 route telemetry 见 [`comparison.json`](comparison.json)；原始 answers、
trace、manifest 和报告保留在被忽略的 `artifacts/arm-v224-risk-gated-20261005/`。
