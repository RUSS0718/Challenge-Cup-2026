# ARM-Harness v1 技术设计文档

> Adaptive Reasoning Mode Harness for Competition Math Agent
> Status: Design Draft
> Base: `codex/repo-hygiene-cleanup`
> Target branch: `feat/arm-harness-v1`

## 1. 背景

当前数学 Agent 已具备以下基础结构：

```text
ReasoningAgent
    ↓
ProblemContract
    ↓
HostRouter
    ├─ Direct Harness
    ├─ Deep Harness
    └─ Legacy FSDF
    ↓
Parser / Candidate Ledger
    ↓
final_response
```

Intern-S2 正式版新增了可显式控制的：

```text
thinking_mode = true / false
```

现有 2026-09-27 实验只能证明：

```text
server default / thinking_mode=null
vs
thinking_mode=false
```

存在显著 Runtime Health 差异。

相同 3 题 smoke 中：

```text
default:
36 / 36 requests timeout

thinking=false:
12 / 13 requests success
2 correct / 1 incorrect
```

但当前没有严格的：

```text
thinking_mode=true
vs
thinking_mode=false
```

同题、同配置配对实验。

因此 ARM-Harness v1 不把“Thinking 更强”或“Non-Thinking 更强”作为预设结论，而将 Thinking 视为一种可调的 inference-time compute resource。

---

# 2. 目标

ARM-Harness v1 解决三个问题：

1. Agent 能够按题目和运行中状态动态选择 `thinking=true/false`。
2. Thinking 不再是 Client 全局配置，而是每一次 Model Call 的属性。
3. 在固定时间、调用数和 token budget 下，把计算资源集中到真正需要的题目。

最终目标：

```text
Problem
   ↓
Problem Analysis
   ↓
Reasoning Policy
   ↓
OFF / Adaptive / ON
   ↓
Candidate Formation
   ↓
Conditional Escalation
   ↓
Verification
   ↓
Finalization
```

---

# 3. 非目标

ARM-Harness v1 暂不包含：

- 模型训练或 Fine-tuning；
- PRM / ORM；
- Agent 在线自进化；
- RAG；
- 多智能体通信；
- 固定 5/8 路并行采样；
- 新数学工具系统；
- 运行过程中修改 Error Notebook；
- 根据 metadata 中潜在答案信息进行路由。

ARM-Harness v1 是纯 Agent / Harness 层的 inference policy 改造。

---

# 4. 核心设计原则

## 4.1 Host 决定 Thinking，而不是模型

模型只负责：

```text
Reasoning Engine
```

Host Agent 负责：

```text
When to Think
How Much to Think
When to Stop
When to Escalate
Which Candidate to Keep
```

因此：

```text
LLM != Scheduler
Agent Host = Scheduler
```

---

## 4.2 Candidate-first，而不是 Process-first

Agent 的第一目标不是生成完整漂亮证明，而是：

```text
尽快形成可判定 Candidate
```

随后才判断是否需要：

```text
verification
second solve
thinking escalation
critic
repair
```

避免：

```text
Analyze
→ Branch A
→ Branch B
→ Deepen
→ Finish
```

成为所有题的固定成本。

---

## 4.3 Thinking 是 Escalation Resource

默认策略：

```text
能 OFF 解决
→ 不 ON

OFF 无可靠候选
→ 才考虑 ON

已有稳定候选
→ 不继续 ON
```

也就是说：

```text
Thinking = conditional compute
```

而不是默认流程。

---

# 5. 总体架构

```text
                           Problem
                              │
                              ▼
                    ┌─────────────────┐
                    │ ProblemContract │
                    │                 │
                    │ answer_shape    │
                    │ reasoning_risk  │
                    │ confidence      │
                    │ task signals    │
                    └────────┬────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │ ReasoningModePolicy   │
                 │                       │
                 │ FAST_OFF              │
                 │ ADAPTIVE              │
                 │ DEEP_ON               │
                 └──────────┬────────────┘
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
         FAST_OFF       ADAPTIVE        DEEP_ON
             │              │              │
        OFF Primary     OFF Primary      ON Primary
             │              │              │
             │         Candidate OK?       │
             │          /       \          │
             │        yes       no         │
             │         │         │         │
             │         │    ON Escalate ◄──┘
             │         │         │
             └─────────┴────┬────┘
                            ▼
                    Candidate Ledger
                            │
                    ┌───────┴─────────┐
                    │                 │
                 Stable           Conflict
                    │                 │
                    │        Deterministic Check
                    │                 │
                    │          unresolved only
                    │                 │
                    │           Bounded Critic
                    │                 │
                    └────────┬────────┘
                             ▼
                      Host Finalizer
                             │
                             ▼
                       final_response
```

---

# 6. 新增核心组件

## 6.1 ReasoningMode

统一定义三种调用级模式：

