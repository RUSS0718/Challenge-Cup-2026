# MATH-HARNESS-112-DIAGNOSTIC-001

状态：用户授权；`diagnostic-only / NO_CAPABILITY_CONCLUSION`。

## 目的

按用户要求，对公开 `sample_data/public_regression_112.jsonl` 执行一次完整的
Constraint-Fit Harness 诊断，观察正确性、候选形成、UNKNOWN、错误、调用、请求 token、
finish reason 和延迟。该窗不是 Issue #17 的能力晋升窗口；端点预检 `-001/-002` 的 NO_GO
处置保持不变。

## 规则修订

本窗是 `MATH-HARNESS-V1-SPEC` 中新增的用户授权 112 题诊断例外。它只放宽“预检失败后不
运行任何额外诊断”的本地实验限制，不放宽官方接口、并发、时限、调用/token、答案库和
隐藏题规则。无论结果如何，不能启动 HEALTH、机制 A/B、能力 A/B 或默认路径晋升。

## 冻结配置

- 数据集：`sample_data/public_regression_112.jsonl`，112 题，固定文件顺序
- 题集 SHA-256：运行 manifest 记录
- `method_id=bounded_evidence_trajectory_selection_v1`
- `temporary_answer_bank=off`
- `thinking_mode=None`，继承官方默认 thinking；环境变量 `INTERN_THINKING_MODE` 必须未设置
- 官方并发模拟：3 workers
- 单题 Harness 硬上限：1200 秒、5 次逻辑调用、16,384 请求 token
- 单次 HTTP timeout：600 秒；client retry=1，实验不补发失败请求
- 总窗口 hard stop：21,600 秒
- temperature 与 Harness 各阶段 token：使用 `HarnessConfig` 冻结 profile：
  `A/B/Critic/Repair/Continuation = 4096/4096/2048/4096/2048`
- 每题新建 client/agent；metadata 只传 `idx`；标准答案只在宿主侧评分，不进入模型请求

## 记录

每题记录 `final_response`、抽取答案、公开 gold 对照 verdict、outcome、错误/timeout、bank
状态、调用数、请求 token、可获得的实际 token、finish reason、候选状态、延迟和 compact
trace。trace 删除 prompt、完整模型 response 和 problem 字段，仅保留证据账本与决策摘要。

## 评分口径

- `correct/incorrect`：复用仓库既有通用 `judge_correct`；
- `invalid`：无抽取答案、`UNKNOWN` 或 judge 无法确定；
- `error`：顶层 client 错误或 Harness call error；timeout 单独计数；
- 结果不转化为 Issue #17 的 capability conclusion，且不与预检或其他窗口合并。

## 停止与发布边界

达到总窗口 hard stop 时不再启动新题，已完成记录保留；不删除、不补跑。运行不修改
`SUBMISSION_CONFIG`、默认开关、FSDF、答案库、远程仓库或赛事提交。
