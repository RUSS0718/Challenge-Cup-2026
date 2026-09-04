# FSDF-V1-CODE-ACCEPTANCE-001 代码验收规范

状态：`REVISED / CODE_ACCEPTANCE_ONLY / ZERO_MODEL_CALLS`

方法 ID：`fork_select_deepen_finish_v1`

本规范只验收 Analyze–Fork–Select/Deepen–Finish（FSDF）的代码结构、难题路由、五阶段调用编排、18432 token 硬上限、上下文压缩、答案降级、接口兼容和并发隔离。它不是能力实验，不产生正确率结论，不授权修改 `SUBMISSION_CONFIG`、提交远端或申请官方评测。

代码验收与发布分层：`AgentConfig()` 的验收基线保持 FSDF 默认关闭；本次代码验收完成后，
用户可另行授权将官方 `SUBMISSION_CONFIG` 切换为 FSDF 默认路径。该发布动作不改变本规范的
零模型调用和无能力结论边界，且必须单独记录。

## 1. 固定方法定义

### 1.1 难题主路径

```text
Agent A：Analyze / 问题拆解（2048）
                  │
          ┌───────┴───────┐
          ▼               ▼
Agent B：思路一（2048）  Agent C：思路二（2048）
          └───────┬───────┘
                  ▼
Agent D：选择一条思路并深推（8192）
                  │
                  ▼
Agent E：继承 D 的 handoff 收尾（4096）
                  │
                  ▼
            final_response
```

- B/C 只提出方法，不展开完整长推导，不输出正式 `FINAL`。
- B/C 接收同一份 A 分析，互相不可见。
- D 必须明确选择 B 或 C 中的一条；不得把两条方法混成第三种方法。
- D 在选定方法后投入主要推理预算，并把尚未完成的状态传给 E。
- E 只沿 D 选定的路径补完、局部纠错和形成终答，不重新进行方法竞赛。
- A→B→C→D→E 默认顺序执行；B/C 逻辑并列，但单次 `solve()` 内不得启动线程、进程或异步任务。

固定 token 序列：

```text
[2048, 2048, 2048, 8192, 4096]
```

单题最多 5 次 `client.chat()`；配置 token 上限合计必须严格等于 `18432`，任何外部配置不得抬高。

### 1.2 简单题兼容路径

只有现有确定性简单算式识别器明确命中的 L0 才走兼容路径：

```text
原题 → 单次 Direct Solve（4096）→ final_response
```

- L0 最多 1 次调用。
- 选择、填空、证明、解释或“最终答案为 scalar”本身都不能判为 L0。
- OlymMATH/AIME 式长题即使最终答案是数字，也必须走难题主路径。
- 不得新增按题号、数据集、学科标签、题面片段或 `metadata` 的路由。

### 1.3 时间上限

- soft deadline：900 秒；达到后不得启动新阶段，从已有 D/B/C 状态终结。
- hard deadline：1080 秒；达到后立即终结，不再调用模型。
- 所有阶段共享同一个 solve-local `time.monotonic()` 起点。
- 任一阶段失败不重试，不增加第 6 次调用。

## 2. Module 与 seam

新增一个深 Module，建议位置：

```text
reasoning_agent/fork_select_deepen_finish.py
```

赛事唯一外部 seam 保持不变：

```python
ReasoningAgent.solve(problem: str, metadata: dict) -> dict
```

Relay Module 的最小 Interface：

```python
ForkSelectDeepenFinishRelay(client, clock=time.monotonic).solve(
    problem: str,
    problem_type: str,
) -> RelayResult
```

Interface 不暴露 A–E 的内部函数、Prompt、parser 或状态容器。`client` 只要求公开契约：

```python
client.chat(messages, temperature, max_tokens) -> str
```

禁止访问 client 私有字段，禁止创建新 client Adapter，禁止引入 LangGraph、AgentScope、队列、数据库或新第三方依赖。

