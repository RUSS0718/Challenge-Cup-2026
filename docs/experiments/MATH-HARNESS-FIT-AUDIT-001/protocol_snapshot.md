# MATH-HARNESS-FIT-AUDIT-001

## 冻结范围

- source spec: `docs/experiments/MATH-HARNESS-V1-SPEC/spec.md`
- spec SHA-256: `594329F14DD283BB71E663DE040E08B27AF4B09EF37E78C43481AF171431AD48`
- candidate: `bounded_evidence_trajectory_selection_v1`
- harness version: `MATH-HARNESS-V1`
- audit mode: zero remote model calls
- audit date: 2026-09-10 (Asia/Shanghai)

## 适配矩阵

| 约束 | 适配结论 | 代码锚点 |
| --- | --- | --- |
| 根目录入口 | 保留 `user_agent.py`，导出 `ReasoningAgent` | `user_agent.py` |
| 构造函数 | `ReasoningAgent(client=official_client)` 兼容，额外参数可选 | `ReasoningAgent.__init__` |
| solve 契约 | 返回 dict，保证非空字符串 `final_response` | `ReasoningAgent.solve`、Harness formatter |
| client 契约 | 仅调用 `client.chat(messages, temperature, max_tokens)` | `ConstraintFitOrchestrator._call` |
| 调用上限 | solve-local，最多 5 次逻辑调用 | `BudgetLedger` |
| token 上限 | A/B/Critic/Repair/Continuation = 4096/4096/2048/4096/2048；合计最多 16384 | `HarnessConfig`、`BudgetLedger` |
| 单题时限 | 默认 1200 秒；响应越过 deadline 进入 timeout/fail-closed | `ConstraintFitOrchestrator._call` |
| 官方并发 | Harness 不创建线程/进程；并发由 runner 约束为 3 | 外部 runner 契约 |
| 题目隔离 | 每次 solve 新建 Evidence Ledger、Budget Ledger、候选编号 | `ConstraintFitOrchestrator.solve` |
| bank 隔离 | `bank_mode=off` 不导入/查找；on 仅显式 gateway 路径 | `SubmissionGateway` |
| 抽取 | 普通自由格式、答案类型、等价规范化、截断区分 | `HostParser` |
| fail-closed | 无候选、未决冲突、超时、异常返回 `UNKNOWN` | `_abstain`、`_call` |
| trace 卫生 | 仅保存候选摘要、状态、调用和预算，不保存完整 prompt/response | `EvidenceLedger.trace` |
| legacy 回滚 | proof/derivation/explanation 仅在显式 hybrid 下转 FSDF adapter | `HostRouter`、`FSDFLegacyBackendAdapter` |
| 工具边界 | typed micro-tools 默认关闭；无 Python/shell/network/MCP 接入 | `TypedMicroToolProvider` |

## 阶段结论

适配审计通过：Harness 可以作为 `ReasoningAgent.solve()` 外层 opt-in 路径存在，默认
FSDF 与 submission 配置保持不变。该审计没有连接端点、没有读取答案库进行能力判断，也不
授权修改 `SUBMISSION_CONFIG`、提交仓库或发布作品。
