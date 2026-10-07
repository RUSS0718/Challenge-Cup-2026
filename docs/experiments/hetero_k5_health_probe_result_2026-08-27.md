# hetero_k5 启动前健康探针结果：UNHEALTHY（2026-08-27）

> 冻结口径：[`hetero_k5_health_probe_2026-08-27.md`](hetero_k5_health_probe_2026-08-27.md)。
> 原始工件：[`hetero_k5_health_dev_2026-08-27.json`](hetero_k5_health_dev_2026-08-27.json)；
> manifest：[`hetero_k5_health_probe_manifest_2026-08-27.json`](hetero_k5_health_probe_manifest_2026-08-27.json)。

## 冻结判定

探针只检查 dev3 的三条 C0 记录是否全部无 `model_error`；correct、invalid 和答案内容不参与。
任一 model_error 即 `UNHEALTHY`，当前窗口停止且不启动 hetero 小筛。

## 结果

| 指标 | 值 |
| --- | ---: |
| 完整记录 | 3/3 |
| 含 model_error 的记录 | **3/3（100%）** |
| runner circuit-breaker | 未触发（最大连续失败 3，小于内部阈值 8） |
| 平均 / P95 model calls | 4.333 / 5 |
| 平均 / P95 单题延迟 | 255.58s / 368.31s |
| correct（仅描述，不参与判定） | 2/3 |

三个 idx（0/1/2）均带 `diagnostic_reasons=["model_error"]`。其中两题最终仍被本地 judge 判对，
说明“最终有答案”不能替代服务健康判据：多调用路径已经暴露于请求失败，正式同窗 A/B 会被污染。

## 处置

**当前窗口 `UNHEALTHY`，不启动 `current vs hetero_k5` complex48 小筛。**

- 本窗口允许的一次探针已用完，不反复探测直到抽到健康；
- `hetero_k5` 保持 `OPEN / NOT_RUN`，没有能力 PASS/FAIL 结论；
- 下一明确时间窗需要新的健康探针记录；只有探针 3/3 无 model_error 才执行既有 hetero 预注册；
- 本结果不反向评价 P1、hetero 或 C0 的答案能力，只说明当前端点不适合比较。
