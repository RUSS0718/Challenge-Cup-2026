# ARM-V2.1.8 external length-pressure window 002 — preregistration

状态：`OPEN`

## 纠正说明

首次 X01–X10 运行作废：runner 当时没有在网络调用前验证 SymPy 评分依赖，且候选与
基线第二次预算发生了 2,048/4,096 的未登记差异。该窗口使用新的 method ID、独立工件
目录和同一冻结题池；首次窗口不提供先验收益数字，也不纳入本窗评分。

## 假设与唯一变量

官方 100 题报告记录了 73 个 invalid，且 200 次请求中有 70 次以 `finish_reason=length`
结束。v2.1.8 只在 Primary 不完整或截断时把第二次请求切换成一次最多 2,048 token 的
answer-only finalizer；完整 Primary 继续走普通 CFR。若短收束有效，候选应减少 invalid
或截断而不增加 incorrect。

- 候选：`arm-v2.1.8-external-pressure`。
- 对照：`cfr-external-pressure`。
- 两臂均 `harness_attempt_a_max_tokens=1024`、`harness_attempt_b_max_tokens=4096`、
  `harness_total_token_budget=16384`；v2.1.8 的 finalizer 在 harness 内部最多实际请求
  2,048 token。
- 除 `arm_harness_version` 外，候选和基线配置经 `asdict` 精确相等；启动前强制导入
  `sympy`，失败则不创建任何端点调用。
- evaluator、分类器、抽取器、评分器、题面和 gold 位置不变；`SUBMISSION_CONFIG` 保持关闭。

## 数据与调度

使用 `sample_data/external_hard_sets/` 中冻结的 OlymMATH、AIME、HLE Math 三套题池，
与首次窗口相同的 5 个五题组、X01–X10 候选/基线配对。每轮 manifest 记录题集 SHA、
`local_replay` 范围、代码 commit 和 dirty-tree 状态；`.venv` 是唯一评分运行时。

## 预注册门

1. **VOID 门**：SymPy 预检失败、题集/题数/SHA/manifest 缺失，或任一臂 model error 超过
   10%，窗口作废。
2. **激活门**：候选至少出现一次 `compact_finalizer`；零次只登记
   `ENGINEERING_NOT_ACTIVATED`。
3. **安全门**：每题最多一次 finalizer，不超过 2,048 token，且不得出现净
   `correct → incorrect`。
4. **探索收益门**：激活和安全门通过后，候选至少减少 2 个 invalid 或 2 个截断事件，
   且 incorrect 不增加；通过只进入独立复验。
5. **成本门**：候选平均调用数相对基线增加不超过 0.5。
6. **晋升边界**：任何结果都不修改 `SUBMISSION_CONFIG`、GitCode main 或正式 selector。

## 记录

运行工件写入 `artifacts/arm-v218-external-length-pressure-002-20261005/`；提交只保留
本预注册、`comparison.json`、`result.md` 和 registry 记录，raw answers/report/manifest
继续留在被忽略的 artifacts 目录。
