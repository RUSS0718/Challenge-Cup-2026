# POST-MAIN-EVAL-001 评测结果

配置：GitCode `main` 提交 `bd16a3f` 对应的 FSDF v1 默认路径；OlymMATH、AIME、HLE
各 1 题，3 workers，thinking-on 默认，单次请求超时 120 秒。

结果：

- 3/3 任务完成，平均 5 次调用，平均耗时约 445.5 秒；顶层 `model_error=0`。
- AIME：1 correct。
- OlymMATH：1 invalid（最终 UNKNOWN）。
- HLE：1 invalid（最终 UNKNOWN）。
- 汇总：`1 correct / 0 incorrect / 2 invalid`，本地近似 accuracy `33.33%`。
- 阶段级 client error 共 5 次，主要集中在 FSDF 的 D/E 阶段；两道 invalid 均为
  阶段 timeout 后的 fail-closed UNKNOWN。
- 所有响应均可序列化，native 与 contract 判定一致；p95 因样本数 3 未提供。

这只是 3 题官方样式本地 smoke，不是赛事隐藏集成绩，也不产生能力晋升结论。结果
不能证明 CAR-001 或 FSDF v1 的数学正确率；它只确认当前 main 可运行，并再次显示
thinking-on 下 FSDF D/E 延迟和 timeout 风险。
