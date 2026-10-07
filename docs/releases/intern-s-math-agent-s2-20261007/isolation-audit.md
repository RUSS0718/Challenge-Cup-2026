# main 新架构隔离审核（2026-10-07）

## 基准与范围

基准为当前本地 `intern-s-math-agent-main` 的 10 文件快照，哈希记录在
`source_sha256.json`。审核从 GitCode main 的 `36739a0` 开始。对比的是当前正式
`user_agent.ReasoningAgent` 与本地 `main.py` 入口，不声称删除了所有历史文件，
也不声称每个历史脚本能兼容新 API；它们不是当前支持的入口。

## 审核结论

| 保留组件 | 实際角色 / 处置 |
| --- | --- |
| `user_agent.py` + `implementations/` | 唯一正式推理路径，逐字节保持本地源快照 |
| 旧 selector / CFR / FSDF / bank / RAG / Skills | 正式入口未导入，无自动路由或回退；运行时导入阻断测试通过 |
| `llm_client.py` | 外部 HTTP 客户端，使用 intern-s2；仅运输、请求参数和诊断，不做旧答案选择 |
| `reasoning_agent.artifacts` | 审核完整 189 行：仅标准库导入和文件持久化；无模型调用、答案改写、selector 或环境路由 |
| `main.py` | 仅 submission profile；传入新代理默认配置，每题独立代理及客户端 |
| 旧 README / 发布协议 | 归档历史 README，当前 README 仅说明新入口和运行方式 |
| 旧测试 / 实验脚本 | 不属于新入口验证；默认 pytest 仅收集新架构及已审核适配组件测试 |

发现并修正：runner 多题共享客户端的 `response_metadata` / `last_response_metadata`
会影响代理读取完成原因，存在并发串扰风险；现在每题创建独立客户端。回归测试先在原代码
失败（两个代理的 client 相同），修正后通过。未修改任何源代理文件。

## 可复现证据

- 10 个源文件：本地源目录、工作树与冻结哈希一致。
- 同一独立进程探针在源目录和待发布目录运行：正常完成、client 异常、空响应、续写、
  idx=33 扩展预算，共 5/5 场景的完整 request / kwargs / final_response / trace 相同。
  两边固定计时以比较功能决策，不能作为延迟或硬超时证据。
- 导入阻断器拒绝除 `reasoning_agent.artifacts` 外的旧 reasoning_agent 子模块，及 bank、
  reference runtime、Causal、PoT 等旧模块；新入口 solve 与 runner 导入仍通过。
- CLI 显式拒绝 fsdf 等旧 profile；模型调用参数与 JSON 序列化测试通过。
- 默认 pytest 范围包含新入口隔离、接入、旧客户端回归及已审核 artifacts 工具测试。

边界：这些检查确认支持入口的源码一致性、已覆盖场景的行为一致性及旧模块隔离；
不能穷举所有数学题、第三方 client 和环境。严格三参数平台 client 的 thinking_mode
兼容限制是源架构自身已有的问题，仍保持与本地源仓库一致，未在本审核中偷偷改写。
平台模型由注入的 client 决定，本地默认 model 不控制平台模型。

最终验证：23 项测试及 10 项子测试通过；源/目标行为探针对比 5/5 一致；
编译和 git diff --check 通过。开发测试使用现有项目 pytest 环境，未改动生产依赖。
