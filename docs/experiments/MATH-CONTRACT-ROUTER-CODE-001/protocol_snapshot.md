# MATH-CONTRACT-ROUTER-CODE-001

状态：零模型代码验收；`CODE_ACCEPTED / DEFAULT_OFF / NO_CAPABILITY_CONCLUSION`。

## 目标

在同一个 `ConstraintFitOrchestrator` seam 内加入双轴 `ProblemContract`，把答案表示形状
与推理风险分开判断。此窗不调用模型、不运行真实题集、不实现 Deep 解题流程。

## 冻结接口

`ProblemContract` 只暴露：

- `answer_shape`：`single_numeric`、`parameterized_expression`、`finite_set`、
  `interval_or_range`、`function_family`、`proof_text`、`unknown`；
- `reasoning_risk`：`direct`、`structured`、`deep`；
- `route_confidence`：`high`、`medium`、`low`。

`HostRouter.route()` 额外返回 `lane` 和 `target`：direct single-answer 进入原 Harness；
Deep lane 只有显式 `deep_enabled=True` 才进入，默认关闭；proof/低置信 mixed 保守回退。

## 验收范围

- direct 单值与 deep 单值必须区分；
- 参数表达式、有限集合、范围、函数族和 proof text 必须分类；
- 低置信 mixed 必须回退；
- metadata 中伪造 answer 不得影响 contract；
- deep lane 关闭时不得改变现有 direct parity；
- `ProblemContract` 必须可 JSON 序列化；
- 5 次调用/token 预算、默认 `SUBMISSION_CONFIG` 和答案库边界不改变。

## 边界

不实现 typed parser、Deep lane 调度、formation、真实端点调用、答案库命中、
`SUBMISSION_CONFIG` 修改或远程发布。
