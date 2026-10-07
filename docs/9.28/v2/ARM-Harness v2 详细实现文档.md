# ARM-Harness v2 详细实现文档

> Base: `feat/arm-harness-v1`<br>
> New branch: `feat/arm-harness-v2`

---

# 1. 开发目标

本轮只做：

```text
Candidate Validity
Candidate Trust
Selective Second Sample
Timeout Recovery
Bounded Conflict Resolution
```

暂不做：

```text
learned router
PRM
multi-agent
RAG
固定 voting
复杂 verifier tree
```

---

# 2. 创建分支

先同步当前 ARM v1：

```bash
git fetch origin

git switch feat/arm-harness-v1

git pull --ff-only origin feat/arm-harness-v1
```

确认：

```bash
git status
git log -5 --oneline
```

然后：

```bash
git switch -c feat/arm-harness-v2
```

检查：

```bash
git branch --show-current
```

应为：

```text
feat/arm-harness-v2
```

---

# 3. 建议 Commit 拆分

```text
commit 1
refactor(arm): split candidate validity from stability

commit 2
feat(arm): add candidate trust policy

commit 3
feat(arm): add selective second-sample consensus

commit 4
feat(arm): separate runtime recovery from reasoning escalation

commit 5
feat(arm): add compact timeout salvage policy

commit 6
test(arm): add candidate trust and timeout recovery coverage

commit 7
eval(arm): add reliability and recovery experiments

commit 8
docs(arm): document ARM v2
```

---

# 4. 第一阶段：废弃 candidate_is_stable 语义

当前：

```python
candidate_is_stable(...)
```

不要直接继续使用。

改成：

```python
candidate_is_parseable(...)
```

或者：

```python
candidate_is_structurally_valid(...)
```

---

# 5. inference_policy.py 重构

新增：

```python
CandidateConfidence = Literal[
    "low",
    "medium",
    "high",
]
```

新增：

```python
@dataclass(frozen=True)
class CandidateTrustDecision:
    trusted: bool
    confidence: CandidateConfidence
    needs_second_sample: bool
    reason: str
```

---

# 6. 新增 CandidateTrustPolicy

建议文件：

```text
reasoning_agent/candidate_trust.py
```

而不是继续把所有东西塞进：

```text
inference_policy.py
```

结构：

```python
class CandidateTrustPolicy:

    def evaluate(
        self,
        *,
        contract,
        candidate,
        parsed,
        call_result,
    ) -> CandidateTrustDecision:
        ...
```

---

# 7. 第一版 Trust Rule

逻辑建议：

```python
if not candidate_is_structurally_valid(...):
    return CandidateTrustDecision(
        trusted=False,
        confidence="low",
        needs_second_sample=True,
        reason="structurally_invalid",
    )
```

之后：

```python
simple_direct = (
    contract.reasoning_risk == REASONING_RISK_DIRECT
    and contract.route_confidence == ROUTE_CONFIDENCE_HIGH
    and candidate.answer_type in {
        ANSWER_INTEGER,
        ANSWER_RATIONAL,
        ANSWER_CHOICE,
    }
)
```

若：

```python
simple_direct
and call_result.finish_reason == "stop"
and not parsed.truncated
```

返回：

```text
trusted=True
```

其他：

```text
trusted=False
needs_second_sample=True
```

---

# 8. Candidate Structural Validator

新增：

```text
reasoning_agent/candidate_validation.py
```

提供：

```python
def validate_candidate_shape(
    candidate,
    answer_type,
) -> tuple[bool, str]:
```

---

# 9. Integer Validator

例如：

```python
INTEGER_RE = re.compile(r"^[+-]?\d+$")
```

不允许：

```text
The answer is 12 because...
有：
the area is:
```

进入 integer candidate。

---

# 10. Choice Validator

只接受：

```text
A
B
C
D
```

如果比赛允许多选，再独立定义。

不要允许：

```text
Answer: maybe C
```

被 Host candidate 直接接受。

---

# 11. Rational Validator

接受：

```text
3/4
-2/5
7
```

但拒绝明显 prose。

---

# 12. Expression Validator

这一类不能过度严格。

第一版只过滤：

```text
空值
纯语言句子
冒号结尾
placeholder
```

不要尝试在 Parser 阶段判断数学正确。

---

# 13. Candidate Ledger 扩展

Candidate 增加：

```python
structural_validity: str
trust_confidence: str
trust_reason: str
```

例如：

```json
{
  "candidate_id": "arm_primary_1",
  "reasoning_mode": "off",
  "structural_validity": "valid",
  "trust_confidence": "medium",
  "trust_reason": "high_reasoning_risk_single_sample"
}
```

