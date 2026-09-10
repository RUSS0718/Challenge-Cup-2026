# MATH-TYPED-PARSER-CODE-001

状态：零模型代码验收；`CODE_ACCEPTED / DEFAULT_OFF / NO_CAPABILITY_CONCLUSION`。

## 目标

建立按 `ProblemContract.answer_shape` 判断完整性的 typed parser，避免把深题中“有数字/有等号”
的推导片段误当作最终答案。parser 不读取 gold、题号、答案库或题目顺序，不执行任意代码。

## 冻结形状契约

- `single_numeric`：完整单值数字/受限数值表达式；
- `parameterized_expression`：含自由变量且结构闭合的表达式；
- `finite_set`：闭合集合表示；
- `interval_or_range`：闭合区间、不等式范围或成员关系；
- `function_family`：至少一个闭合的函数定义；
- `proof_text`：有明确完成结论且未截断的证明文本。

任何 `finish_reason=length`、多个冲突候选、缺少结构闭合或仅有推导片段均不得成为
`typed_complete`。

## 负例

回放 `MATH-HARNESS-EVAL112-SMOKE-001` 中 7 个非 `UNKNOWN` 输出类别：未完成证明句、
缺少参数的常数、带自然语言的集合断言、无等号的函数片段、未完成证明尾句、未闭合范围
表达式和孤立变量。负例只保存输出类别/文本，不保存 gold，不与具体题号绑定。

## 边界

本窗不调用模型、不实现 Deep 调度、不修改默认配置、不启用 matcher 或答案库；通过后才允许
进入 `MATH-DEEP-FORMATION-PROBE-001`。
