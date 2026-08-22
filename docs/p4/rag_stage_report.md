# P4 离线方法卡 RAG 阶段报告（2026-08-18）

## 已完成

- `method_cards.jsonl`：40 张方法卡，字段为适用信号、方法、必要条件、常见误用和示例。
- `method_rag.py`：依赖零的本地检索器，Top-K 默认 2。
- 中文检索使用连续短语的二/三字 n-gram，避免单字高频重叠虚增命中率。
- `user_agent.py`：`enable_method_rag=False` 默认关闭；实验路径有 4000 字符上下文上限。
- `scripts/evaluate_method_rag.py`：19 条独立检索用例，Top-2 命中率 19/19。
- 方法卡不含 `answer`、`idx` 字段，也未包含冻结集题号。
- `scripts/independent_stage_evaluator.py` 已将冻结集、确定性双轮和检索覆盖率合并验收；当前唯一失败项是 `rag:model_ab_missing`。

## 尚未满足的晋升条件

- 尚未取得真实模型 baseline/RAG 双轮 A/B 结果。
- 因模型 API 连接在当前执行环境中持续阻塞，不能据离线检索覆盖率推断答案准确率收益。
- 低成本复验（1题、1调用、5秒）仍返回 `model_call_failed:request`；RAG Gate 已将 `failed_item_ids` 和评测状态错误列为硬失败。
- 因此 RAG 不进入默认路径，也不启动 DSL、自一致性或 P2/P3 扩展。

## 真实 397B 双轮 A/B 结果

结果见 `medium_397b_rag_ab_summary.json`。baseline→RAG：

- Round 1：48.33% → 45.00%，P95 48.8s → 104.8s；
- Round 2：50.00% → 41.67%，P95 46.1s → 81.5s。

两轮均无超时、空响应或失败项，但 RAG 准确率均下降，且第二轮平均调用数增加。
严格 Gate 失败，结论为 `REJECT_RAG_DEFAULT_PROMOTION`。

## 晋升 Gate

两轮均需满足：

1. 中等冻结集正确题数至少增加 5；
2. 112 题回退不超过 2pp；
3. 空响应、超时为 0；
4. 平均调用数不增加；
5. 两轮方向一致。

执行器：`scripts/evaluate_rag_gate.py`。