```python
ReasoningMode = Literal[
    "inherit",
    "off",
    "on",
]
```

语义：

```text
inherit
    使用 client 默认设置；
    主要用于兼容旧代码。

off
    请求显式发送 thinking_mode=false。

on
    请求显式发送 thinking_mode=true。
```

ARM 路径禁止依赖 `inherit` 做正式能力实验。

实验中必须明确记录：

```text
off
or
on
```

---

## 6.2 CallPolicy

每一次 LLM 调用拥有独立 Policy：

```python
@dataclass(frozen=True)
class CallPolicy:
    stage: str
    reasoning_mode: ReasoningMode
    max_tokens: int
    temperature: float
```

例如：

```text
primary:
    reasoning_mode = off
    max_tokens = 4096

deep_primary:
    reasoning_mode = on
    max_tokens = 8192

critic:
    reasoning_mode = off
    max_tokens = 2048
```

---

## 6.3 SolvePolicy

一道题的整体计算策略：

```python
@dataclass(frozen=True)
class SolvePolicy:
    lane: Literal[
        "fast_off",
        "adaptive",
        "deep_on",
    ]

    initial_mode: ReasoningMode
    escalation_mode: ReasoningMode | None

    max_calls: int
    token_budget: int
```

---

# 7. Router 设计

现有 `ProblemContract` 继续保留：

```text
answer_shape
reasoning_risk
route_confidence
```

ARM 不重新设计数学分类系统。

ReasoningModePolicy 在其上增加：

```text
ProblemContract
       ↓
Compute Policy
```

第一版规则：

| ProblemContract | ARM Lane |
|---|---|
| direct + scalar/choice + high confidence | FAST_OFF |
| structured / medium confidence | ADAPTIVE |
| high reasoning risk | ADAPTIVE |
| unknown / mixed | ADAPTIVE |
| proof / long-form | ADAPTIVE 或 legacy control |

在 `thinking=true` 尚未通过 capability/health gate 前：

```text
DEEP_ON 不进入默认 submission。
```

架构支持 DEEP_ON，但由 feature flag 控制。

---

# 8. 三条 Lane

## 8.1 FAST_OFF

适合：

```text
choice
scalar
direct calculation
high-confidence contract
```

执行：

```text
OFF Primary
    ↓
Candidate parsed?
    ├─ yes → Finalize
    └─ no  → OFF Recovery
```

推荐：

```text
max calls = 2
```

无需 Thinking。

---

## 8.2 ADAPTIVE

ARM-Harness 的核心路径。

执行：

```text
OFF Primary
      │
      ▼
Candidate Assessment
      │
 ┌────┴──────────┐
 │               │
Stable        Unresolved
 │               │
Stop        Thinking allowed?
                 │
          ┌──────┴──────┐
          │             │
         yes            no
          │             │
      ON Escalate    OFF Recovery
          │
          ▼
      Candidate
```

这是整个新架构最重要的一点：

```text
difficulty 不只在 solve 前估计，
还通过 solve 过程中的实际失败信号暴露。
```

---

## 8.3 DEEP_ON

只用于通过实验 Gate 后的高风险问题。

```text
ON Primary
    ↓
Candidate
    ↓
OFF / deterministic verification
```

禁止：

```text
ON Solver
→ ON Reviewer
→ ON Critic
→ ON Finalizer
```

因为这会重新回到不可控 compute expansion。

---

# 9. Online Escalation Signals

ARM 不只使用静态题目难度。

Primary call 后读取：

```text
candidate_count
parse_status
finish_reason
timeout
request_error
typed_complete
answer_conflict
remaining_calls
remaining_tokens
remaining_wall_time
```

触发 Thinking escalation 的典型情况：

```text
no candidate
typed incomplete
parse failure
明显 truncation
first candidate structurally invalid
candidate conflict
```

不触发 escalation：

```text
已经形成唯一、闭合、可解析候选
仅仅因为回答很短
仅仅因为题目文本很长
仅仅因为 domain 看起来复杂
```

---

# 10. Candidate Ledger

继续采用 Host-owned Candidate Ledger。

每个 Candidate 至少记录：

```text
candidate_id
value
normalized_value
source_stage
reasoning_mode
parse_status
verification_status
finish_reason
```

必须能够回答：

```text
这个 Candidate 是 OFF 得到的？
还是 ON 得到的？
```

后续实验才能分析：

```text
OFF → correct
ON → correct
OFF wrong → ON correct
OFF correct → ON wrong
```

---

# 11. Verification Policy

优先级：

```text
1. Exact normalization
2. Candidate equivalence
3. Deterministic host check
4. Existing typed verifier
5. Bounded LLM critic
```

LLM critic 是最后手段。

原则：

```text
不要为了验证一个答案，
重新完整求解整个问题。
```

---

# 12. Finalizer

默认：

