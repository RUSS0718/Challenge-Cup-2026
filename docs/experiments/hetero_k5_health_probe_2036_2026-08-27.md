# hetero_k5 第二健康窗口探针（2026-08-27 20:36）

> 用户在 20:36 明确要求继续实验，并确认不以官方端点争用作为停止理由。
> 端点健康仍是本地 A/B 的证据条件。本探针不进入能力结论。

## 冻结配置

- runtime：GitCode main / 本地工作树 `25f99b5`；
- 数据：`sample_data/dev.jsonl` 三题；
- 变体：仅 `current`；
- 参数：rounds=1、workers=3、timeout=90s、retry=1、temperature=0.6；
- 输出：`tmp/hetero_k5_2026-08-27/health_dev_2036.json`；
- 只读取 model_error 与工件完整性，不看 correct、invalid 或答案文本。

## 冻结判定

- 3/3 均无 model_error：`HEALTHY`，立即串行启动 hetero complex48 小筛；
- 任一 model_error、异常退出或工件不完整：`UNHEALTHY`，本窗口不启动小筛；
- 本窗口只探测一次；若失败，可由已经安排的 21:30 新窗口另行复检。
