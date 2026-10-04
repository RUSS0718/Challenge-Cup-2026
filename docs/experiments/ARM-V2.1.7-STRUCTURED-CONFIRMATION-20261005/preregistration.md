# ARM-V2.1.7-STRUCTURED-CONFIRMATION-20261005

状态：`OPEN`

## 假设

官方 100 题报告显示 73 个 invalid，且 200 次请求中 70 次以
`finish_reason=length` 结束。v2.1.4 的 Challenger 仍可能生成第二个答案并把冲突送入
修复/验证路径。若第二次请求只对已有 incumbent 做结构化、有限确认，且 PASS 必须精确
复述 incumbent，则可以减少无关的候选漂移，同时不扩大 evaluator 接受面。

## 唯一变量

- 候选：`arm-v2.1.7-structured-confirmation`。
- 对照：`arm-v2.1.4-cfr`。
- 两臂共用 `harness_attempt_a_max_tokens=1024`、`harness_attempt_b_max_tokens=1024`、
  `harness_total_token_budget=8192`，共享题目顺序、并发和超时。
- 候选第二次响应必须是 JSON；只有 `status=PASS` 且 `confirmed_value` 与 incumbent
  等价时才形成共识。FAIL、UNKNOWN、JSON 缺失、答案标记、不同值都不能产生新候选。
- evaluator、题目分类、答案抽取和评分器不作修改；`SUBMISSION_CONFIG` 保持不变。

## 数据与调度

- 新鲜题集：`sample_data/arm_v217_fresh_confirmation_25.jsonl`
- 题集 SHA-256：`AB959B997294EBEE36A0010D77FC60DF16ACE1A8D01783C0B461470BF7137C2F`
- 25 个本地题目分为 5 组，每组 5 题；V01/V02、V03/V04、V05/V06、V07/V08、V09/V10
  分别是候选/基线同题配对，共 10 轮、50 条记录。
- 范围固定为 `local_replay`，标准答案只留在宿主评分器；结果不代表官方隐藏集成绩。

## 预注册门

1. **VOID 门**：题集 SHA、题数、manifest 范围字段缺失，或任一臂 model error 超过 10%，
   则窗口无能力结论。
2. **激活门**：候选至少出现一次 `structured_challenger_confirmation`；0 次只记为
   `ENGINEERING_NOT_ACTIVATED`，不解释为收益或失败。
3. **安全门**：候选不得接受与 incumbent 不等价的确认值；每题调用不超过 v2.1.4
   上限，平均调用数相对基线增加不超过 0.5。
4. **探索收益门**：候选相对基线至少减少 2 个 invalid，且不得出现净
   `correct → incorrect` 损失；该门只允许进入独立复验，不触发默认晋升。
5. **晋升边界**：任何结果都不修改 `SUBMISSION_CONFIG`、GitCode main 或官方 selector；
   只有第二个独立窗口通过后，才可提出新的架构发布评审。

## 记录与证据边界

每轮写入 `artifacts/arm-v217-structured-confirmation-20261005/<round>/`。提交只保留本
预注册、压缩结果和处置；answers、report、manifest 和 raw response 留在被忽略的
`artifacts/`。逐题转移、截断率、调用成本和 confirmation 激活数必须从这些工件重算。