---

# 14. 修改 arm_harness.py

现在：

```python
if candidate_is_stable(...):
    return _select(...)
```

删除这个逻辑。

改成：

```python
if candidate_is_structurally_valid(...):
    trust = self.trust_policy.evaluate(...)
```

然后：

```python
if trust.trusted:
    return self.harness._select(...)
```

否则：

```text
进入 second sample
```

---

# 15. Selective Second Sample

新增：

```python
def _run_second_sample(...)
```

使用：

```text
OFF
independent prompt
```

不能把 Candidate A 放进 prompt。

---

# 16. Second Sample Prompt

建议：

```text
你是独立数学求解器。

请独立解决原题，不参考任何其他候选答案。

优先保证最终答案正确。
必要推导保持紧凑。

最后一行：
Final answer: <answer>
```

---

# 17. Second Sample Budget

第一版：

```text
max_tokens = attempt_b max tokens
reasoning_mode = off
```

Call budget：

```text
FAST trusted:
1

VERIFY:
2

CONFLICT:
3
```

---

# 18. Agreement 判定

复用：

```python
value_equivalence(...)
```

逻辑：

```python
if A equivalent B:
    mark both:
        verification_status = "consensus_supported"
```

然后：

```text
low-risk
→ select

high-risk
→ deterministic checks
```

---

# 19. Conflict 判定

如果：

```text
A != B
```

进入：

```python
_resolve_candidate_conflict(...)
```

顺序：

```text
normalize
→ value_equivalence
→ typed validation
→ deterministic constraint checks
→ critic
```

---

# 20. Critic 不允许创造新 Candidate

Prompt 明确：

```text
只能输出：
A
B
UNKNOWN
```

不要让 critic：

```text
重新解题并给第三答案
```

---

# 21. Critic Prompt

示意：

```text
给定同一道数学题的两个候选答案。

Candidate A: ...
Candidate B: ...

请仅判断：
A
B
UNKNOWN

不要生成新的第三个答案。
```

---

# 22. Critic 配置

推荐：

```text
reasoning_mode = off

max_tokens = 1024
```

如果 1024 不够再测试：

```text
2048
```

不要直接 4096。

---

# 23. 第二阶段：拆 Runtime Recovery

当前：

```python
should_escalate()
```

同时处理：

```text
timeout
candidate conflict
no candidate
```

这需要拆开。

新增：

```text
reasoning_agent/runtime_policy.py
```

---

# 24. RuntimeFailure

```python
RuntimeFailure = Literal[
    "timeout",
    "request_error",
    "empty_response",
]
```

---

# 25. RuntimeRecoveryPolicy

```python
@dataclass(frozen=True)
class RuntimeRecoveryDecision:
    action: Literal[
        "retry_longer",
        "compact_salvage",
        "abstain",
    ]
    max_tokens: int
    timeout_seconds: int
    reason: str
```

---

# 26. 第一版 Runtime Policy

暂时不要 hardcode 谁最好。

用 profile 配置控制：

```python
arm_timeout_recovery_mode: str = "compact_salvage"
```

支持：

```text
repeat
longer_first
compact_salvage
none
```

---

# 27. Compact Salvage

新增：

```python
ARM_COMPACT_SALVAGE_PROMPT = """
直接重新计算题目，并尽快形成最终答案。

不要长篇解释。
只保留必要步骤。

最后一行：
Final answer: <answer>
"""
```

---

# 28. Salvage 参数

初始：

```text
reasoning_mode = off
max_tokens = 1024
```

timeout：

```text
10~15 seconds
```

这一项需要 Client 支持 per-call timeout。

---

# 29. Client 增加 request-local timeout

当前 per-request 已经支持：

```text
reasoning_mode
```

下一步可以扩展：

```python
client.chat(
    ...,
    reasoning_mode="off",
    timeout_seconds=15,
)
```

如果：

```python
timeout_seconds is None
```

则：

```text
使用 self.timeout
```

---

# 30. 禁止修改共享 client.timeout

和 reasoning mode 一样：

```python
self.timeout = ...
```

不能动态改。

否则并发会产生 race condition。

---

# 31. Client Test

增加：

```text
Thread A:
timeout=15

Thread B:
timeout=60
```

Mock HTTP request。

确认互不污染。

---

# 32. Scheduler 扩展

`AttemptScheduler.call()` 增加：

```python
timeout_seconds: int | None = None
```

一路传到：

```text
ConstraintFitOrchestrator._call
→ InternChatClient.chat
```

