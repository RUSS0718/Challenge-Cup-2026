# CAR-001 恢复 probe 结果

结论：`PARTIAL_RECOVERY / DO_NOT_REOPEN_F1 / NO_CAPABILITY_CONCLUSION`

- 最小默认-thinking 请求成功，延迟约 0.81 秒；`max_tokens=8` 时因预算过小以
  `finish_reason=length` 结束。
- 同一冻结题（idx 6000）分别运行 FSDF v1 与 CAR-001，单题内部不并发。
- CAR-001：1 次调用、约 112 秒、无阶段错误，形成一个候选；但 2048 token 请求以
  `length` 结束，候选仍属于 `candidate_unproven`。
- FSDF v1：A/B/C 三阶段成功，D/E 两阶段 timeout；5 次调用、约 542 秒，最终
  `UNKNOWN`。

端点从“完全连接失败”恢复为“可间歇响应”，但 thinking-on 下阶段延迟仍不稳定；
基线 FSDF 未通过单题健康条件，因此不能重新开启 F1-003，也不能进入 F2。该 probe
不产生正确率或 CAR 能力结论。F1-002 的健康门结论仍然有效。
