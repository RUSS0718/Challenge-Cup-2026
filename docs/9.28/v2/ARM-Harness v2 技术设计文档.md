# ARM-Harness v2 技术设计文档

> Adaptive Reliability & Compute Harness<br>
> Status: Design Draft<br>
> Base branch: `feat/arm-harness-v1`<br>
> Target branch: `feat/arm-harness-v2`

---

# 1. 背景

ARM-Harness v1 已经完成以下基础能力：

```text
Per-request reasoning mode
        ↓
FAST_OFF / ADAPTIVE / DEEP_ON
        ↓
Candidate-first
        ↓
Conditional escalation
        ↓
Bounded critic
```

现有实验说明：

```text
ON:
30s → 9/9 timeout
60s → 3/3 timeout
```

因此当前比赛预算下，ON 暂时不能作为可靠主路径。

与此同时，OFF 固定 30 题结果：

```text
5 correct
19 incorrect
6 invalid

candidate formation:
26 / 30

mean calls:
1.53 / problem
```

进一步拆分：

```text
stable candidate early stop:
14 questions

4 correct
9 incorrect
1 invalid
```

这说明：

```text
Candidate Formation
已经不是当前最主要问题

Candidate Reliability
才是当前主要问题
```

ARM v1 中：

```text
parseable
≈ stable
≈ final
```

这一假设不成立。

---

# 2. ARM v2 核心目标

ARM v2 不再主要解决：

```text
Should Thinking be ON or OFF?
```

而是解决：

```text
Can this candidate be trusted?

Should we stop?

Should we sample again?

Should we verify?

Should we spend more compute?
```

核心目标：

> 在固定 wall-clock、call budget 和 token budget 下，减少错误 early-stop，并把额外计算集中到不可信 candidate 上。

---

# 3. 核心架构变化

ARM v1：

```text
Problem
↓
OFF
↓
Candidate formed?
├─ yes → Final
└─ no  → Escalate
```

ARM v2：

```text
Problem
↓
Primary Candidate
↓
Candidate Validity
↓
Candidate Trust
↓
┌────────────────────────────┐
│                            │
Trusted                   Uncertain
│                            │
Final                 Second Candidate
                             │
                    Agreement / Conflict
                             │
                ┌────────────┴────────────┐
                │                         │
             Supported                Contested
                │                         │
              Final              Deterministic Check
                                          │
                                    Bounded Resolver
                                          │
                                        Final
```

Thinking ON 从主要 escalation 手段降级为：

```text
Optional Last-resort Compute
```

---

# 4. 设计原则

## 4.1 Parseable != Trustworthy

拆分 candidate 状态：

```text
PARSED
↓
STRUCTURALLY_VALID
↓
SUPPORTED
↓
TRUSTED
↓
FINAL
```

禁止：

```text
parsed
→ directly final
```

---

## 4.2 Verification-first，而不是 Reasoning-more-first

当前错误类型大量是：

```text
模型成功返回
+
答案格式正常
+
答案实际上错误
```

因此当出现一个 candidate 时，下一单位 compute 优先考虑：

```text
验证 / 独立确认
```

而不是：

```text
重新做更长推理
```

---

## 4.3 Runtime Failure 与 Reasoning Failure 分离

必须拆成：

### Runtime Failure

```text
timeout
network error
empty response
provider failure
```

### Reasoning Failure

```text
no candidate
candidate conflict
typed incomplete
structural invalid
```

二者使用不同 recovery policy。

---

## 4.4 Second Sample 是 Selective 的

不恢复固定 voting。

禁止：

```text
每题固定 3 / 5 / 8 candidates
```

采用：

```text
Candidate A
↓
Trust Gate
↓
只有不可信时
才生成 Candidate B
```

---

# 5. 新的总体架构

```text
                         Problem
                            │
                            ▼
                     ProblemContract
                            │
                            ▼
                    ComputePolicy
                            │
                            ▼
                    OFF Candidate A
                            │
                            ▼
                CandidateValidityGate
                            │
             ┌──────────────┴───────────────┐
             │                              │
          invalid                        valid
             │                              │
      Runtime/Parse Recovery       CandidateTrustGate
                                            │
                                 ┌──────────┴──────────┐
                                 │                     │
                              trusted              uncertain
                                 │                     │
                               Final          OFF Candidate B
                                                       │
                                                       ▼
                                             CandidateCompare
                                                       │
                              ┌────────────────────────┴──────────────┐
                              │                                       │
                           agree                                  conflict
                              │                                       │
                    deterministic checks                    deterministic checks
                              │                                       │
                           supported                            unresolved
                              │                                       │
                            Final                            bounded resolver
                                                                      │
                                                                    Final
```

