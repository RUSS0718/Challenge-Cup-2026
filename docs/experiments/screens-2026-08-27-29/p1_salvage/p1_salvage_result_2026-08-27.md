# P1 失败路径抢救回归结果：VOID（2026-08-27）

> 判定依据：[`p1_salvage_preregistration_2026-08-27.md`](p1_salvage_preregistration_2026-08-27.md)
> （运行前冻结）。协议锚：`codex/b1-4k-canary @ cedad82`。
> 原始工件：[`p1_salvage_complex48_r12_2026-08-27.json`](p1_salvage_complex48_r12_2026-08-27.json)；
> manifest：[`p1_salvage_manifest_2026-08-27.json`](p1_salvage_manifest_2026-08-27.json)。

## 执行完整性

预注册计划为 `complex48 ×2` 后串行执行 `public112 ×2`，双臂均为
`current` vs `current_salvage`、逐题交错。实际情况：

- complex48 两轮四份 arm-report 完整落盘，JSON 可解析，每份均为 48 题；
- 父命令链于 19:05:35 结束，未生成 `public112_r12.json`；
- 当前无法从保留的终端状态确认第二条命令未启动或快速退出的具体原因，因此不作推测；
- 即使缺失 public112，complex48 已先触发预注册 VOID，不能形成 P1 晋升结论。

## 窗口健康门

预注册字面规则：**任一臂 model_error 率 >10%，整窗作废；VOID 先于 invalid 与正确率门。**
complex48 每臂每轮 48 题，因此 5 个及以上 model_error 即超过 10%。

| 轮次 | 臂 | correct（描述性） | invalid | model_error | error 率 | 预注册健康门 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| R1 | current(C0) | 23/48 | 0 | **9** | **18.75%** | VOID |
| R1 | current_salvage | 23/48 | 0 | **6** | **12.50%** | VOID |
| R2 | current(C0) | 24/48 | 0 | 1 | 2.08% | 单臂未触发 |
| R2 | current_salvage | 23/48 | 0 | **6** | **12.50%** | VOID |

runner 报告中的 `void=false` 只表示“连续 8 次 model_error”的内部熔断器没有触发；本次最大
连续失败数为 4。它与预注册的**整臂错误率门**不是同一判据，不能用来覆盖上述 VOID。

## 判定

**P1 本次回归窗口作废（VOID），不评估后续门。**

- invalid 缩减门：`NOT_EVALUATED`。complex48 两臂本身均为 invalid=0，且 public112 缺失；
- 正确率不回退门：`NOT_EVALUATED`。不计算或引用池化 b/c/p 支撑结论；
- 官方变更额度：`NOT_QUALIFIED`；
- P1 方法状态：`OPEN / NO_VALID_CONCLUSION`，不是 `PASSED`，也不是能力失败的 `REJECTED`。

表内 correct 仅用于工件身份核对和描述窗口，不得被池化或解释成 salvage 的效果。

### 机制覆盖（离线描述，不改变 VOID）

两轮 `current_salvage` 共 96 个 item-round 全部以 `finalization_status=selected` 结束：
`salvaged=0`、`fallback=0`。C0 两轮同样全部为 `selected`。因此 complex48 本次没有触达
P1 的失败路径，无法观察 invalid 回收；它最多只能在健康窗口承担“成功路径不回退”辅证。
未来若另立 P1 复测，应先说明哪个冻结数据能产生可审计的失败路径覆盖，不能机械重复一个
`salvaged=0/96` 的集合来宣称验证了 P1 机制。

## 处置

1. 本窗口和原始工件归档，不补跑 public112 来挽救已经触发 VOID 的证据包；
2. 不在同一不健康端点窗口启动 `hetero_k5`；
3. 若未来重测 P1，必须另写有限复测预注册，明确允许的健康复跑次数和替换哪些 VOID 窗；
4. 新预注册还必须给出失败路径覆盖来源；complex48 可保留作非回退辅证，但不能单独承担
   invalid 缩减门；
5. 在出现有效 P1 证据前，`enable_failure_salvage` 继续默认关闭，不进入官方候选或融合臂。
