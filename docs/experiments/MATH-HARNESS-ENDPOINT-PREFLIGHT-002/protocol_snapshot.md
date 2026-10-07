# MATH-HARNESS-ENDPOINT-PREFLIGHT-002

状态：运行前冻结；这是对 `MATH-HARNESS-ENDPOINT-PREFLIGHT-001` 的一次独立、用户授权的
诊断重试，不覆盖原窗口，也不自动解除原窗口的 NO_GO 处置。

## 目的

在完全相同的协议、题集、提示词和门槛下，再次检查官方默认 thinking 端点能否把普通自由
格式响应稳定交给 `MATH-HARNESS-V1` `HostParser`。本窗只检查格式/健康，不检查答案正确率。

## 冻结配置

- source dataset：`sample_data/external_hard_sets/set_b_aime.jsonl`
- selection：与 `MATH-HARNESS-ENDPOINT-PREFLIGHT-001` 完全相同的 10 道 AIME 题
- source dataset SHA-256：`E39108744B5B0548FCCFC28A089DDD1CCCD0821E7235A6F2E18FA74449CD8315`
- spec SHA-256：`594329F14DD283BB71E663DE040E08B27AF4B09EF37E78C43481AF171431AD48`
- `method_id=bounded_evidence_trajectory_selection_v1`
- official client：`InternChatClient`
- `thinking_mode=None`，继承官方默认 thinking；`INTERN_THINKING_MODE` 必须未设置
- `temporary_answer_bank=off`
- 每题一次请求；不重试、不补跑、不并行
- `temperature=0.6`，`max_tokens=4096`
- 单请求 timeout：600 秒；窗口 hard stop：7200 秒
- 唯一可抽取候选门槛：至少 8/10；`parsed` 和 `truncated_with_candidate` 均可抽取

提示词与 001 完全一致：普通自由格式回答，不要求 `CANDIDATE`、`FINAL`、`最终答案` 或
FSDF handoff marker；最终结果独立成行。

## 记录与处置

每题只记录元数据、请求状态、错误类别、响应长度、finish reason、completion tokens、延迟、
parser 状态、候选数量、候选阶段来源和截断状态；不记录完整 prompt、完整 response、候选值
或 gold answer。该重试无论结果如何都不产生数学能力结论；若通过，也必须另行评估是否允许
恢复后续窗口，不能自动启动 HEALTH 或 A/B。

## 边界

不修改 FSDF、默认配置、`SUBMISSION_CONFIG`、答案库、main、远程仓库或赛事提交；不覆盖
`MATH-HARNESS-ENDPOINT-PREFLIGHT-001` 的任何工件。
