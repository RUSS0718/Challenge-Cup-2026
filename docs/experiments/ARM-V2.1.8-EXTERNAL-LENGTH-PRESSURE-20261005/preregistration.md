# ARM-V2.1.8 external length-pressure window — preregistration

状态：`VOID`

> 本预注册对应的首次 X01–X10 运行已作废：runner 当时没有在端点调用前验证本地
> SymPy 评分依赖，且候选/基线的第二次预算实际为 2,048/4,096，违反了唯一变量约束。
> 该目录中的 comparison 只保留审计痕迹，不进入能力或收益判断。纠正后的独立窗口见
> [`ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002`](../ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002-20261005/preregistration.md)。

## 假设

官方 100 题报告记录了 73 个 invalid，且 200 次请求中有 70 次以
`finish_reason=length` 结束。v2.1.8 只改变 Primary 不完整或截断时的第二次请求：
改用一次最多 2,048 token 的 answer-only finalizer。若短收束能把已经形成但未闭合的
答案变成可解析结论，候选应减少 invalid 或截断，而不扩大错误答案和调用成本。

本窗口的 1,024-token Primary 预算是激活压力设计，不能外推为正式提交预算；它只用于
验证机制在三套冻结外部题池上是否真的触发并产生可归因差异。

## 唯一变量与对照

- 候选：`arm-v2.1.8-external-pressure`，ARM v2.1.8，Primary 1,024 token，
  compact finalizer 上限 2,048 token。
- 对照：`cfr-external-pressure`，ARM v2.1.4 CFR，Primary 同为 1,024 token，
  第二次请求保持普通 Challenger，预算 4,096 token。
- 两臂共享题目顺序、题集、并发数、超时、分类器、抽取器、judge 和宿主评分器；gold
  只留在宿主端。
- 不修改 `SUBMISSION_CONFIG`、正式 selector、答案库或发布指针。

## 数据与调度

- `sample_data/external_hard_sets/set_a_olymmath_hard.jsonl`
  （176 行，SHA-256 见 `MANIFEST.json`）
- `sample_data/external_hard_sets/set_b_aime.jsonl`
  （52 行，SHA-256 见 `MANIFEST.json`）
- `sample_data/external_hard_sets/set_c_hle_math.jsonl`
  （80 行，SHA-256 见 `MANIFEST.json`）
- X01/X02、X03/X04 使用两组不重叠 OlymMATH 题；X05/X06 使用 AIME；X07/X08、
  X09/X10 使用两组不重叠 HLE Math 题。每组 5 题，候选/基线严格同题配对，共 10 轮、
  50 条记录。
- 范围固定为 `local_replay`；结果不能替代官方隐藏集评测。

## 预注册门

1. **VOID 门**：任一题集、题数、SHA、manifest 范围字段不一致，或任一臂 model error
   超过 10%，窗口无能力结论。
2. **激活门**：候选至少出现一次 `compact_finalizer` trace 事件；0 次只记为
   `ENGINEERING_NOT_ACTIVATED`，不解释为收益或失败。
3. **安全门**：finalizer 每题最多一次，只能输出一个可解析答案或 `UNKNOWN`，不得越过
   v2.1.8 的 2,048-token 上限；候选不得出现净 `correct → incorrect` 损失。
4. **探索收益门**：在激活门和安全门通过后，候选相对基线至少减少 2 个 invalid，或
   至少减少 2 个截断事件；同时不得增加 incorrect。通过只允许进入独立复验，不触发默认晋升。
5. **成本门**：候选平均模型调用数不得比基线增加超过 0.5；若 finalizer 激活，需报告
   触发原因分布、调用数和截断事件。
6. **晋升边界**：任何结果都不修改 `SUBMISSION_CONFIG`、GitCode main 或官方 selector；
   只有新的独立窗口和用户明确授权才可提出发布评审。

## 记录与证据边界

运行命令使用 `scripts/run_robustness_matrix.py --rounds X01,...,X10`，工件写入
`artifacts/arm-v218-external-length-pressure-20261005/`。每轮必须保存 manifest、
answers、report 和压缩 trace；汇总必须包含 `compact_finalizer_activations`、
`compact_finalizer_trigger_reason_counts`、`truncation_count`、invalid、incorrect、
调用数以及逐题候选→基线转移。结果文档明确标记为 `local_replay`，不产生官方能力结论。
