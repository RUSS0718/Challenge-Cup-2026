# ARM-ISOLATION-001 隔离实验重跑报告

- run_id：`ARM-ISOLATION-001-20260928-RERUN`

- 有效性：PARTIAL_ENDPOINT_RESPONSES
- 题目：OlymMATH-HARD-13-EN（仅保存 SHA-256，不保存题面）
- 条件记录：54/54
- 收到端点响应的条件：14/18；响应数：37
- timeout / 每题总预算：180s / 180s；预检：ok
- 每格 3 次；不保存模型响应正文或 API 凭据。

|路径|max_tokens/调用|workers|n|端点响应|correct / incorrect / invalid|请求 timeout|connectivity 错误|平均单题秒|平均请求秒|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|bare_endpoint|2048|1|3|3|0 / 3 / 0|0|0|47.109|47.108|
|bare_endpoint|2048|3|3|3|0 / 3 / 0|0|0|37.067|37.065|
|bare_endpoint|4096|1|3|3|0 / 3 / 0|0|0|120.099|120.013|
|bare_endpoint|4096|3|3|3|0 / 3 / 0|0|0|104.287|104.286|
|bare_endpoint|8192|1|3|0|0 / 0 / 3|3|0|180.125|180.126|
|bare_endpoint|8192|3|3|0|0 / 0 / 3|3|0|180.125|180.113|
|current_arm_on|2048|1|3|3|0 / 0 / 3|0|0|53.401|53.396|
|current_arm_on|2048|3|3|3|0 / 0 / 3|0|0|62.901|62.894|
|current_arm_on|4096|1|3|3|0 / 0 / 3|0|0|109.156|109.135|
|current_arm_on|4096|3|3|3|0 / 2 / 1|0|0|90.76|90.756|
|current_arm_on|8192|1|3|0|0 / 0 / 3|3|0|180.13|180.128|
|current_arm_on|8192|3|3|1|0 / 1 / 2|2|0|168.906|168.913|
|minimal_agent|2048|1|3|3|0 / 1 / 2|0|0|39.437|39.42|
|minimal_agent|2048|3|3|3|0 / 0 / 3|0|0|46.203|46.204|
|minimal_agent|4096|1|3|2|0 / 1 / 2|1|0|132.417|132.411|
|minimal_agent|4096|3|3|3|0 / 0 / 3|0|0|99.282|99.286|
|minimal_agent|8192|1|3|1|0 / 0 / 3|2|0|170.422|170.424|
|minimal_agent|8192|3|3|0|0 / 0 / 3|3|0|180.114|180.121|

注：“端点响应”仅表示请求收到了 HTTP 响应；`correct / incorrect / invalid` 是 native 判题结果，不等同于响应是否到达。

## 判读

本轮是**部分端点响应**，不能当作完整的因果实验：54 次请求覆盖 18 格，每格 3 次；14/18 格至少收到一次响应，共 37/54 次。另 17 次请求均记录为客户端 `ReadTimeout`，约 180.1 秒触发，HTTP 状态为空；没有 connectivity 错误。连通性预检（`thinking_mode=false`、16 tokens）收到 HTTP 200，耗时 3.39 秒。预检只能证明轻量请求可达，不能说明复杂请求在端点内部的生成或排队状态。

- **token 上限与超时最相关。** 2048 档 18/18 次均收到端点响应；4096 档 17/18 次收到；8192 档仅 2/18 次收到，另 16/18 次读超时。8192 档的超时出现在裸端点、最小 Agent 和当前 ARM-ON；裸端点本身 8192 档 6/6 超时。因此 Agent 架构不是发生超时的必要条件。提高 token 上限与延迟上升、超时增多同时出现，但单题小样本不能证明它是唯一原因。
- **没有证据表明 workers=3 是主要超时来源。** 2048 档所有路径在 workers=1/3 都有响应；4096 档只有最小 Agent、workers=1 的一个重复超时；8192 档两种 worker 设置下各路径都大幅超时。worker=3 的耗时没有一致变差，但每格只有 3 次，且无法排除端点负载/限流影响。
- **正确性与响应可用性是另一项严重问题。** 54 次中正确答案为 0；17 次形成了答案，但全部判错；37 次判为 invalid，其中包括未收到端点响应和收到响应但 Agent 未形成可评分答案的情况。也就是说，单纯延长 timeout 或降低 token 上限并未在本题上得到正确解。

**结论：** 当前证据不支持“超时主要是 ARM Agent 架构过于复杂”这一单因解释；更符合观测的判断是高 token/长推理请求在本地 180 秒读超时内未返回，且端点侧计算、排队或传输停滞尚不能区分。最小 Agent 在 4096、workers=1 有 1/3 次超时，说明架构或 prompt 仍可能在某些条件下有影响，但不足以定因。下一步应优先检查端点侧请求日志/usage，或记录流式首 token 与完成时延；同时单独修复答案抽取/格式，因为本轮没有任何正确答案。扩展结论前应使用更多题目、随机化条件顺序并重复。

## 边界

- Single fixed problem: diagnostic only, not general accuracy evidence.
- Three repeats per condition are small-sample diagnostics.
- workers=3 means three independent solves in parallel, not parallel calls within one solve.
- Each trial used one HTTP attempt (no retry after the initial attempt); timeout means the local client did not receive a response within 180 seconds, not proof of server-side compute time.

逐次请求明细、机器汇总、连通性预检与 manifest 留在本地忽略目录
`docs/experiments/ARM-ISOLATION-001-20260928-RERUN/`，不进入 Git。
