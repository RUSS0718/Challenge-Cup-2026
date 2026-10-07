# hetero_k5 第三健康窗口结果：UNHEALTHY（2026-08-27 21:30）

> 依据：[`hetero_k5_health_probe_2130_2026-08-27.md`](hetero_k5_health_probe_2130_2026-08-27.md)。
> 原始工件：[`hetero_k5_health_dev_2130_2026-08-27.json`](hetero_k5_health_dev_2130_2026-08-27.json)；
> manifest：[`hetero_k5_health_probe_2130_manifest_2026-08-27.json`](hetero_k5_health_probe_2130_manifest_2026-08-27.json)。

## 结果

| 指标 | 值 |
| --- | ---: |
| 完整记录 | 3/3 |
| model_error 诊断 | **1/3** |
| runner circuit-breaker | 未触发（最大连续失败 1） |
| 平均 / P95 calls | 4.0 / 5 |
| 平均 / P95 completion tokens | 5845.33 / 7929 |
| 平均 / P95 单题延迟 | 235.20s / 356.70s |
| final_response nonempty | 100% |
| correct（仅描述） | 2/3 |

## 判定与处置

**21:30 窗口 `UNHEALTHY`，不启动 current vs hetero_k5 complex48。**

- 3/3 无 model_error 的启动条件未满足；
- correct 与非空 final_response 不参与健康门，不能豁免该错误；
- 本次一次性自动化使命已完成并删除；
- hetero_k5 仍是已发布、尚无有效本地 A/B 的 canary，不产生 PASS/FAIL。