ON fallback：

```text
仍 unresolved
+
ON health available
+
budget permits
↓
ON fallback
```

默认关闭。

---

# 6. Candidate 状态模型

新增：

```python
CandidateState = Literal[
    "parsed",
    "structurally_valid",
    "supported",
    "trusted",
    "rejected",
]
```

---

# 7. CandidateValidityGate

职责：

> 判断这个输出是不是一个合法 candidate。

它不判断数学正确。

例如：

### INTEGER

合法：

```text
117
```

非法：

```text
the answer is:
有：
therefore
```

### RATIONAL

合法：

```text
4/3
```

### CHOICE

合法：

```text
A
C
```

### EXPRESSION

合法：

```text
2x+1
sqrt(3)/2
```

但不能简单接受：

```text
the area is:
```

---

# 8. CandidateTrustGate

输入：

```text
ProblemContract
Candidate
CallResult
Candidate metadata
Runtime state
```

输出：

```python
@dataclass(frozen=True)
class CandidateTrustDecision:
    trusted: bool
    confidence: str
    reason: str
    needs_second_sample: bool
```

---

# 9. 第一版 Trust Policy

保守设计。

只有满足下列条件时才允许 single-sample early stop：

```text
direct reasoning risk
AND
high route confidence
AND
simple answer shape
AND
candidate structurally valid
AND
request completed normally
AND
no truncation
```

即：

```text
Direct + High Confidence
+ Integer / Rational / Choice
→ allow single-sample final
```

其他情况：

```text
single candidate
→ uncertain
→ second sample
```

特别是：

```text
OlymMATH Hard
HLE
structured expression
low-confidence contract
deep reasoning risk
```

不能因为 parser 成功就直接 early-stop。

---

# 10. Selective Consensus

对于 uncertain candidate：

```text
Candidate A
↓
Independent Candidate B
```

B 必须 blind：

```text
不能看到 Candidate A
不能看到 A 的 reasoning
```

目的：

```text
independent evidence
```

---

# 11. Candidate Agreement

如果：

```text
A ≡ B
```

则状态：

```text
supported
```

但：

```text
agreement != mathematical proof
```

因此：

### Low-risk problem

```text
A == B
→ trusted
→ final
```

### High-risk problem

```text
A == B
→ deterministic validation
→ final
```

若 deterministic validation 无法执行：

```text
supported candidate
→ final
```

但 trace 中标记：

```text
verification_status = consensus_supported
```

---

# 12. Conflict Policy

如果：

```text
A != B
```

先进行：

```text
normalization
answer_equivalence
typed constraints
safe deterministic checks
```

仍冲突：

```text
bounded resolver
```

Resolver 只允许：

```text
选择 A
选择 B
无法判断
```

禁止产生：

```text
Candidate C
```

第一版 Resolver：

```text
reasoning_mode = off
max_tokens = 1024~2048
```

---

# 13. Timeout Policy 重设计

v1：

```text
timeout
→ full recovery solve
```

v2：

```text
timeout
→ RuntimeRecoveryPolicy
```

而不是 CandidateTrustPolicy。

---

# 14. RuntimeRecoveryPolicy

定义：

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

# 15. Timeout 实验候选策略

三条候选：

### Policy A — Current

```text
30s full solve
→ timeout
→ second 30s full solve
```

### Policy B — Longer First Call

```text
60s full solve
```

### Policy C — Compact Salvage

```text
30s full solve
→ timeout
→ 10~15s compact answer recovery
```

其中：

```text
Policy A
```

当前 10 个 timeout case：

```text
0 / 10 correct
```

因此必须重新评估。

---

# 16. Compact Salvage

Prompt：

```text
请直接重新求解并尽快形成最终答案。

不要展开长证明。
只保留必要计算。

输出：
Final answer: <answer>
```

