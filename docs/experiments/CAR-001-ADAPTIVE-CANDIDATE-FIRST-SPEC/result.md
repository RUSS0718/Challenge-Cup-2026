# CAR-001 F0 零模型代码门结果

方法：`adaptive_candidate_first_v1`

结论：`CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`

- 12/12 定向用例通过，使用只实现 `chat(messages, temperature, max_tokens)` 的
  `ScriptedClient`，没有连接真实模型端点。
- 首轮唯一候选在一次调用后早停；缺失候选最多追加第二次，再使用一次有界恢复。
- 冲突候选会同时保留，等价候选走确定性合并，不同候选最多一次短裁决；裁决显式
  `UNKNOWN` 时保持 `UNKNOWN`。
- 候选值、占位符、未闭合表达式和空响应均有边界；模型异常只记录脱敏的错误类别。
- 单题最大调用数被限制为 3，token 序列为 `2048/2048/4096`；恢复输入包含有界的
  原题片段，不从截断点继续长推导。
- `ReasoningAgent` 通过 `enable_adaptive_candidate_first` 显式选择该路径；与
  FSDF/FESF 及其他实验答题路径互斥。`SUBMISSION_CONFIG` 未改变，仍为 FSDF v1。
- CAR 路径可读取现有相对路径 `math_routes.json`，只注入一段可接受或拒绝的软路线建议；
  不强制逐步执行，trace 记录 `skill_hint` 事件。
- `py_compile`、`git diff --check` 和全量回归通过；全量回归为 736 项，732 项通过，
  4 项明确跳过，0 项 failure/error。跳过项属于现有归档 BTCS 测试。

本结果只证明 CAR-001 的宿主编排、预算、互斥和输出卫生契约；不产生 thinking-on
模型的数学能力、正确率、截断率或官方得分结论。F1 健康探针、F2 探索窗和 F3 fresh
A/B 尚未运行。