`user_agent.py` 只允许增加薄接入：题型识别后交给 Relay Module，再将 `RelayResult` 转成赛事字典。A–E 的实现不得继续堆入 `ReasoningAgent.solve()`。

## 3. Solve-local 状态

每次 `solve()` 独立持有：

```text
started_at
logical_calls
stage_status
analysis_packet_a
idea_packet_b
idea_packet_c
selected_branch
deep_handoff_d
finish_packet_e
candidate_history
sanitized_errors
```

不得用类字段、模块全局变量或磁盘文件保存题目状态。三个并发 `solve()` 之间不得共享候选、预算、计时器或 trace。

## 4. A：难题拆解契约

预算：`max_tokens=2048`，temperature=0.2。

A 不负责完成整题，只生成：

```text
GOAL: 题目真正要求
ANSWER_TYPE: 整数/分数/表达式/集合/证明结论等
CONSTRAINTS: 定义域、整数性、边界、唯一性
STRUCTURE: 题目的核心数学结构
BOTTLENECK: 最困难的唯一环节
```

要求：

- 状态包最多 1800 字符；
- 不输出 `FINAL`；
- A 输出不直接参与最终答案选择；
- 字段缺失时使用确定性首尾裁剪，不能终止后续阶段。

## 5. B/C：双思路分叉契约

B/C 的预算均为 `max_tokens=2048`，temperature=0.6。

两者接收：完整原题 + 完全相同的 A 状态。

B 使用标准构造/正向推导方向；C 使用与 B 明确不同的方向，例如反推、极值、不变量、分类讨论、几何变换或模运算。

每个思路包只能包含：

```text
BRANCH: B 或 C
METHOD: 方法名称
KEY_LEMMA: 必须成立的关键引理
PLAN: 不超过 6 个步骤
EXPECTED_FORM: 预期答案形式
RISK: 该方法最可能失败的位置
```

要求：

- 每个思路包最多 1600 字符；
- B/C 不展开完整证明，不做大段计算；
- B/C 不输出 `FINAL`，其文本不能直接成为 `final_response`；
- B 不得看到 C 的输出，C 不得看到 B 的输出；
- B/C 提出等价方法时仍继续进入 D，但 trace 必须标记 `ideas_not_diverse`。

## 6. D：选择并深推契约

预算：`max_tokens=8192`，temperature=0.2。

D 接收：完整原题、A 状态、B 思路包、C 思路包。

D 首先必须输出：

```text
SELECTED_BRANCH: B 或 C
SELECTION_REASON: 基于约束覆盖、关键引理可证性和闭环长度的一句话理由
CANDIDATE_D: 当前候选或 UNKNOWN
```

随后仅沿选定分支深度推理。正常路径禁止融合 B/C；如果选定方法在推导中出现可证伪矛盾，D 可以标记：

```text
SELECTED_BRANCH_FAILED: <原因>
```

但不得重新调用 B/C，也不得启动新分支。此时 D 可以把未完成状态交给 E，由 E 决定局部修复或返回候选。

D 传给 E 的 handoff：

```text
SELECTED_BRANCH: B 或 C
CANDIDATE_D: 当前候选或 UNKNOWN
DERIVED: 已经确认的关键等式/结论
OPEN: 尚未完成的唯一步骤
CHECKS: 已验证的定义域、边界和反例
RISK: 尚未排除的错误
```

要求：

- D handoff 最多 5000 字符；
- D 可以输出 `FINAL_D`，但 E 仍负责最终收尾；
- D 不得把未选择分支的完整文本复制进 handoff；
- D 的主要推理内容不得写入 trace。

若 `SELECTED_BRANCH` 缺失、不是单一的 `B`/`C`、选择了不可用分支，或无法解析，D 视为协议失败：
保留 D 中合法的 `FINAL_D`、`CANDIDATE_D`、完整 boxed 或独立数学行作为后续降级候选，
但不得把 D handoff 字段或原始自由文本传给 E。此时 E 使用确定性回退分支；B/C 均可用时固定选择标准路径 B，
只有一支可用时选择该支。