---

# 33. 第三阶段：ComputePolicy

新增：

```python
@dataclass(frozen=True)
class ComputePolicy:
    max_calls: int
    token_budget: int
    wall_time_budget: float
    allow_second_sample: bool
    allow_resolver: bool
    allow_thinking_on: bool
```

---

# 34. v2 Profile

建议新增：

```text
arm-v2-single
arm-v2-selective
arm-v2-long-timeout
arm-v2-salvage
```

而不是继续污染：

```text
arm-off
```

保留 ARM v1 baseline。

---

# 35. Profile 语义

### arm-v2-single

```text
OFF A
→ Trust Gate
→ no second sample
```

用于测 Trust Gate 本身。

### arm-v2-selective

```text
OFF A
→ trust?
→ selective OFF B
→ bounded resolver
```

主实验。

### arm-v2-long-timeout

```text
first OFF timeout = 60s
```

### arm-v2-salvage

```text
30s OFF
→ compact salvage
```

---

# 36. 不修改 Submission

继续：

```text
SUBMISSION_CONFIG
不启用 ARM v2
```

只有实验完成后再 promotion。

---

# 37. 第四阶段：实验数据冻结

保留当前：

```text
arm_fixed_items_30.json
```

另外新增两个集合。

---

# 38. Stable-14 集合

从 ARM-OFF-LOCAL-001 中提取：

```text
14 个 candidate_stable early-stop cases
```

写入：

```text
sample_data/arm_v2_stable_14.json
```

这个集合用于：

```text
Candidate Trust
Selective Consensus
```

---

# 39. Timeout-10 集合

提取：

```text
10 个 first-call timeout cases
```

写入：

```text
sample_data/arm_v2_timeout_10.json
```

用于 timeout policy。

---

# 40. E1：ON Raw Health

建议新增：

```text
scripts/run_arm_on_raw_health.py
```

不要经过：

```text
ReasoningAgent
Harness
Parser
```

直接：

```text
InternChatClient.chat()
```

测试：

```text
thinking_mode=true
workers=1
```

---

# 41. E1 Matrix

```text
token=512, timeout=130
token=2048, timeout=130
token=4096, timeout=130
```

3 题：

```text
easy
medium
hard
```

记录：

```text
status
latency
completion_tokens
finish_reason
response formed
```

不判断 Agent accuracy。

---

# 42. E2：Timeout Recovery

固定 timeout-10。

### Arm A

```text
30 + 30 repeat
```

### Arm B

```text
60 single
```

### Arm C

```text
30 + 15 compact salvage
```

尽量保持：

```text
总 wall-clock budget
接近
```

---

# 43. E2 指标

```text
correct
incorrect
invalid

candidate formation

wall time
calls

timeout count
```

主要看：

```text
correct under same wall budget
```

---

# 44. E3：Candidate Trust

固定 stable-14。

### Baseline

```text
ARM v1
single candidate
```

已有：

```text
4 correct
9 incorrect
1 invalid
```

### Candidate

```text
ARM v2 selective
```

比较：

```text
wrong early-stop rate
trusted candidate precision
correct count
calls/problem
```

---

# 45. E4：Full-30

只有 E2/E3 有正结果后再跑。

比较：

```text
ARM v1 arm-off
vs
ARM v2 selective
```

---

# 46. 报告新增字段

每题：

```json
{
  "candidate_a": "...",
  "candidate_a_valid": true,
  "candidate_a_trust": "medium",

  "second_sample_triggered": true,

  "candidate_b": "...",

  "agreement": false,

  "resolver_triggered": true,

  "final_source": "candidate_b"
}
```

---

# 47. Summary 新增指标

```text
trusted_candidate_n

trusted_candidate_correct_n

trusted_candidate_precision

wrong_early_stop_n

wrong_early_stop_rate

second_sample_n

second_sample_rate

agreement_n

agreement_correct_n

conflict_n

resolver_n

resolver_correct_n
```

---

# 48. 单元测试

新增：

```text
tests/test_candidate_validation.py
tests/test_candidate_trust.py
tests/test_runtime_recovery.py
tests/test_arm_v2_harness.py
```

---

# 49. Candidate Validation Test

必须覆盖：

```text
"117"
→ valid integer

"有："
→ invalid integer

"The area is:"
→ invalid numeric

"4/3"
→ valid rational
```

---

# 50. Trust Gate Test

### Case 1

```text
direct
high confidence
integer
normal stop
```

→ trusted。

### Case 2

```text
deep
integer
```

→ second sample。

### Case 3

```text
structured
expression
```

→ second sample。

