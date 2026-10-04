# ARM-V2.1.8 external length-pressure window — result

状态：`VOID / NO_CAPABILITY_CONCLUSION`

X01–X10 的首次运行不满足预注册的可比性条件，不能作为候选或基线结果。运行时没有在
真实端点调用前验证 SymPy 评分依赖；随后发现 `.venv` 重算会改变 8 条记录的判定，且
候选/基线第二次请求预算实际为 2,048/4,096，违反了“只改 finalizer”的唯一变量约束。

因此本目录的 `comparison.json` 只保留原始审计痕迹，不能用于报告 correct、incorrect、
invalid、截断或成本收益，也不支持任何晋升或否定结论。纠正后的独立窗口使用新的方法 ID，
见 [`ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002 result`](../ARM-V2.1.8-EXTERNAL-LENGTH-PRESSURE-002-20261005/result.md)。
