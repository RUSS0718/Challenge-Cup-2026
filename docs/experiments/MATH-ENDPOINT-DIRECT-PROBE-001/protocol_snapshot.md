# MATH-ENDPOINT-DIRECT-PROBE-001

目的：绕过 `ReasoningAgent`、Constraint-Fit Harness、HostParser 和答案库，仅测试公开
`InternChatClient.chat(messages, temperature, max_tokens)` 到当前远程端点的最小调用。

冻结配置：

- `thinking_mode=None`，使用 official-default thinking；
- `temporary_answer_bank` 不导入；
- `temperature=0.0`、`max_tokens=128`、单请求 timeout 90 秒、`retry=1`；
- 两类 prompt 各重复 3 次：纯文本 `OK`，基础数学 `1+1=2`；
- 只记录状态、响应是否非空、响应长度、finish reason、completion tokens 和延迟；不保存响应正文；
- 本窗只作端点诊断，不产生数学能力结论、不修改默认路径。

解释规则：

- 简单请求也 timeout：远程端点/网络链路存在一般性健康问题；
- 简单请求均快速成功：端点对简单请求健康，结合 Harness 复杂题 timeout，优先怀疑远程复杂推理排队/服务长尾；
- 本探针不区分远端模型推理、网关排队和中间网络设备，需要服务端日志才能进一步区分。
