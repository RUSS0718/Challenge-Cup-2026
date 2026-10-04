# ARM-V2.1.9-INCUMBENT-GUARD-20261005 — preregistration

状态：`OPEN`

## 目的与假设

v2.1.8 的独立复验减少了截断事件，但出现了一个 `correct → incorrect` 转移，且
invalid 没有下降。新的假设是：收束器应只负责补齐缺失或不完整答案；当 Primary 已经
形成结构有效且完整的 incumbent（包括带明确答案尾部的截断响应）时，第二次请求必须回到
原 CFR Challenger。这样可以把“收束”与“替换已有答案”分开，避免未经 CFR 异议、定向
修复和 Fresh Review 的答案漂移。

v2.1.9 是一个默认关闭的触发门实验。它不修改正式 selector，不合并 v2.1.5/7 的确认
协议，也不改变 parser、评分器、调用上限或 `SUBMISSION_CONFIG`。

## 唯一变量与预算

- 候选：`arm-v2.1.9-incumbent-guard`，method ID
  `ARM-V2.1.9-INCUMBENT-GUARD-20261005`。
- 对照：`cfr-external-pressure`，即 ARM v2.1.4 CFR。
- 两臂 `harness_attempt_a_max_tokens=1024`、`harness_attempt_b_max_tokens=4096`、
  `harness_total_token_budget=16384`；每题最多一次第二请求。
- 候选与基线的 `asdict` 配置必须只在 `arm_harness_version` 上不同。
- 候选触发 `incumbent_preserving_finalizer_gate` 时必须使用原 CFR Challenger；
  只有 Primary 缺失或不完整时才允许使用 v2.1.8 的 2,048-token compact finalizer。

## 数据与配对

使用三套外部题池中与 v2.1.8 X/Y 窗口不重叠的冻结题目，共 10 轮、50 条配对记录。
候选和基线严格同题、同序、交错运行。

| dataset | rows | SHA-256 |
| --- | ---: | --- |
| `external_olymmath` | 176 | `b9d26b6568fc7032fe70b7b6592176c3ed011074be2ec9dff3bd3ccbef41c610` |
| `external_aime` | 52 | `e39108744b5b0548fccfc28a089ddd1cccd0821e7235a6f2e18fa74449cd8315` |
| `external_hle` | 80 | `51cf0dd6349ba387ed26b1641c38ac47ef82891bc7a607b502aa8848fccaf4f8` |

Z01/Z02 和 Z03/Z04 使用两组新的 OlymMATH 题；Z05/Z06 使用新的 AIME 题；
Z07/Z08 和 Z09/Z10 使用新的 HLE Math 题。题目选择由
`incumbent_guard_round_specs()` 固定，运行前必须验证题目 ID、数量、哈希和与 X/Y
窗口不相交。

范围固定为 `local_replay`；标准答案只留在宿主评分器，模型请求、metadata 和 trace
不得包含 gold。

## 预注册门

1. **VOID 门**：SymPy 预检失败、题集/题数/SHA/manifest 缺失或不一致，或任一臂
   model error 超过 10%，窗口不产生能力结论。
2. **激活门**：候选至少出现一次
   `incumbent_preserving_finalizer_gate`。零次只登记
   `ENGINEERING_NOT_ACTIVATED`，不能解释为收益或失败。
3. **安全门**：完整 incumbent 触发 guard 时，第二请求的 backend 必须为
   `challenger`；候选不得出现净 `correct → incorrect`，不得增加每题请求上限；
   平均调用数相对基线增加不超过 0.5。
4. **探索收益门**：在安全门通过后，候选相对基线至少减少 2 个 invalid 或增加
   2 个 correct，且 incorrect 不增加。通过只表示进入后续独立复验，不触发默认晋升。
5. **晋升边界**：无论结果如何，不修改 `SUBMISSION_CONFIG`、正式 selector、
   GitCode main 或官方作品；所有 raw answers、manifest 和 report 留在被忽略的
   `artifacts/` 目录。

## 运行与证据

```powershell
.venv\Scripts\python.exe scripts/run_robustness_matrix.py `
  --rounds Z01,Z02,Z03,Z04,Z05,Z06,Z07,Z08,Z09,Z10 `
  --output-dir artifacts/arm-v219-incumbent-guard-20261005 `
  --matrix-id ARM-V2.1.9-INCUMBENT-GUARD-20261005
```

每轮必须保留 `run_manifest.json`、`report.json`、`answers.jsonl` 和压缩 trace。提交只
保留本预注册、配对 comparison、result 和注册表处置；运行结果不能被写成官方隐藏集成绩。
