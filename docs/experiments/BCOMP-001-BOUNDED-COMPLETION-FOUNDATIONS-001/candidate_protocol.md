# BCOMP-001 候选答案形成协议草稿

协议 ID：`ordinary_free_format_typed_formation_v1`

这是后续形成率测量的候选协议，不是能力通过标准，也不启动真实端点。

1. Host 发送固定 system prompt 和题面；不要求 `CANDIDATE:`、`FINAL` 或其它可见 marker。
2. 请求使用现有 `HostParser`/`TypedParser` 的冻结版本；不为提高形成率放宽 parser。
3. 每次响应的形成状态独立记录为：`no_response`、`incomplete_response`、
   `candidate_incomplete_or_ambiguous` 或 `complete_candidate`。
4. `complete_candidate` 只表示满足答案形状与终答语义的候选已形成，不表示原题正确。
   截断但带候选仍是未完成候选；完整但错误由宿主评分侧单独标记。
5. `support_source` 与 `recovery_source` 分开记录；`recovered` 不升级为 verified，
   `CONSENSUS` 也不等同原题正确。
6. 缺失 usage / finish metadata 记录为 `null`，不能填充为 0 或推断 `stop`。
7. 失败分类至少包括 `timeout`、`transport`、`empty`、`malformed`、`budget_refusal`、
   `deadline_refusal`、`cancelled` 和 `unknown`。

禁止：答案库、隐藏答案、任意代码、隐式重试、并行同题调用、跨题记忆，以及通过丢弃
超时样本来提高形成率。
