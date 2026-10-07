# MATH-DEEP-FORMATION-PROBE-001

状态：`PREREGISTERED / BANK_OFF / NO_CAPABILITY_CONCLUSION`

目的：只验证 `typed_contract_adaptive_deep_v1` 在当前公开 client 端点上能否
形成符合 `ProblemContract` 的完整 typed answer；本窗不判数学正确性，不与
`eval_112.json` 的答案库交互，也不改变线上默认路径。

## 冻结配置

- 题源：`sample_data/external_hard_sets/set_a_olymmath_hard.jsonl`；6 个此前未
  出现在本仓库既有实验工件中的 OlymMATH 题组，题面只从 prompt-safe 字段读取。
- 题目顺序：`34-EN, 47-EN, 53-EN, 57-EN, 90-EN, 95-EN`。
- 路由：`HostRouter(deep_enabled=True)`；每题必须为 `target=harness`、
  `lane=deep`，契约见 `dataset_manifest.json`。
- bank：`temporary_answer_bank=off`；gold 不传入 Agent，也不写入逐题结果。
- client：只使用 `client.chat(messages, temperature, max_tokens)`；
  `thinking_mode=None`，继承当前 client 默认行为；不读取 client 私有字段。
- 首调用：`deep_primary=8192`；第二调用按 typed completeness 触发
  `deep_review=4096` 或 `deep_continuation=4096`；冲突至多一次
  `deep_critic=4096`。
- 硬上限：每题最多 3 次逻辑调用、请求 token 总额不超过 16384、单题 1200 秒；
  runner 最多 3 workers，整窗 7200 秒。
- 调度：先并发运行冻结顺序的前三题；若前三题均未 `typed_complete`，立即停止；
  否则再并发运行后三题。不得运行中修改题集、prompt、parser、预算或停止门。

## 门槛

formation 通过必须同时满足：6/6 有 durable record、0 model error、0 timeout，
且至少 5/6 题出现一次 `typed_complete`。`typed_complete` 统计 parser 的 typed
formation 记录，不把最终选中、单次 `candidate_unproven` 或答案库命中当作形成。

任一门失败均记录 `NO_GO / NO_CAPABILITY_CONCLUSION`，不进入 Deep trajectory、
Deep ability A/B 或 Hybrid；不得回到原 10 题继续调参。