特点：

```text
OFF
small max_tokens
short timeout
```

目标不是完成漂亮 reasoning，而是：

```text
在剩余预算里尽可能形成 answer candidate
```

---

# 17. Compute Policy

ARM v2 不再只控制：

```text
reasoning_mode
```

而控制：

```text
call count
token budget
timeout budget
candidate sampling
verification
reasoning mode
```

因此引入：

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

# 18. 推荐 Lane

## FAST

```text
OFF A
↓
high-trust
↓
Final
```

最多：

```text
1 call
```

---

## VERIFY

```text
OFF A
↓
uncertain
↓
OFF B
↓
agreement
↓
Final
```

最多：

```text
2 calls
```

---

## CONFLICT

```text
OFF A
↓
OFF B
↓
conflict
↓
resolver
```

最多：

```text
3 calls
```

---

## ON_FALLBACK

实验性：

```text
OFF paths unresolved
↓
ON
```

只有：

```text
arm_allow_thinking_on=True
```

时允许。

---

# 19. ON Health Gate

ON 不再和正常 capability evaluation 混合。

建立单独：

```text
ON-RAW-HEALTH
```

测试：

```text
workers = 1

timeout:
130s

max_tokens:
512
2048
4096
```

题目：

```text
easy
medium
hard
```

目标：

```text
判断 endpoint 能否返回
```

而不是：

```text
判断数学能力
```

---

# 20. ON Promotion 条件

只有满足：

```text
request success rate 可接受
AND
latency 可接受
AND
比赛预算允许
```

才允许：

```text
ON fallback
```

否则：

```text
arm_allow_thinking_on=False
```

---

# 21. 新指标

ARM v2 不再把：

```text
candidate formation rate
```

作为主要目标。

新增：

```text
candidate acceptance precision

trusted candidate precision

wrong early-stop rate

second-sample trigger rate

consensus precision

conflict rate

resolver accuracy

runtime recovery success rate

correct / call

correct / wall-clock budget
```

---

# 22. 最重要指标

## Wrong Early Stop Rate

定义：

```text
错误但被 Trust Gate 接受的 candidate
/
所有 early-stop candidate
```

目标：

```text
显著低于 ARM v1
```

---

# 23. Candidate Acceptance Precision

定义：

```text
correct trusted candidates
/
all trusted candidates
```

ARM v1 stable early-stop：

```text
4 / 14
≈ 28.6%
```

ARM v2 必须显著提升这个值。

---

# 24. 实验阶段

## E1 ON Raw Health

判断：

```text
ON 是否只是需要更长 latency
```

---

## E2 Timeout Recovery

固定当前 10 个 timeout cases：

```text
A 30+30
B 60
C 30 + compact salvage
```

---

## E3 Candidate Trust

固定当前 14 个 early-stop cases：

```text
ARM v1 single candidate
vs
ARM v2 selective second sample
```

---

## E4 Full OFF-30

```text
current arm-off
vs
arm-v2-selective
```

---

# 25. Promotion 标准

ARM v2 不能只看：

```text
5 correct → 6 correct
```

必须同时观察：

```text
correct ↑
wrong early stop ↓
invalid 不恶化
calls 不失控
latency 不失控
```

优先目标：

```text
把错误 early stop 转化成：
correct
或至少 unresolved

而不是 confident wrong answer
```

---

# 26. 论文层面的研究问题

ARM v1：

> When should an Agent enable Thinking?

ARM v2 可以升级成：

> How should a mathematical agent allocate test-time compute based on candidate reliability under strict inference budgets?

或者：

> Adaptive Candidate Verification and Compute Allocation for Budget-Constrained Mathematical Agents

核心创新结构：

```text
candidate reliability estimation
+
selective resampling
+
bounded conflict resolution
+
runtime-aware compute allocation
```

相比只做 Thinking Router，研究空间更完整。

---

# 27. ARM v2 最终定位

ARM v1：

```text
Adaptive Reasoning Mode
```

ARM v2：

```text
Adaptive Reliability
+
Adaptive Compute
```

核心原则：

> 不要因为模型成功输出了一个答案就停止计算；只有当已有证据足够支持 candidate 时才停止，否则把额外 inference budget 用在最有价值的 verification 或 resampling 上。
