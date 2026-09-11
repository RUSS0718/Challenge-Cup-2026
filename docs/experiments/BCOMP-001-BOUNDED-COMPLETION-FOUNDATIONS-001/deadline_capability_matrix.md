# BCOMP-001 截止能力矩阵

状态：`CODE_ACCEPTED_ZERO_MODEL_NO_CAPABILITY_CONCLUSION`。本文件描述执行层边界，
不把本地等待停止写成远端取消，也不把调用前后的时间检查写成同步 client 的硬超时。

| 能力 | 执行层 | 状态 | 可执行保证 | 验证方式 |
| --- | --- | --- | --- | --- |
| 调用准入截止 | Host scheduler | `supported` | 剩余题内时间必须覆盖已验证等待上限和收尾余量，否则不发起调用。 | `BoundaryPolicy.admit`、预算拒绝事件 |
| 调用等待截止 | 受限本地 runner | `supported_local_only` | 本地 runner 等待到 call-wait 边界；inline `solve()` 不能打断任意同步 client。 | blocking stub 集成测试 |
| 本地工作单元终止 | 本地 runner | `unknown_after_block` | 超时后不创建替代 worker；仍运行的 daemon worker 被计入并可产生迟到事件。 | active worker/timeout/late event |
| 远端取消 | 官方 client / 平台 | `unsupported` | 公开 `client.chat(messages, temperature, max_tokens)` 没有取消句柄；远端状态保持 `unknown`。 | 公共契约审计与报告字段 |
| `solve` 返回截止 | 官方 runner / 平台 | `platform_owned` | Host 可拒绝后续调用，不能强迫阻塞中的注入 client 返回。 | 平台超时；本地不冒充通过 |
| 整个窗口停止 | Probe runner | `supported_for_dispatch` | 达到 6 小时窗口或出现未解决活动调用后停止 dispatch，未请求项单列 `skipped`。 | manifest、planned/dispatched/skipped |

固定边界：每题最多 20 分钟、窗口最多 6 小时、最多 3 workers、每题最多 5 个逻辑调用、
每题请求 token 最多 16384。BCOMP 零模型 probe 本身每臂每题只规划 1 次调用、无自动重试。
