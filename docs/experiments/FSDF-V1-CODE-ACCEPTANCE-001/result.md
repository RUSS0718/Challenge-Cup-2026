# FSDF-V1-CODE-ACCEPTANCE-001 验收结果

方法：`fork_select_deepen_finish_v1`

结论：`CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`

- T01–T37：37/37 通过，使用只实现 `chat(messages, temperature, max_tokens)` 的 `ScriptedClient`，未连接真实模型端点。
- T02 中 BTCS 互斥组合标记为 `N/A`：当前基线缺少 `reasoning_agent.btcs` 和 `AgentConfig.protocol_mode`，无法构造该组合；不把 N/A 计为失败。
- 难题路径调用序列：`[2048, 2048, 2048, 8192, 4096]`，最多 5 次，合计 `18432` token。
- L0：仅简单四则算式识别命中时单调用 `4096`；长 scalar calculation 仍进入 A–E 主路径。
- 接口、JSON、三并发隔离、上下文上限、答案降级、trace 卫生和 deadline 门均通过。
- D 选择非法时记录 `protocol_failed/invalid_response`，保留合法 D 答案降级候选，但不把 D raw 传给 E。
- D 选择不可用分支时不静默改写，使用可用分支做确定性降级；D 的 handoff/raw 不传给 E。
- D handoff 字段不完整时仅传已识别字段并标记 `HANDOFF_INCOMPLETE: true`；E 上下文为 handoff 固定预留 2000 字符。
- 代码验收快照未修改 `SUBMISSION_CONFIG`；本轮之后按用户单独授权，官方 profile 已切换为 FSDF 开启、contextual 关闭；未新增依赖。
- `py_compile` 和 `git diff --check` 通过。

全量回归 `python -m unittest discover -s tests -q`：498 项，494 项通过，4 项明确跳过，0 项 error/failure。4 项是已归档 BTCS 测试：当前基线缺少 `reasoning_agent.btcs` 或 `AgentConfig.protocol_mode`，已在测试入口明确 skip，未涉及 FSDF 文件或路由。

本结果只证明代码结构、预算、接口和隔离契约满足本 spec，不产生数学能力或正确率结论；D 失败且两支均可用时固定回退 B。默认切换是用户单独授权的发布动作，不等于能力结论；GitCode `main` 已快进至 payload commit `1afdbe7`，后续仍需单独核验官方结果。
