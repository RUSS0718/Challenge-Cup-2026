# ARM-V2.1.8 external length-pressure replication — preregistration

状态：`OPEN`

## 目的与假设

这是纠正窗口 `ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002-20261005` 的独立 paired
复验。它使用同一机制、同一调用预算和三套冻结外部题池中未被 X01–X10 选中的题目，
因此不能把 X 窗口的结果当作本窗的先验数字。v2.1.8 只在 Primary 不完整或截断时把
第二次请求切换为一次最多 2,048 token 的 answer-only finalizer；完整 Primary 继续走
普通 CFR。若短收束具有可迁移收益，候选应减少 invalid 或截断而不增加 incorrect。

- 候选：`arm-v2.1.8-external-pressure`。
- 对照：`cfr-external-pressure`。
- 两臂均 `harness_attempt_a_max_tokens=1024`、`harness_attempt_b_max_tokens=4096`、
  `harness_total_token_budget=16384`；候选 finalizer 的实际硬上限为 2,048 token。
- 除 `arm_harness_version` 外，候选和基线配置必须经 `asdict` 精确相等；运行前导入
  `sympy`，失败则不创建任何端点调用。
- evaluator、分类器、抽取器、评分器、题面和 gold 位置不变；`SUBMISSION_CONFIG`、
  正式 selector、GitCode main 和发布指针保持不变。

## 数据与配对

数据文件在运行前冻结，完整文件哈希如下：

| dataset | rows | SHA-256 |
| --- | ---: | --- |
| `external_olymmath` | 176 | `b9d26b6568fc7032fe70b7b6592176c3ed011074be2ec9dff3bd3ccbef41c610` |
| `external_aime` | 52 | `e39108744b5b0548fccfc28a089ddd1cccd0821e7235a6f2e18fa74449cd8315` |
| `external_hle` | 80 | `51cf0dd6349ba387ed26b1641c38ac47ef82891bc7a607b502aa8848fccaf4f8` |

Y01/Y02 和 Y03/Y04 使用两组新的、不与 X 窗口重叠的 OlymMATH 题；Y05/Y06 使用
新的 AIME 题；Y07/Y08 和 Y09/Y10 使用新的 HLE Math 题。每组 5 题，候选和基线
严格同题同序，共 10 轮、50 条记录。具体选择由
`external_pressure_replication_round_specs()` 生成，并在测试中检查每个 item_id
存在、与 X 窗口不相交、候选/基线成对一致。

运行范围固定为 `local_replay`；标准答案只留在宿主评分器，模型请求不包含 gold。

## 预注册门

1. **VOID 门**：SymPy 预检失败、题集/题数/SHA/manifest 缺失或不一致，或任一臂
   model error 超过 10%，窗口作废，不出能力结论。
2. **激活门**：候选至少出现一次 `compact_finalizer` trace 事件；零次只登记
   `ENGINEERING_NOT_ACTIVATED`，不解释为收益或失败。
3. **安全门**：每题最多一次 finalizer，不超过 2,048 token，只能形成可解析答案或
   `UNKNOWN`；候选不得出现净 `correct → incorrect` 损失。
4. **探索收益门**：激活门和安全门通过后，候选至少减少 2 个 invalid 或 2 个截断
   事件，且 incorrect 不增加；通过只表示复验支持，仍不触发默认晋升。
5. **成本门**：候选平均模型调用数相对基线增加不超过 0.5；必须报告触发原因、调用
   数和截断事件。
6. **晋升边界**：无论结果如何，不修改 `SUBMISSION_CONFIG`、正式 selector、
   GitCode main 或官方作品。

## 可复现记录

运行命令使用：

```powershell
python scripts/run_robustness_matrix.py `
  --rounds Y01,Y02,Y03,Y04,Y05,Y06,Y07,Y08,Y09,Y10 `
  --output-dir artifacts/arm-v218-external-length-pressure-replication-20261005 `
  --matrix-id ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-REPLICATION-20261005
```

每轮必须保存 `run_manifest.json`、`report.json`、`answers.jsonl` 和压缩 trace；提交只
保留本预注册、配对 comparison、result 和 registry 记录，raw 运行工件继续写入被忽略的
`artifacts/` 目录。所有结论必须明确标为 `local_replay`，不能替代官方隐藏集评测。
