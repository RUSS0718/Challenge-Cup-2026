# BTCS Frame v2 structural and fidelity preregistration

状态：`STRUCTURAL_ONLY / RESOURCE_VOID / NO_CAPABILITY_CONCLUSION`

## 方法身份与边界

- method id：`btcs_frame_v2`
- `btcs_v1` 保持 `ARCHIVED_VOID`，其 6/7 raw frame 结果不并入 v2
- GSA `ff040df` 仅为历史观察，不作 control
- 健康对照仍为 `hetero_k5`；只有 hard smoke 阶段才进行同窗比较
- `SUBMISSION_CONFIG` 保持不变；v2 仅通过 `protocol_mode=btcs_frame_v2` opt-in

## 已冻结的实质变化

1. 数值、选择、填空 solver 只要求单行 `FINAL: <答案>`，不要求 `EVIDENCE`。
2. parser 只增加有限兼容：`FINAL:`、`FINAL：`、`最终答案：`、`Final answer:`，以及
   单层 code fence、单个列表前缀和粗体包装；裸数字、任意最后一行、自然语言截断尾部和
   占位符继续拒绝。
3. 证明、推导、解释题仍要求 `FINAL + EVIDENCE + BODY`。
4. trace 增加封闭的 packet diagnostics、`per_solve_final_success`、`selection_source` 和
   `raw_packet_parse_rate`，不保存题面、Prompt、模型正文或凭证。
5. logical calls≤4、HTTP attempts≤5、retry≤1/solve 不变。

## 离线代码门

- 整理后的提交候选全量 unittest：502/502；此前混合工作树记录为 507/507，
  不作为本次提交范围的门结论
- v2 replay 覆盖单行 `FINAL`、有限 Markdown 外壳、proof 正文、诊断计数、选择来源和
  Arbiter 数值输入不带伪造 evidence
- `py_compile`、JSON 序列化、trace 卫生和 `git diff --check` 通过
- 离线门只证明协议结构和工程契约，不证明模型能力

## 固定真实 fidelity 设计（未启动）

输入固定为 `sample_data/complex_capability_freeze_48.jsonl`，全文件 SHA-256：
`57f78259c185623beb144cde29d1c0acad15915404736163481a35e119f25c0e`。
按 `sha256(problem UTF-8)` 升序取前 10 题，选中 idx 为：
`6006, 6034, 6039, 6028, 6004, 6023, 6019, 6041, 6030, 6015`。
不按题目答案、题型或逐题错误调 Prompt。

资源窗口已另立并执行为 `BTCS-FRAME-V2-RESOURCE-001`：workers=1、solver 4096 tokens、
明确 endpoint/model、底层 timeout 和 request deadline；实际 3 个串行请求仅 1/3 成功、
2 timeout，因此按预注册健康门作废，不能启动 fidelity。

真实 fidelity 固定运行这 10 题一轮，不允许追加题目直到过门。每题协议至少发起前两次
solver 请求，目标 raw solver response 数至少 20；实际 response 数在报告中冻结。raw parse rate
只有在实际 solver response 数≥20 时才应用 `≥95%` 观察门；少于 20 只报告
`RAW_SAMPLE_INSUFFICIENT`，不作通过或能力结论。

## 安全门

- 10/10 solve 完成；0 model error、0 deadline、0 orphan
- `per_solve_final_success=100%`，且最终来源只能是显式解析 candidate、合法已有候选的
  Arbiter 选择或基于前缀的明确 continuation；`UNKNOWN` 不得变成答案
- 每题 logical≤4、HTTP≤5、retry≤1
- Arbiter 只能选择 A/B/C；不得创造候选集合之外的新答案
- 任一安全门失败立即 VOID；不降 token、不增并发、不增 retry、不改名复跑

安全门通过且 raw solver response 数达到 20 后，才可评价预注册的 raw parse rate；该结果仍不是
能力结论。只有后续独立 hard smoke 通过，才考虑 `BTCS-LEGACY84-001`。
