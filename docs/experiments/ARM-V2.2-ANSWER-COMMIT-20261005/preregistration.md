# ARM-V2.2-ANSWER-COMMIT-20261005 — preregistration

状态：`COMPLETED / EXPLORATORY_NO_GO / DEFAULT_OFF`

## 目的与假设

2026-10-04 官方 100 题报告记录 `21/6/73`，且 200 次请求有 70 次
`finish_reason=length`。v2.2 测试一个与 v2.1.8/2.1.9 不同的机制：让第一次请求先提交
唯一可解析答案，再输出最多四行核对文字；第二次请求仍沿用 v2.1.4 CFR Challenger。
假设是答案先提交可以减少“推理耗尽但没有终答”的 invalid，同时不会引入可接受的
`correct → incorrect` 损失。

## 唯一变量与对照

- 候选：`arm-v2.2-answer-commit`，`arm_harness_version=v2.2`。
- 对照：`cfr-answer-commit-pressure`，使用 `arm-v2.1.4-cfr`。
- 两臂 `harness_attempt_a_max_tokens=2048`、`harness_attempt_b_max_tokens=4096`、
  `harness_total_token_budget=16384`；只有 ARM harness 版本和第一次请求提示契约不同。
- 两臂均 bank-off、RAG-off、Skill-off、official selector 不变；模型请求不包含 gold。

## 数据与配对

Q01–Q02 使用 5 个新 OlymMATH 记录，Q03–Q04 使用另外 5 个新 OlymMATH 记录，Q05–Q06
使用 5 个新 AIME 记录，Q07–Q08 和 Q09–Q10 各使用 5 个新 HLE Math 记录。候选与基线
同题、同序，共 10 轮、25 条 paired records、50 条 arm records。所有题目均不在已完成的
X/Y/Z 外部压力窗口中。

数据文件与哈希：

| 数据集 | 行数 | SHA-256 |
| --- | ---: | --- |
| `external_olymmath` | 176 | `b9d26b6568fc7032fe70b7b6592176c3ed011074be2ec9dff3bd3ccbef41c610` |
| `external_aime` | 52 | `e39108744b5b0548fccfc28a089ddd1cccd0821e7235a6f2e18fa74449cd8315` |
| `external_hle` | 80 | `51cf0dd6349ba387ed26b1641c38ac47ef82891bc7a607b502aa8848fccaf4f8` |

## 预注册门

1. **VOID 门**：SymPy 预检、题集哈希、题数、paired manifest 或模型错误记录不完整时，
   窗口作废，不产生能力结论。
2. **协议门**：候选每题第一次响应必须记录 `primary_prompt_variant=answer_commit_first_v1`；
   两臂预算和题目必须相同。
3. **安全门**：候选不得出现任何 `correct → incorrect`；不得增加模型错误；每题仍受
   既定调用与 token 上限约束。
4. **探索收益门**：安全门通过后，候选至少减少 2 个 invalid 或 2 个截断事件，且 correct
   不下降；通过只允许继续独立复验，不自动晋升。
5. **成本门**：候选平均调用数相对基线增加不超过 0.5。
6. **晋升边界**：无论结果如何，不修改 `SUBMISSION_CONFIG`、正式 selector、GitCode main
   或官方作品。

## 运行命令

```powershell
python scripts/run_robustness_matrix.py `
  --rounds Q01,Q02,Q03,Q04,Q05,Q06,Q07,Q08,Q09,Q10 `
  --output-dir artifacts/arm-v220-answer-commit-20261005 `
  --matrix-id ARM-V2.2-ANSWER-COMMIT-20261005
```

原始 answers、report、manifest 和 trace 保留在被忽略的 `artifacts/`；提交只保留压缩后的
result、comparison 和注册表记录。

结果：候选 `0/15/10`、基线 `1/15/9`；候选截断事件 `0`、基线 `3`，但出现 1 个
`correct → incorrect`，因此安全门和探索收益门未通过。详见
[`result.md`](result.md) 与 [`comparison.json`](comparison.json)。
