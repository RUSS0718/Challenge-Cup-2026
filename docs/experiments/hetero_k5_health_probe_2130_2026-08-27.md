# hetero_k5 第三健康窗口探针（2026-08-27 21:30）

> 由 `challenge-cup` 心跳在预定时间触发。用户已允许与官方端点争用；本地 A/B
> 仍严格执行健康门。runtime 锚为 GitCode main `25f99b5`，实现 commit `18f4f5a`。

## 冻结配置

- 数据：`sample_data/dev.jsonl` 三题；
- 变体：仅 `current`；
- 参数：rounds=1、workers=3、timeout=90s、retry=1、temperature=0.6；
- 输出：`tmp/hetero_k5_2026-08-27/health_dev_2130.json`；
- 判定只读 model_error 与工件完整性，不看 correct、invalid 或答案文本。

## 冻结判定

- 3/3 均无 model_error：`HEALTHY`，立即串行启动 current vs hetero_k5 complex48；
- 任一 model_error、异常退出或工件不完整：`UNHEALTHY`，本窗口不启动小筛；
- 本窗口只探测一次，不在同一窗口复测。
