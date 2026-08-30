# tests/ 索引

> 2026-08-30 归类：与历史一次性脚本配对的测试移入 `archive/`；其余按被测对象分组索引。
> 运行：`python -m unittest discover -s tests`（一律从仓库根执行）。

## 运行时/接口（提交面）

| 文件 | 被测对象 |
| --- | --- |
| `test_user_agent.py` / `test_user_agent_facade.py` | `user_agent` facade + reasoning_agent 行为 |
| `test_llm_client.py` | InternChatClient（含 request-deadline 护栏三态） |
| `test_verification_gated_retry.py` | B1 门控重试（历史形态） |
| `test_pot_executor.py` / `test_substitution_agent.py` / `test_substitution_check.py` / `test_sympy_adapter.py` | 受控工具（默认关） |

## 评测基础设施

| 文件 | 被测对象 |
| --- | --- |
| `test_evaluate_protocol_ab.py` | A/B runner（臂/交错/熔断/answer_rows） |
| `test_evaluate_dev.py` | 单题记录 schema 与判分 |
| `test_analyze_paired_ab.py` / `test_paired_analysis.py` | 配对键/健康门/聚类统计（PRE0-STATIC 契约） |
| `test_evaluate_protocol_ab_gate.py` | 晋升门 + 完整性模式 |

## archive/

与 `scripts/archive/` 历史一次性工具配对的 13 个测试
（deterministic 三件套、method_rag、token_ladder、rag_gate、scan_budget、
independent 审计、diagnose_dev_failures、freeze/medium/length-pressure 数据集）。
仍可运行；引用已指向 `scripts.archive.*`。
