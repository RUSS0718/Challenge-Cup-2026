# CAR-001 F1-002 thinking-on 健康探针结果

结论：`VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION`

- 6 个冻结题目、12 个配对任务、3 workers 已完成；总耗时约 1771 秒（29.5 分钟）。
- FSDF v1：6/6 任务至少一个阶段超时，平均每题 5 次调用、平均耗时约 510 秒。
- CAR-001：4/6 任务至少一个阶段超时，2/6 任务完整返回；平均每题 2.5 次调用、
  平均耗时约 257 秒。
- 成功响应仍出现 `finish_reason=length`（FSDF 1 次、CAR 3 次）和 `stop`；这说明
  端点并非完全不可达，但 thinking-on 下响应延迟和阶段超时不满足健康门。
- 预注册健康规则要求任一臂至少 2 个任务出现模型/阶段错误即 VOID；因此本窗不进入
  F2，不比较正确率，也不把 CAR 的较少调用或部分候选形成解释为能力收益。
- 所有请求均使用 `thinking_mode=None`，未关闭思考；没有修改 `SUBMISSION_CONFIG`。

本窗使用修复后的 runner，能够识别 relay fail-closed `UNKNOWN` 背后的阶段错误。逐题
脱敏记录见 `answers.jsonl`，汇总见 `report.json`，协议与配置见 `run_manifest.json`。
端点恢复后，应先做单请求/少量请求 probe，再开启新的 F1 编号；不得直接进入 F2。