## 7. E：收尾契约

预算：`max_tokens=4096`，temperature=0.0。

E 接收：完整原题、A 的约束摘要、D 选择的方法和 D handoff。E 不接收未选择分支的完整思路包。

E 的职责：

1. 核对 D 的关键等式和题目目标；
2. 从 `OPEN` 继续，不重新做方法选择；
3. 只修复选定链路中的局部错误；
4. 第一项输出 `CANDIDATE_E`，末尾输出唯一 `FINAL`。

如果 D 已经完成，E 只做短复核和答案规范化。如果 D 未完成，E 使用4096预算补完。

## 8. 上下文压缩上限

| 内容 | 最大字符数 |
| --- | ---: |
| A 状态包 | 1800 |
| A 缺失字段时 fallback | 5000 |
| B 思路包 | 1600 |
| C 思路包 | 1600 |
| D 接收的接力上下文（不含原题） | 6000 |
| D handoff | 5000 |
| E 接收的接力上下文（不含原题） | 6500 |

裁剪函数必须保证返回字符串总长度不超过调用者给出的上限，包括省略标记。

中间状态是建议格式，不是硬 parser 门。D handoff 字段缺失时，继续传递已经识别的允许字段，
并增加 `HANDOFF_INCOMPLETE: true`；不得逐项填充 `UNKNOWN`，也不得把任意 D 原始自由文本传给 E。
E 的接力上下文必须预留至少 2000 字符给 D handoff；A 摘要和选中思路只能压缩到剩余配额。

## 9. 最终答案选择

固定优先级：

```text
E.FINAL
→ E.CANDIDATE_E
→ D.FINAL_D
→ D.CANDIDATE_D
→ D 中完整 boxed
→ E/D 中独立纯数学答案行
→ UNKNOWN
```

B/C 只提供思路，不进入答案优先级。A 不提供答案。

要求：

- 后一级只能在前一级缺失或为占位符时使用；
- 拒绝 `<answer>`、`<result>`、格式示例和 `UNKNOWN`；
- boxed 必须闭合；
- 独立数学行必须完整，不能从正文句子中抽取最后一个数字；
- 不读取 gold，不调用 judge，不按本地题号选择答案；
- 全部失败时仍返回可序列化字典和非空 `final_response="UNKNOWN"`。

## 10. 错误与降级矩阵

| 故障 | 必须行为 |
| --- | --- |
| A 失败 | B/C 仅依据原题给思路；仍进入 D/E |
| B 失败 | D 选择 C；不得等待或重试 B |
| C 失败 | D 选择 B；不得等待或重试 C |
| B/C 都失败 | D 使用固定 direct fallback 深推，不产生新模型分支 |
| D 失败 | E 使用 A + 确定性回退的可用 B/C 思路收尾；D 原始自由文本不传给 E，但合法 D 答案字段仍可按第9节降级 |
| E 失败 | 按 D.FINAL_D → D.CANDIDATE_D 降级 |
| soft deadline | 不启动下一阶段，从最新 D/E 候选终结 |
| hard deadline | 立即终结，不再调用 client |
| 所有响应不可解析 | `UNKNOWN`，总调用仍不得超过5 |

异常只记录类别，如 `timeout`、`rate_limit`、`http_status`、`invalid_response`；不得记录异常对象、URL、凭证或完整响应。

D 的 `SELECTED_BRANCH` 非法或不可解析时，最后一次 D 事件必须记录
`stage=deepen`、`status=protocol_failed`、`error_category=invalid_response`。

## 11. Trace 契约

允许字段：

```text
method
stage
status
model_calls
max_tokens
packet_present
selected_branch
candidate_present
final_present
fallback_source
elapsed_bucket
error_category
ideas_not_diverse
```