```text
Host Finalizer
```

负责：

```text
strip wrappers
normalize answer shape
produce final_response
```

原则上：

```text
0 LLM calls
```

只有 Host 无法安全完成协议闭合时，才允许一个：

```text
OFF Finalizer
```

禁止 Thinking Finalizer。

---

# 13. Budget Model

Budget 必须在 Route 之后建立。

当前：

```text
HarnessConfig.effective_call_limit
```

在 `enable_deep_lane=True` 时会提前将整个 Harness 的 call limit 压到 deep cap。

ARM 改为：

```text
Problem
  ↓
Route
  ↓
SolvePolicy
  ↓
BudgetLedger
```

例如：

```text
FAST_OFF
calls = 2

ADAPTIVE
calls = 3

DEEP_ON
calls = 2~3
```

Token budget 同理按 lane 分配。

---

# 14. Client 调用模型

现有：

```python
client.chat(
    messages,
    temperature,
    max_tokens,
)
```

修改为：

```python
client.chat(
    messages,
    temperature,
    max_tokens,
    reasoning_mode="off",
)
```

关键约束：

**禁止通过修改：**

```python
client.thinking_mode = ...
```

动态切换模式。

原因：

```text
ReasoningAgent 允许多题并发；
共享 Client mutable state 会产生 race condition。
```

必须让 reasoning mode 成为 request-local 参数。

---

# 15. Trace 设计

每次调用至少记录：

```json
{
  "stage": "primary",
  "reasoning_mode": "off",
  "requested_tokens": 4096,
  "completion_tokens": 521,
  "finish_reason": "stop",
  "duration_ms": 4213,
  "status": "ok"
}
```

Route Trace：

```json
{
  "stage": "arm_route",
  "lane": "adaptive",
  "answer_shape": "scalar",
  "reasoning_risk": "structured",
  "route_confidence": "medium",
  "initial_mode": "off",
  "escalation_mode": "on"
}
```

Escalation Trace：

```json
{
  "stage": "arm_escalation",
  "from": "off",
  "to": "on",
  "reason": "no_extractable_candidate"
}
```

---

# 16. Feature Flags

新增：

```python
enable_arm_harness: bool = False

arm_allow_thinking_on: bool = False

arm_default_lane: str = "adaptive"

arm_fast_max_calls: int = 2
arm_adaptive_max_calls: int = 3
arm_deep_max_calls: int = 3

arm_fast_token_budget: int = 8192
arm_adaptive_token_budget: int = 16384
arm_deep_token_budget: int = 16384
```

第一阶段：

```text
enable_arm_harness = experimental only
```

不得立刻替换 `SUBMISSION_CONFIG`。

---

# 17. 实验 Arms

必须建立四个明确实验 Arm。

### ARM-A

```text
Always OFF
```

目标：

建立正式版新的稳定 baseline。

### ARM-B

```text
Always explicit ON
```

目标：

第一次真正建立 Thinking ON baseline。

### ARM-C

```text
Static Routing
FAST → OFF
DEEP → ON
```

目标：

验证静态 compute allocation。

### ARM-D

```text
OFF-first
→ conditional ON
```

目标：

验证 Adaptive Escalation。

四组必须使用：

```text
same item IDs
same code
same prompt
same timeout
same retry
same workers
same token caps

only inference policy differs
```

---

# 18. Promotion Gate

ARM-Harness 不以：

```text
invalid ↓
timeout ↓
```

直接作为能力提升结论。

至少观察：

```text
correct
incorrect
invalid
request success
timeout
calls/problem
tokens/problem
latency
candidate formation rate
reasoning escalation rate
```

最重要指标：

```text
correct answers
under fixed total inference budget
```

ARM-D 进入 submission 的最低要求：

```text
correct 不低于 Always OFF baseline
AND
平均 compute cost 可接受
AND
invalid 不恶化
AND
不存在明显 OFF-correct → ON-wrong 大量反转
```

---

# 19. Rollback

任何时候出现：

```text
ON timeout 爆炸
invalid 显著升高
call budget 不可控
并发 reasoning mode 污染
parser regression
```

直接：

```text
disable enable_arm_harness
```

回到当前：

```text
ConstraintFit Harness
+ Deep
+ Hybrid FSDF
```

旧路径不删除。

---

# 20. v1 最终定位

ARM-Harness v1 不试图让模型：

> “想得更多”。

它解决的是：

> “什么时候值得让模型想更多”。

核心：

```text
Static Problem Signals
        +
Online Candidate Signals
        ↓
Adaptive Compute Allocation
        ↓
Reasoning Mode Selection
        ↓
Candidate-first Early Stop
```

最终架构定位：

> 在严格 inference budget 下，由 Host Agent 根据题目先验与候选形成状态动态控制 Intern-S2 的 reasoning mode、调用次数和 token budget。
