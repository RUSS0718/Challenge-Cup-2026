# Intern-S2-Preview-397B 基线复验（2026-08-18）

## 配置

- 模型：`intern-s2-preview-397b`
- 数据：`sample_data/medium_capability_freeze_60.jsonl`
- `max_tokens=4096`
- 单题最多 2 次调用，实际平均 1.0167 次
- 请求超时 120 秒，重试 1 次
- RAG 关闭

## 有效结果

- 正确：29/60（48.33%）
- UNKNOWN：31/60（51.67%）
- incorrect：0
- 空响应：0
- 超时：0
- failed item：0
- P95 延迟：48.827 秒

该轮证明显式 397B 模型可用，并显著不同于旧别名/网络失败观测；但只有一轮，不能作为模型或 RAG 晋升依据。

## RAG 对照状态

RAG 第一轮尚未启动：两次沙箱外权限审核超时，未产生评测进程。不能把 baseline 与 RAG 混合比较，也不能据此判定 RAG 收益。