禁止字段：完整题目、完整 Prompt、完整响应、未裁剪接力包、凭证、gold。

最后一个事件必须记录：

```text
stage=finalize
model_calls=<0..5>
fallback_source=<finish_final|finish_candidate|deep_final|deep_candidate|boxed|math_line|unknown>
```

## 12. 必须实现的零模型测试

使用只实现 `chat(messages, temperature, max_tokens)` 的 `ScriptedClient`，不得连接真实端点。

| ID | 测试场景 | 验收条件 |
| --- | --- | --- |
| T01 | 默认配置分层 | `AgentConfig()` 的 FSDF 默认关闭；验收快照不修改 `SUBMISSION_CONFIG`；若已获单独发布授权，则官方 profile 可显式 FSDF 开启且 contextual 关闭 |
| T02 | 路径互斥 | FSDF 与 contextual/KCV/PS-C/V5 同时开启时 fail-fast；BTCS 组合因当前基线缺失 `reasoning_agent.btcs`/`protocol_mode` 标记 N/A |
| T03 | L0 兼容 | 恰好1次调用，token序列 `[4096]` |
| T04 | 长 scalar 路由 | 最终答案是数字也走难题主路径，不因 calculation 标签旁路 |
| T05 | 完整难题路径 | 恰好5次调用，token序列 `[2048,2048,2048,8192,4096]`，合计18432 |
| T06 | 分叉输入一致 | B/C 收到相同 A 状态；B 不含 C；C 不含 B |
| T07 | B/C Prompt 差异 | B 是标准方法，C 是替代方法，Prompt hash 不同 |
| T08 | B/C 只给思路 | B/C 输出不进入 final_response，不要求 `FINAL` |
| T09 | 思路包长度 | B/C 各≤1600字符，超长确定性裁剪 |
| T10 | D 只选一支 | `SELECTED_BRANCH` 只能为 B/C；handoff 不含未选择分支全文 |
| T11 | D 深推预算 | D 恰好使用8192上限；不能拆成多个调用 |
| T12 | E 只接选中路径 | E 不得看到未选择分支的完整思路包 |
| T13 | E 收尾预算 | E 使用4096上限并输出候选优先、FINAL末尾 Prompt |
| T14 | 状态缺字段 | 中间 packet 不完整仍继续，不提前 `UNKNOWN` |
| T15 | A 失败 | B/C/D/E按降级矩阵运行，总调用≤5 |
| T16 | B 失败 | D选择C，不重试B |
| T17 | C 失败 | D选择B，不重试C |
| T18 | B/C双失败 | D使用固定direct fallback，不增加调用 |
| T19 | D 失败 | E 获得可用思路并完成收尾；B/C 均可用时确定性回退 B，单支可用时回退该支 |
| T20 | E 失败 | 严格降级到D答案，不新增调用 |
| T21 | 答案优先级 | 分别构造E.FINAL、E候选、D.FINAL、D候选、boxed和math-line fixture |
| T22 | 禁止B/C抢答 | B/C中出现数字或伪FINAL不能覆盖D/E |
| T23 | 占位符 | `<answer>`、`<result>`、`UNKNOWN`不得接受 |
| T24 | 禁止正文捞数 | 多个中间数字但无显式答案时不得取尾部数字 |
| T25 | soft deadline | 假时钟达到900秒后不启动新调用 |
| T26 | hard deadline | 假时钟达到1080秒后调用数不增加 |
| T27 | 三并发隔离 | 3个并发solve的预算、状态、选择和trace不串题 |
| T28 | 接口与JSON | 官方式构造、额外构造参数、非空final_response、JSON序列化通过 |
| T29 | trace卫生 | 不含题目、Prompt、raw response、凭证或gold |
| T30 | metadata卫生 | metadata中任意answer/gold字段不影响调用和结果 |
| T31 | 无内部并发 | 不创建ThreadPool、async任务、进程或子线程 |
| T32 | 预算不可抬高 | 外部配置更大时仍钳制为5次和18432 token |
| T33 | D 选择非法 | D 记为 `protocol_failed/invalid_response`；E 不接收 D raw，但合法 D 答案仍可严格降级 |
| T34 | D handoff 字段不完整 | E 只收到已识别字段和 `HANDOFF_INCOMPLETE: true`，不收到任意 D raw 或逐项 `UNKNOWN` |
| T35 | 最大上下文接力 | A/选中思路超长时仍为 D handoff 固定预留至少2000字符，E 上下文（不含原题）≤6500 |
| T36 | B 不可用但 D 选 B | 记 `protocol_failed/invalid_response`，E 只接 C 和不完整 handoff，不接 D handoff/raw |
| T37 | C 不可用但 D 选 C | 记 `protocol_failed/invalid_response`，E 只接 B 和不完整 handoff，不接 D handoff/raw |

