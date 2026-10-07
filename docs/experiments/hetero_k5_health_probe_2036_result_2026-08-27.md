# hetero_k5 第二健康窗口结果：UNHEALTHY（2026-08-27 20:36）

> 依据：[`hetero_k5_health_probe_2036_2026-08-27.md`](hetero_k5_health_probe_2036_2026-08-27.md)。
> 原始工件：[`hetero_k5_health_dev_2036_2026-08-27.json`](hetero_k5_health_dev_2036_2026-08-27.json)；
> manifest：[`hetero_k5_health_probe_2036_manifest_2026-08-27.json`](hetero_k5_health_probe_2036_manifest_2026-08-27.json)。

## 结果

| 指标 | 值 |
| --- | ---: |
| 完整记录 | 3/3 |
| model_error 诊断 | **2/3** |
| runner circuit-breaker | 未触发（最大连续失败 2） |
| 平均 / P95 calls | 4.333 / 5 |
| 平均 / P95 completion tokens | 4427.67 / 6340 |
| 平均 / P95 单题延迟 | 315.48s / 445.81s |
| main length rate | 33.3% |
| correct（仅描述） | 2/3 |

## 判定与处置

**当前 20:36 窗口 `UNHEALTHY`，不启动 complex48 小筛。**

- correct=2/3 不参与健康判定，不能豁免 2 个 model_error；
- `hetero_k5` 已经直接发布为未验证 canary，但本窗口仍不产生本地能力证据；
- 用户允许与官方端点争用，不改变本地 A/B 需要健康窗口的统计边界；
- 本窗口的一次探针已用完；恢复 21:30 自动复检，届时另立第三窗口记录。
