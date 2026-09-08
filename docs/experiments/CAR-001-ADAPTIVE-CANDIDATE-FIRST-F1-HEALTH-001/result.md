# CAR-001 F1 thinking-on 健康探针结果

结论：`VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION`

- 6 个配对题、12 个任务、3 workers 已完成；没有任何成功模型响应。
- FSDF v1 的 6/6 题在 Analyze/B/C/D/E 阶段均出现 `model_error`，客户端诊断为
  `connectivity / ConnectionError`。
- CAR-001 的 6/6 题在 candidate-1/candidate-2/recovery 均出现客户端错误，客户端诊断
  为 `connectivity / ConnectionError`。
- 两臂 `finish_reasons` 和 `completion_tokens` 均为空；因此没有截断率、正确率或 token
  能力数据可供解释。
- 初始 runner 曾把 fail-closed `UNKNOWN` 记录成顶层 `status=ok`；复核逐题 stage trace
  后已重分类为两臂各 6/6 stage-error，并修复 runner 统计逻辑。没有因修复而追加模型调用。

按预注册健康规则，本窗在能力门之前作废，不启动 F2/F3。该结果只说明当前端点窗口
不可用，不说明 FSDF、CAR 或 thinking-on 的数学能力。F1 runner 修复见
[run_car001_health_probe.py](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/run_car001_health_probe.py)。
