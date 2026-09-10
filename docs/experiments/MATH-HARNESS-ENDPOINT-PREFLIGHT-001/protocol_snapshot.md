# MATH-HARNESS-ENDPOINT-PREFLIGHT-001

状态：运行前冻结；本窗只验证端点格式/健康，不产生数学能力结论。

## 目的

验证当前官方默认 thinking 端点在普通自由格式提示下，是否能够稳定产生由
`MATH-HARNESS-V1` `HostParser` 抽取的唯一候选。该实验不要求 `CANDIDATE:`、
`FINAL:`、`最终答案：` 或 FSDF handoff marker。

## 冻结输入

- source dataset：`sample_data/external_hard_sets/set_b_aime.jsonl`
- 选择 10 道 AIME 公共题：`aime-2024-I-4`、`aime-2024-I-3`、`aime-2024-I-8`、
  `aime-2024-I-12`、`aime-2024-I-11`、`aime-2024-I-2`、`aime-2024-II-6`、
  `aime-2024-I-7`、`aime-2024-II-3`、`aime-2024-I-1`
- source dataset SHA-256：`E39108744B5B0548FCCFC28A089DDD1CCCD0821E7235A6F2E18FA74449CD8315`
- source answers are never placed in the prompt or persisted in the result artifacts
- spec SHA-256：`594329F14DD283BB71E663DE040E08B27AF4B09EF37E78C43481AF171431AD48`

## 冻结运行配置

- `method_id=bounded_evidence_trajectory_selection_v1`
- official client：`InternChatClient`
- `thinking_mode=None`，继承官方默认 thinking；环境变量 `INTERN_THINKING_MODE` 必须未设置
- `temporary_answer_bank=off`
- 每题 1 次请求；不重试、不补跑、不并行
- `temperature=0.6`
- `max_tokens=4096`
- 单请求 timeout：600 秒
- 窗口 hard stop：7200 秒
- 官方运行约束记录为 3 workers、单题 1200 秒、整轮 21600 秒；本窗串行运行

系统提示词固定为：

> You are a careful mathematical problem solver. Solve the problem in ordinary free-form prose.
> Do not use a special output protocol or tags. Conclude clearly; for a numerical or exact-answer
> problem, put the final result on its own last line.

用户提示词固定为：

> Solve the following problem.\n\n`<problem>`

## 记录与判定

每题只记录 item 元数据、请求状态、错误类别、响应长度、finish reason、completion tokens、
延迟、parser 状态、候选数量、候选阶段来源和截断状态；不记录完整 prompt、完整 response、
候选值或公共 gold answer。

通过门：

1. 10/10 durable records；
2. 0 model error；
3. 至少 8/10 题由 HostParser 形成唯一候选；`parsed` 与
   `truncated_with_candidate` 均算可抽取，但不宣称答案正确；
4. 任一失败均为 `ARCHIVED / NO_GO / NO_CAPABILITY_CONCLUSION`，不启动 HEALTH、机制 A/B
   或能力 A/B。

## 排除项

本窗不复用 CAR-002/CAR-002B/CAR-002C 的 marker 协议或 runner，不修改 FSDF、默认配置、
`SUBMISSION_CONFIG`、答案库、main、远程仓库或赛事提交。
