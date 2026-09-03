# V5-HARD20-TYPED-CAPSULE-001 结果报告

状态：**EXPLORATORY_NO_GO**

## 1. 窗口处置

- 原始首轮目录：`V5-HARD20-TYPED-CAPSULE-001`
- 首轮因 runner 错误传入 `retry=0`，客户端执行零次 HTTP 请求，20/20 条均立即得到 request error；该轮定级：
  **`VOID_RUNNER_CONFIGURATION`**，不作为方法能力结论。
- 修复：客户端改为 `retry=1`，即一次 HTTP 尝试；实验本身不自动重试模型错误。
- 合规重跑目录：`V5-HARD20-TYPED-CAPSULE-001-RETRY`
- 题集：`official_like_hard20_v1`，SHA-256 `3cf90e65ef9239a70d9675b3807a01692d19aef27fa7cd1e5ffcefdc70ef12dd`
- 调度：20 题、3 workers、请求 timeout 900s、总硬停止 180 分钟、每题最多两次独立调用。
- 重跑耗时：`1144.6s`（约 19.1 分钟）。

## 2. 合规重跑指标

| 指标 | 预注册门 | 实测 | 判定 |
|---|---:|---:|---|
| 完整题数 | 20/20 | **20/20** | PASS |
| model error | ≤10% | **0/20（0%）** | PASS |
| typed answer 形成率 | ≥60% | **4/20（20%）** | FAIL |
| native correct | ≥4/20 | **2/20** | FAIL |
| invalid + model_error | ≤16/20 | **17/20** | FAIL |
| 平均调用 | ≤1.50 | **1.85** | FAIL |

附加统计：17/20 题触发 compact retry；总调用 37 次；typed answer 形成 4 次；native incorrect 1 次；invalid 17 次。

## 3. 结论

`typed_answer_capsule_v1` 在合规 V5 hard20 重跑中未达到形成率、correct、卫生或成本探索门，定级为：

**`EXPLORATORY_NO_GO / NO_PROMOTION`**

本结果支持以下判断：

1. 严格 typed parser 与 fail-closed 行为按设计工作，没有从正文、计划或尾部整数 salvage；
2. 0 model error 说明重跑端点健康；失败不是 runner 崩溃；
3. 4096 primary + 2048 independent retry 在本题集上只形成 20% typed answer，不能把输出协议修复转化为可判正确答案；
4. 不修改 `SUBMISSION_CONFIG`，不申请 official canary，不进入 baseline matched 复验；官方发布面继续保持 `hetero_k5 @ 25f99b5`（GitCode `34bc353`）。

完整原始工件见本目录：`answers.jsonl`、`run_manifest.json`、`report.json`。首轮 VOID 工件保留在上级目录以供审计，不与重跑结果合并。