### Case 4

```text
truncated
```

→ untrusted。

---

# 51. Selective Sampling Test

模拟：

```text
A = 117
trust=low

B = 117
```

确认：

```text
2 calls
consensus_supported
```

---

# 52. Conflict Test

```text
A = 117
B = 118
```

确认：

```text
critic triggered
```

最多：

```text
3 calls
```

---

# 53. High Trust Early Stop Test

```text
A valid
trust=high
```

确认：

```text
1 call
```

不能误触第二 candidate。

---

# 54. Runtime Failure Test

模拟：

```text
first call timeout
```

确认：

```text
不会进入 CandidateTrustPolicy
```

而进入：

```text
RuntimeRecoveryPolicy
```

这是 v2 很关键的边界。

---

# 55. Test Commands

先：

```bash
pytest -q tests/test_candidate_validation.py
pytest -q tests/test_candidate_trust.py
pytest -q tests/test_runtime_recovery.py
pytest -q tests/test_arm_v2_harness.py
```

再：

```bash
pytest -q
```

最后：

```bash
git diff --check
```

---

# 56. 推荐实施顺序

```text
1. branch feat/arm-harness-v2

2. rename/deprecate candidate_is_stable

3. CandidateValidityGate

4. CandidateTrustPolicy

5. trace trust metadata

6. selective second sample

7. conflict resolver restriction

8. RuntimeRecoveryPolicy

9. request-local timeout

10. compact salvage

11. freeze stable-14

12. freeze timeout-10

13. E1 ON raw health

14. E2 timeout policy

15. E3 candidate trust

16. E4 full-30

17. analyze

18. decide promotion
```

---

# 57. 建议的最小代码改动范围

硬题 runner 的默认运行方式不再把 raw 文件写入 `docs/experiments/`：省略
`--output-dir` 和 `--run-id` 时，运行器会创建唯一的
`artifacts/<run_id>/`，并在 manifest 中记录配置、数据集、模型、时间和代码版本。
需要断点续跑或执行 qualification preflight 时，显式传入同一个
`--output-dir artifacts/<run_id>`（可同时指定 `--run-id`）。

```text
reasoning_agent/
    arm_harness.py
    inference_policy.py
    candidate_validation.py
    candidate_trust.py
    runtime_policy.py
    harness_contracts.py

llm_client.py

reasoning_agent/profiles.py

scripts/
    external_hard_sets_artifacts.py
    external_hard_sets_aggregate.py
    external_hard_sets_judging.py
    external_hard_sets_qualification.py
    external_hard_sets_reporting.py  # compatibility exports
    run_arm_on_raw_health.py
    run_external_hard_sets_smoke.py

tests/
    test_external_hard_sets_artifacts.py
    test_external_hard_sets_reporting.py
    test_external_hard_sets_runner_report.py
    test_candidate_validation.py
    test_candidate_trust.py
    test_runtime_recovery.py
    test_arm_v2_harness.py
    test_llm_client.py
```

---

# 58. 暂时不要做的事情

本轮明确禁止同时加入：

```text
新的 RAG
更多 skill
更多 FSDF stage
K=5 voting
第三 candidate
PRM
learned router
```

原因：

```text
否则无法判断提升来自哪里。
```

---

# 59. Promotion Gate

ARM v2 要进入 submission，至少满足：

```text
Full-30 correct > ARM v1

AND

wrong early-stop 显著降低

AND

invalid 不明显恶化

AND

mean calls 不超过可接受范围

AND

p95 latency 不突破比赛预算
```

---

# 60. 推荐优先目标

不要第一阶段追求：

```text
accuracy 最大化
```

先追求：

```text
错误答案不要被过早相信
```

即优先优化：

```text
wrong early-stop
```

因为当前数据已经证明：

```text
模型经常能够形成一个非常像正确答案的错误 candidate。
```

只要这个问题没解决：

```text
更复杂 Router
更复杂 Thinking 策略
更多 token
```

都会建立在错误 stopping criterion 上。

---

# 61. 下一阶段

如果 ARM v2 selective 能明显优于 ARM v1，再进入：

```text
ARM v3
Learned Compute Policy
```

届时再使用历史实验构建 oracle action：

```text
1x OFF
2x OFF
resolver
ON
```

学习：

```text
给哪道题多少 compute
```

而不是现在就训练 Router。

---

# 62. 一句话执行原则

```text
ARM v1:
什么时候 Thinking

ARM v2:
什么时候应该相信答案

ARM v3:
下一单位计算资源应该花在哪里
```

当前先把 ARM v2 做扎实。
