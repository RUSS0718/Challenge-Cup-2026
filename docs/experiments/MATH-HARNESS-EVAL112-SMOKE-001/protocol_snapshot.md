# MATH-HARNESS-EVAL112-SMOKE-001

状态：用户授权的 10 题 smoke；`diagnostic-only / NO_CAPABILITY_CONCLUSION`。

- 数据源：团队自建、仿官方格式的 `reasoning_agent/error_notebook/eval_112.json`
- 选择：文件前 10 题，idx 0–9
- 最新 Harness：`bounded_evidence_trajectory_selection_v1`
- `temporary_answer_bank=off`
- 3 workers；单题 HTTP timeout 600 秒；总窗口 hard stop 7200 秒
- 每题最多 5 次逻辑调用、16,384 请求 token；gold 不进入 Agent，仅在宿主返回后评分

运行目标是完整完成 10 题；若总 correct 仅为 1–2 题，则停止后续扩大测试。
本窗不修改 `SUBMISSION_CONFIG`、FSDF 或远端发布面。
