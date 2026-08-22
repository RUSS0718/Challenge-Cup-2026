# 确定性求解阶段报告（2026-08-18）

## 数据与验证

- 数据集：`sample_data/medium_capability_freeze_60.jsonl`。
- 来源门槛：60/60 HTTPS 公开来源。
- 两次独立进程审计：`scripts/evaluate_deterministic_math.py`。
- 晋升判定：`scripts/evaluate_deterministic_gate.py`。
- 独立复核：`scripts/independent_audit_deterministic.py` 不调用求解器内部逻辑，重新计算支持形式；12/12 输出与独立期望和冻结答案一致。

## 两轮结果

```text
total       = 60
supported   = 12
correct     = 12
incorrect   = 0
unknown     = 0
unsupported = 48
```

两轮正确题 ID 集合完全一致：

```text
6100, 6101, 6110, 6111, 6200, 6201,
6202, 6203, 6220, 6221, 6222, 6223
```

## 结论

确定性工具满足本地“至少 10 个稳定新增正确、零误命中、零 unknown”的实验门槛，
但仍通过 `enable_deterministic_solver=False` 保持默认关闭。正式晋升仍需要新的独立
evaluator 线程确认，并在官方隔离环境完成接口/依赖验收。
