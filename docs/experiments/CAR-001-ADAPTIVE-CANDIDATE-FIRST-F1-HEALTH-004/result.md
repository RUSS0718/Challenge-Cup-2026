# CAR-001 F1-004 完整健康窗口结果

结论：`VOID / STAGE_ENDPOINT_UNHEALTHY / NO_CAPABILITY_CONCLUSION`

- 6 个冻结题目、12 个配对任务、3 workers、thinking-on 默认；窗口硬截止 1200 秒。
- 全部 12 个任务在约 942 秒内完成并已增量落盘，未触发 `partial_hard_stop`；启动时的
  `running` manifest/report 和每题 checkpoint 均存在。
- FSDF v1：6/6 任务至少一个阶段 timeout，平均 5 次调用、平均约 291 秒；D/E 超时
  仍是主要失败位置。
- CAR-001：2/6 任务至少一个阶段 timeout，4/6 任务无阶段错误；平均 1.83 次调用、
  平均约 120 秒。候选臂调用数明显低于 FSDF，但这只是成本/健康观察。
- `finish_reason`：FSDF 为 7 stop、3 length；CAR 为 3 stop、2 length；两臂均出现
  length，不能把候选形成当作截断问题已解决。
- 按预注册规则，任一臂至少 2 个任务出现阶段错误即 VOID；因此不进入能力门，不比较
  correct/incorrect，也不启动 F2。

本窗验证了 bounded futures、20 分钟窗口截止、启动 manifest、增量原子 checkpoint、
未完成任务不伪造为结果，以及 F1 专用 fail-fast（同题首次 transport error 后后续
阶段不再访问端点）。没有修改 `SUBMISSION_CONFIG`，未提交或推送。