## 13. 验收命令

```powershell
python -m unittest tests.test_fork_select_deepen_finish -v
python -m py_compile user_agent.py reasoning_agent/fork_select_deepen_finish.py tests/test_fork_select_deepen_finish.py
python -m unittest discover -s tests -q
git diff --check
```

验收口径：

- T01–T37 全部通过；T02 的 BTCS 组合按当前基线能力标记 N/A，不计为失败；
- 全量测试相对实现前冻结快照不得新增 failure/error；既有无关失败原样报告，不得伪报全绿；
- `py_compile`、`git diff --check` 通过；
- 不新增 requirements；
- 零真实模型调用；
- 代码验收阶段不修改 `SUBMISSION_CONFIG`；任何验收后的默认切换必须作为单独授权的发布动作记录；
- 不 commit、不 push。

## 14. 必备交付物

```text
reasoning_agent/fork_select_deepen_finish.py
tests/test_fork_select_deepen_finish.py
docs/experiments/FSDF-V1-CODE-ACCEPTANCE-001/result.md
docs/experiments/FSDF-V1-CODE-ACCEPTANCE-001/report.json
docs/experiments/FSDF-V1-CODE-ACCEPTANCE-001/run_manifest.json
```

`report.json` 至少包含：

```json
{
  "method_id": "fork_select_deepen_finish_v1",
  "zero_model_calls": true,
  "target_tests_passed": 0,
  "target_tests_failed": 0,
  "max_logical_calls_observed": 0,
  "max_token_cap_sum_observed": 0,
  "observed_hard_token_sequence": [],
  "l0_calls_observed": 0,
  "selected_branch_only_passed": false,
  "finish_excludes_rejected_branch": false,
  "three_solve_isolation_passed": false,
  "trace_hygiene_passed": false,
  "submission_config_unchanged": false,
  "verdict": "IN_PROGRESS"
}
```

禁止填写未实际运行得到的数字。

## 15. 最终裁决

只有 T01–T37、预算门、接口门、trace卫生和编译门全部通过，才可标记：

```text
CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION
```

以下任一情况直接 `CODE_REJECTED`：

- 难题超过5次调用或18432 token配置总和；
- 长 scalar 被 calculation 分类后错误进入简单路径；
- B/C看到对方输出；
- B/C展开完整长解答并直接参与答案选择；
- D 未明确选择 B/C、选择不可用分支且实现没有按 §6/T33/T36/T37 执行 `protocol_failed` 降级，或把两条方法拼成第三条；
- E收到未选择分支的完整文本；
- 中间packet失败导致整题提前终止；
- 从正文任意捞数字；
- trace泄露题目、完整响应、凭证或gold；
- 读取metadata答案字段；
- 修改默认提交配置；
- 新增依赖、内部并发、子进程或无界接力循环。

代码验收通过只证明结构忠实、预算受控，可以进入后续真实 fidelity/能力验证；不得据此声称正确率提升。
