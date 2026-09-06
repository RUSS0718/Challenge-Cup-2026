# FESF v1：证据合成 Harness、独立 Skill 与单题记忆升级规格

状态：`IMPLEMENTED / CODE_ACCEPTED / LOCAL_FESF_DEFAULT / MODEL_EXPERIMENT_DEFERRED / NO_RELEASE`

方法 ID：`fork_evidence_synthesize_finish_v1`（简称 `FESF v1`）

日期：2026-09-06

## 0. 本规格的授权边界

本规格的代码、Skill 与单题记忆部分已完成并通过零模型工程验收；真实模型资格/能力窗按
用户决定暂缓，因此本轮不执行模型调用。已完成的范围是：

1. 保留 FSDF v1 作为显式回退 runner 臂；
2. 实现新的 FESF v1 候选，并在当前本地评测 profile 默认打开；
3. 在独立目录中开发并完成首个数学 Skill 的工程验收；
4. 在独立目录中实现单题记忆，并固定离线错题经验沉淀边界；
5. 扩展双臂 runner 与零模型验收工件。

以下模型实验仍是后续可选阶段：在得到明确启动指示后，最多使用 180 分钟完成资格窗和
两个能力窗；本状态不对 FESF 的数学正确率作结论。

本地 `SUBMISSION_CONFIG` 打开 FESF 仅用于当前用户授权的本地新体系测试；这不等同于
正式发布授权。以下动作仍需分别授权：推送 GitCode main、修改赛事作品、使用官方隐藏题
信息更新运行时代码。代码验收、Skill 验收和本地 A/B 均不自动产生上述发布授权。

## 1. 已确认事实、设计判断与未验证项

### 1.1 已确认

- FSDF v1 的官方证据锚为 `de74934`；仓库记录为 correct 14 / incorrect 61 /
  invalid 37。
- 当前本地 `SUBMISSION_CONFIG` 打开 FESF v1 与 `exact-evaluation`；FSDF v1 仍由
  `fsdf_v1_tkoff` runner 臂显式提供，六个可靠性 canary 保持关闭。历史 canary 官方结果
  correct 7/112 仅作回滚背景，不作为本轮能力证据。
- 本地 `thinking_off` 是 `InternChatClient`/runner 的请求参数，不是
  `ReasoningAgent(client=official_client)` 三参数公开契约的一部分。
- 迭代 10–12 表明本地关闭思考后阶段截断和耗时大幅下降，但正确数没有自动提高；
  迭代 12 的固定路线强制遵从造成两例 correct→incorrect。
- 当前运行器支持逐题追加 `answers.jsonl` 和按 `(set_id, item_id, arm)` 恢复未完成任务。
- 官方规则要求每个 `solve` 独立，不能假设固定题序、同一进程或跨调用状态保留。

### 1.2 设计判断

- 新 Harness 应在宿主侧增加状态、证据和路由能力，不继续增加固定数学路线约束。
- D 应选择一条主线，但另一分支保留为辅助证据来源；只有命题级硬证据可以产生
  `REFUTED`，不能把未选分支整体判错。
- Skill 的 `name`/`description` 负责可靠触发；Skill 正文负责程序步骤；确定性工具负责
  新事实。三者的验收必须分开。
- 单题记忆可以在一个 `solve` 的 Python 局部状态中跨 A–E 保存；它只有被宿主重新渲染到
  messages 中时才会被下一次模型调用看见。
- 跨题经验不应在正式评测运行中在线学习。它应在评测后离线审计、去题目特化、验收，
  再作为新版本 Skill 进入下一次运行。

### 1.3 尚未验证

- 官方 client 是否允许参赛代码控制 `thinking_mode=False`。
- FESF、首个 Skill 或单题记忆是否提高困难题正确数。
- 模型能否稳定地产生首个 Skill 要求的受限工具请求。
- 官方运行目录是否可写、是否跨题复用、是否在下一轮评测继续存在。FESF 不依赖这些
  未验证条件。

## 2. 方法边界与成功标准

### 2.1 目标

在不增加模型调用数和单阶段 token 上限的前提下：

1. 保留一条不受 Skill 强制的自由求解路径；
2. 让另一条路径使用经过独立验收的 Skill，并向确定性工具提出受限请求；
3. 把 B、C、工具和 D 的完整命题保存为有来源、有状态的单题记忆；
4. 让 D 在命题层选择主线、借用辅助事实、记录反证和未决冲突；
5. 让 E 根据原题和有界证据完成唯一 `final_response`；
6. 用两个新的、互不重叠的困难题窗口判断端到端正确率是否改善。

### 2.2 非目标

- 不把旧 `math_routes_v1`、方法卡 RAG、模型生成 Python、PoT/TIR 或旧 substitution
  协议改名复活。
- 不实现完整 Deep Agents、LangGraph checkpointer、数据库、向量检索或跨题在线学习。
- 不并行发起 B/C 模型请求。官方同时运行三个 Agent，内部并行会扩大端点瞬时并发；
  FESF v1 保持物理串行、逻辑分支。
- 不用题号、题面原文、gold、数据来源或 `metadata.subject/source` 做运行时路由。
- 不因 Skill 被选中、步骤写满或模型自称“已验证”而提高命题可信度。
- 不把 invalid 降低、trace 更完整、耗时下降或工具执行成功表述为数学能力提升。

### 2.3 Definition of Done

FESF v1 只有同时满足以下条件才算完成本规格：

- 回退提交在干净快照中恢复 FSDF v1 可观察行为，并保留后续代码为默认关闭；
- 新方法、Skill 目录、记忆目录和 runner 臂均有代码与测试；
- 全部零模型工程门通过；
- 首个 Skill 通过独立工程门；真实 Skill 资格门暂缓；
- 两个 fresh 能力窗在 180 分钟总预算内完成或按止损规则提前结束（本轮暂缓）；
- 工件、manifest、逐题答案、报告、结果与排除表处置全部落盘；
- 未经另行授权不切换 FESF 默认、不提交赛事作品、不推送发布。

## 3. 阶段 R：恢复正式 FSDF v1 基线

### 3.1 两个不同的基线

必须区分：

1. `release_anchor_fsdf_v1`：`de74934` 的官方运行行为，思考模式由官方 client 决定；
2. `local_control_fsdf_v1_tkoff`：FSDF v1 行为不变，但本地
   `InternChatClient(thinking_mode=False)`；仅用于与 FESF 的同窗 A/B。

本地 `thinking_off` 成绩不能直接归属于 `release_anchor_fsdf_v1`，除非官方公开 client
明确暴露并实际应用同一控制字段。

### 3.2 回退方式

- 先用只读命令重新核对 GitCode main、当前 `SUBMISSION_CONFIG`、官方日志和工作树范围。
- 使用新的前向回退提交恢复运行行为，不 `git reset --hard`、不 force-push、不删除六开关
  实现和历史工件。
- `SUBMISSION_CONFIG.enable_fork_select_deepen_finish` 保持 `True`。
- 以下六个 canary 开关恢复为 `False`：
  `enable_fsdf_diagnostics_v2`、`enable_fsdf_multiline_handoff_v2`、
  `enable_fsdf_final_confirmation_v2`、`enable_fsdf_finish_prompt_v2`、
  `enable_fsdf_handoff_first_d`、`enable_fsdf_d_result_to_e`。
- 其它迭代候选开关保持默认关闭；不顺手清理相邻代码。
- 发布前显式暂存命名文件/代码块，保留当前工作树中与本任务无关的修改和未跟踪文件。

### 3.3 回退完成标准

- 对同一 ScriptedClient 序列，回退后的模型请求、调用次序、token 上限和
  `final_response` 与 `de74934` 一致；允许新增但行为中性的诊断字段单独列明。
- 非 L0 仍为五次逻辑调用，token 序列为
  `[2048, 2048, 2048, 8192, 4096]`；L0 仍为一次 4096。
- `ReasoningAgent(client=official_client)`、`solve(problem, metadata)` 和 JSON 返回契约通过。
- 回退验证不使用真实模型正确率证明。
- 推送 GitCode main 仍需用户在看到差异、测试和目标 commit 后明确授权。

## 4. 阶段 A：FESF v1 架构

### 4.1 五调用顺序

FESF v1 复用 FSDF v1 的调用和 token 总预算，不追加恢复调用：

| 次序 | 阶段 | 职责 | token 上限 |
|---|---|---|---:|
| 1 | A / Analyze + route | 提取目标、约束和答案类型；只依据 name/description 选择一个 Skill 或 NONE | 2048 |
| 2 | B / Free branch | 不加载 Skill 正文，保持自由求解 | 2048 |
| 3 | C / Skill branch | 宿主加载 A 选中的一份 Skill 正文，形成互补候选和工具请求；NONE 时走普通互补求解 | 2048 |
| 4 | D / Evidence synthesis | 选择主线、借用辅助命题、处理工具证据和冲突 | 8192 |
| 5 | E / Finish | 回到原题完成唯一终答 | 4096 |

本地两个实验臂都使用 `thinking_mode=False`。宿主文件读取、Skill 加载、工具执行、
记忆更新和证据渲染不计模型调用，但都受单题 20 分钟和本规格软/硬截止约束。

### 4.2 B/C 调度

- B 和 C 是逻辑分支，物理执行仍为 B 后 C；不存在 C 完成后等待尚未启动的 B。
- B 保持自由路径，Skill 误选不能同时绑架 B/C。
- A 的第一行必须是 `SKILL_CHOICE: <id> | NONE`，第二行为
  `APPLICABILITY: <适用条件是否成立>`；A 同时完成原有问题分析，选择不单独占用模型调用。
- A 只看至多 3 个已验收 Skill 的 `name`/`description`，看不到正文；宿主在 A 返回后校验
  ID，并只把选中 Skill 的正文注入 C。
- A 选择不存在、未通过验收或不适用的 Skill，或声明缺失/不可解析时，宿主记录原因并把
  选择降为 `NONE`；C 走普通互补求解，不触发任意隐藏 fallback，也不把 A 整阶段判失败。
- C 不再次选择 Skill。这样才能在五调用内真正做到“元数据选择→正文加载→执行”。

### 4.3 D 的命题级合成协议

D 必须输出一个主线，但不得把未选分支整体判错：

```text
PRIMARY_BRANCH: B | C
PRIMARY_REASON: <完整度、约束覆盖和证据依据>
SUPPORTED_CLAIMS:
- <claim_id> <- <evidence_id>
AUXILIARY_CLAIMS:
- <另一分支中可并入主线的 claim_id>
REFUTED_CLAIMS:
- <claim_id> <- <确定性证据或明确内部矛盾>
UNRESOLVED_CLAIMS:
- <无法判断的 claim_id>
CANDIDATE_D: <当前候选或 UNKNOWN>
OPEN: <仍需 E 完成的义务>
```

宿主执行以下规则：

- `PRIMARY_BRANCH` 只表示继续书写的主线，不等于另一分支为错。
- `REFUTED_CLAIMS` 必须引用存在且状态允许反驳的 `evidence_id`；无引用时降为
  `UNRESOLVED`。
- 工具只能证明其声明 scope 内的计算；宿主还必须核对 checked expression、实际结果和
  expected 都出现在同一命题中，并把显式定义域假设带入 D/E。除非“原题→工具输入”的
  映射也被确定性验证，`EXACT` 不能自动升级为整题答案正确。
- 不拼接 B/C 原始全文；只传完整、有界、带来源的命题。
- E 看到原题、主线、辅助命题、反证、未决义务和工具结果；E 可修正主线，但不能把
  一个被硬证据反驳的命题恢复为已证。
- 数学上未验证不自动返回 UNKNOWN。只有空响应、占位符、协议损坏、冲突终答或明确撤回
  等工程/输出错误继续 fail-closed；这避免重复 v2 把可能正确答案过度转为 UNKNOWN。
- 工具拒绝未定义/非有限结果、缺失符号分母定义域和超出累计资源预算的表达式；E 的
  `FINAL` 只接受一个位于末尾且闭合的标记，重复、占位或截断答案一律为 `UNKNOWN`。

### 4.4 新方法 seam

新方法通过一个小接口进入 `ReasoningAgent.solve()`：

```text
ForkEvidenceSynthesizeFinishRelay(client, clock).solve(problem, problem_type)
    -> RelayResult
```

Skill 与记忆作为构造依赖注入 relay；测试通过同一接口替换它们。不要为只有一个实现的
细节再建立工厂或通用编排框架。

## 5. 阶段 S：独立 Skill 目录、契约与验收

### 5.1 目录

新 Skill 不修改或复用迭代 11/12 的 `reasoning_agent/skills/math_routes.json`：

```text
reasoning_agent/fesf_skills/
  exact-evaluation/
    SKILL.md
    cases.jsonl
```

`SKILL.md` frontmatter 是 `name` 和 `description` 的单一事实源。运行时扫描一级 Skill
目录并读取 frontmatter；只有被选中的正文才进入模型输入。不另建一份会漂移的
`registry.json`。

### 5.2 `name`/`description` 规范

- `name` 使用小写 ASCII 与连字符，表示可执行操作，不使用“专家”“万能”“数学推理”等
  宽泛身份词。
- `description` 必须同时写：正向触发条件、反向边界、预期产物、使用的工具。
- 每个独立适用分支只出现一次，不堆叠同义词骗触发。
- 描述不得含题号、数据集名、题面片段、答案或来源标签。

首个 Skill 固定为：

```yaml
---
name: exact-evaluation
description: >
  Use when a candidate derivation has reduced the problem to a bounded exact
  arithmetic or symbolic expression. Produce one restricted EXACT_EVAL request
  and map its result back to a named claim. Do not use for unbounded search,
  informal existence arguments, geometric interpretation, or when the needed
  expression has not been derived.
---
```

### 5.3 Skill 正文结构

每个 Skill 正文必须按以下顺序包含：

1. Preconditions：适用条件；
2. Inputs：需要从原题/记忆取得的字段；
3. Procedure：有限、有序步骤；
4. Required artifacts：必须生成的命题和工具请求；
5. Verification：工具返回后如何检查 scope 和假设；
6. Stop/Fallback：不适用、工具 UNKNOWN、证据冲突时回到什么状态。

首个 Skill 只允许受限 `EXACT_EVAL` DSL；不允许 Python、import、文件、网络、线程或
子进程。执行器复用已安装的 SymPy 和现有 AST 白名单思想，但这是“中途精确计算反馈”新
机制，不宣称继承旧 SymPy 终答比较的能力结果。

### 5.4 独立 Skill 工程门

`cases.jsonl` 至少包含：

- 12 个应适用案例；
- 12 个不适用案例；
- 合法整数、分数、幂、简单符号表达式；
- 越界指数、未知函数、赋值、导入、文件/网络调用等拒绝案例；
- 工具 `EXACT`、`REFUTED`、`UNKNOWN` 与错误返回；
- Skill 不适用时 B 自由路径和最终接口不受影响。

零模型验收必须 100% 通过：

- Skill 名称唯一、frontmatter 可解析、description 四要素齐全；
- 路径只来自仓库相对目录，正文/案例 hash 可记录；
- 只加载被选择的一份正文，非法 ID 不读取任意路径；
- DSL 白名单与资源上限有效；
- 未定义结果、缺失符号定义域和累计幂膨胀均被拒绝；
- 工具结果可 JSON 序列化；
- evidence 必须绑定同一 claim 的表达式/结果/expected；不满足时不进入 D/E；
- 不存在错误 `SUPPORTED/REFUTED`；不确定和异常均为 `UNKNOWN`；
- D/E 可见 scope、checked expression、expected 与 assumptions；
- 重复、撤回、占位或明显截断的 `FINAL` 均 fail-closed；
- Skill 输出不能直接写入 `final_response`，必须经过 D/E。

### 5.5 Skill 真实可用性门

在 24 题资格集上预先人工标注 12 个 `exact-evaluation` 适用、12 个不适用案例；标注只看
结构条件，不看候选臂答案。资格窗观察：

- `skill_choice_parse_rate`；
- 适用题选择率和不适用题 `NONE` 率；
- `applicability_match_rate`；
- `required_artifact_complete_rate`；
- `tool_request_valid_rate`；
- `tool_execution_success_rate`；
- `evidence_consumed_by_d_rate`；
- `evidence_changed_candidate_count`；
- `skill_attributable_correct_to_incorrect`。

资格门固定为：

- 适用题正确选择至少 10/12；
- 不适用题正确选择 `NONE` 至少 11/12；
- 已选择且适用的样本中，完整产物至少 80%；
- 合法工具请求执行成功至少 90%；
- 可用证据中至少 80% 被 D 正确引用；
- 错误 `SUPPORTED/REFUTED` 为 0；
- Skill 引起的 correct→incorrect 为 0。

任一项失败即 `SKILL_QUALIFICATION_NO_GO`，不得启动能力窗。只修复实现 Bug 可以在
180 分钟总预算内重跑未完成资格项；改变 description、正文、DSL 或门槛必须新版本、新
manifest，不在同一窗口临场改口径。

## 6. 阶段 M：独立记忆目录与持久化边界

### 6.1 目录

```text
reasoning_agent/fesf_memory/
  __init__.py
  solve_state.py

docs/experiments/FESF-EXPERIENCE/
  reviewed_experience.jsonl
```

- `reasoning_agent/fesf_memory/solve_state.py`：运行时单题状态和渲染逻辑；
- `docs/experiments/FESF-EXPERIENCE/reviewed_experience.jsonl`：评测后候选经验账本，属于
  开发工件，不随运行时加载。

### 6.2 单题状态

每次 `solve` 新建一个 `SolveMemory`，不得放在模块全局、类变量或共享文件中。最小状态：

```text
goal
answer_type
constraints[]
claims[]: id, content, source, status, evidence_ids, depends_on
candidates[]: branch, answer, supporting_claim_ids
evidence[]: id, source, status, scope, result, assumptions
open_obligations[]
loaded_skills[]: name, content_hash
remaining_calls
remaining_stage_tokens
```

状态更新只接受已闭合的协议条目。半截公式、未闭合多行块、冲突 ID 和模型自述的信任等级
不得升级为可信命题。宿主为每个后续阶段按字符预算渲染相关状态；原题、约束、硬证据和
OPEN 优先，重复叙述后删。

### 6.3 能否在评测时持久化

| 范围 | 技术上能否保存 | FESF v1 是否依赖 | 规则 |
|---|---|---|---|
| 同一个 `solve` 的 A→E | 能；Python 局部对象 | 是 | 宿主必须重新注入下一次 messages |
| 同一进程的下一道题 | 也许，但进程复用/题序未知 | 否 | 每题独立，不读取上一题状态 |
| 官方运行目录文件 | 也许，但可写性、并发和生命周期未知 | 否 | 不写隐藏题动态记忆，不用固定共享文件 |
| 下一次官方评测 | 不能自动延续 | 否 | 只能通过赛后审核并提交的新 Skill 版本进入 |
| 本地评测工件 | 能 | 仅用于离线审计 | 逐题落盘、manifest、报告；不进入当前题 Prompt |

因此答案是：**agent state 可以保存一个 `solve` 内的过程；不能可靠或合规地把正式评测
中的做题过程当作跨题、跨轮在线记忆。** 即使某个容器偶然允许写盘，也不能把偶然持久化
当作提交设计前提。

### 6.4 错题经验沉淀流程

错题本是离线开发流程，不是正式评测中的自训练：

```text
评测 answers/report
  -> 赛后错误审计
  -> 候选经验（docs/experiments/FESF-EXPERIENCE/reviewed_experience.jsonl）
  -> 去除题号、原文、gold、来源标签和单题特判
  -> 写成结构适用条件 + 失败模式 + 程序步骤 + 检查义务
  -> 更新某个 Skill 的新版本和 cases
  -> 独立 Skill 验收
  -> fresh held-out A/B
  -> 通过后才进入下一次评测
```

经验条目最小字段：

```text
experience_id
status: PROPOSED | ACCEPTED | REJECTED
structural_trigger
failure_pattern
countermeasure
required_check
source_scope: local_external | official_aggregate
source_artifact
reviewer
target_skill
```

约束：

- 有 gold 的冻结外部数据可以用于定位数学错误；题目和答案仍留在实验工件，不复制进运行时
  Skill。
- 官方隐藏评测若不提供题目/gold，就不能声称识别了数学错因；只能沉淀可观察的协议、截断、
  超时或输出卫生经验。
- 即使平台展示了隐藏题，也不得把题面原文、答案、idx 或等价指纹写入运行时资源；仅在赛事
  规则明确允许时做人工审核，并只沉淀可迁移结构规则。
- “相同题型和领域”必须由题面中的数学结构条件识别，例如“有限状态上界明确且要求精确计数”，
  不能只凭 `Combinatorics` 标签或题目来源触发。
- 离线经验账本不进入提交运行包、不直接参与检索或 Prompt，避免把已否决的方法卡 RAG
  复活；只有晋升进版本化 `SKILL.md` 的经验才可被运行时加载。

## 7. 计划文件范围

后续实现只应触及以下必要范围：

```text
user_agent.py
reasoning_agent/fork_evidence_synthesize_finish.py
reasoning_agent/fesf_skills/exact-evaluation/SKILL.md
reasoning_agent/fesf_skills/exact-evaluation/cases.jsonl
reasoning_agent/fesf_memory/__init__.py
reasoning_agent/fesf_memory/solve_state.py
scripts/run_external_hard_sets_smoke.py
tests/test_fesf.py
tests/test_fesf_skills.py
docs/experiments/FESF-EXPERIENCE/reviewed_experience.jsonl
docs/experiments/FESF-V1-*/
docs/excluded_approaches.md
```

优先复用 `RelayResult`、现有 client 调用包装、答案抽取、时间门、runner 的配对/恢复能力和
现有 SymPy 依赖。不要复制整个 `user_agent.py`、建立第二套 client、增加数据库或修改
`requirements.txt`。

## 8. 零模型工程验收

至少覆盖：

1. 回退基线与 `de74934` 请求/终答行为一致；
2. L0 一调用和非 L0 五调用上限；
3. A 可选择 NONE；非法/缺失选择使 C 回到普通互补求解，且不污染 B；
4. D 选择主线但保留另一支合法辅助命题；
5. 无硬证据时 `REFUTED` 自动降为 `UNRESOLVED`；
6. 工具 `EXACT/REFUTED/UNKNOWN` 的 scope、假设和引用完整；
7. 半截、冲突或不存在的 claim/evidence ID 不进入 E；
8. E 看见原题、主线、辅助命题、反证和 OPEN，不看未选分支原始全文；
9. 数学未验证不被自动改成 UNKNOWN，协议损坏继续 fail-closed；
10. Skill 路径穿越、非法 ID、重复 name、frontmatter 错误和 DSL 越权被拒绝；
11. 三个并发 `solve` 的 `SolveMemory` 完全隔离；
12. 第二次 `solve` 不读取第一次的状态；
13. trace 只记录有界状态、ID、工具状态和失败类别，不保存 API key、完整 Prompt 或长输出；
14. runner 臂显式钉死全部旧候选开关，避免 `SUBMISSION_CONFIG` 漂移；
15. answers 逐条 flush，外部终止后 resume 不重复已完成三元组；
16. 返回值 JSON 可序列化且 `final_response` 为非空字符串。

建议命令使用项目固定解释器：

```powershell
D:\Anaconda\envs\CA-py310\python.exe -m unittest tests.test_fesf tests.test_fesf_skills tests.test_fork_select_deepen_finish tests.test_external_hard_sets_runner_report
D:\Anaconda\envs\CA-py310\python.exe -m py_compile user_agent.py reasoning_agent\fork_evidence_synthesize_finish.py reasoning_agent\fesf_memory\solve_state.py scripts\run_external_hard_sets_smoke.py
git diff --check
```

若全量发现测试含仓库既有失败，报告必须把“本次新增失败”和“既有失败”分开，不得修改无关
测试来制造全绿。

## 9. 后续可选真实模型实验：总计不超过 3 小时

### 9.1 总预算

若后续获得明确启动指示，总计时从首次真实模型请求前开始，到最终报告/处置写回结束，硬
上限 180 分钟。零模型测试和代码实现应在计时开始前完成。当前轮次按用户指示暂缓，
不启动 Q/W1/W2，也不消耗模型调用。共享端点的所有窗口串行运行。

| 阶段 | 最大时间 | 任务量 | 是否条件启动 |
|---|---:|---:|---|
| Q：Skill 资格窗 | 20 分钟 | 24 题单臂，8/外部集 | 必须先运行 |
| W1：fresh 配对能力窗 | 65 分钟 | 48 题 × 2 臂，16/外部集 | Q 通过才运行 |
| W2：独立确认窗 | 65 分钟 | 新 48 题 × 2 臂，16/外部集 | W1 通过才运行 |
| buffer：resume、长尾、报告与处置 | 30 分钟 | 不新增样本 | 始终保留 |

任何阶段提前完成，剩余时间进入 buffer，不自动扩大样本。任一阶段触发 NO-GO 后不启动下一
阶段，也不把剩余时间用于换 Prompt、改 Skill 或追加新候选。

### 9.2 数据冻结

- Q、W1、W2 在任何模型输出前一次性冻结，三者题组互不重叠。
- 排除 FSDF 迭代 1–12 已反复使用的 15 题和本次开发 Skill 案例。
- 每窗从 OlymMATH-hard、AIME、HLE 各取固定数量；同一问题的语言变体按
  `problem_group_id` 去重。
- manifest 记录题目文件 hash、选择清单、gold hash、grader 版本、Skill 文件 hash、代码
  commit、客户端 thinking 参数和臂定义。
- gold 只进入本地 scorer，不进入任何模型消息、Skill、记忆或工具请求。

### 9.3 实验臂

W1/W2 固定双臂：

- `fsdf_v1_tkoff`：FSDF v1 请求/答案行为，全部 v2/迭代候选关闭，client thinking off；
- `fesf_v1_tkoff_exact_eval`：FESF v1 + 已通过 Q 的 `exact-evaluation`，其余模型、
  temperature、token、调用、timeout 和 thinking 设置相同。

采用同题配对、逐题轮换首臂、workers=3、request timeout=300s、answer-level resume。不得
同时运行其它共享端点实验。

### 9.4 VOID 门

先判 VOID，再看正确率：

- 任一 manifest/hash/arm/thinking 配置不一致；
- Q/W1/W2 选择集重叠，或与旧 15 题重叠；
- 任一臂顶层/请求错误率 >10%；
- hard-stop 时完整配对率 <90%；
- gold、题号特判或上一题状态进入模型请求；
- 实际模型调用超过 5，或 token 上限漂移；
- 运行中修改 Skill、Prompt、grader、臂定义或门槛。

VOID 窗不产生能力结论；只允许在总 180 分钟内用同 manifest resume 尚未完成项，不换样本。

### 9.5 能力、反转与成本门

W1 启动 W2 的条件：

- candidate correct − baseline correct ≥ 3；
- `skill_attributable_correct_to_incorrect = 0`；
- 错误 `SUPPORTED/REFUTED = 0`；
- candidate 平均调用 ≤5，P95 时长不超过 baseline 1.25×；
- 输出接口和 trace 卫生全部通过。

W2 完成后的本地 `EXPLORATORY_GO` 条件：

- W1、W2 各自净 correct 均 >0；
- 两窗合计净 correct ≥5；
- 两窗均无可归因于 Skill 错配、错误证据或记忆污染的 correct→incorrect；
- 报告原始 paired b/c、双侧精确符号检验、各来源/领域结果、incorrect/invalid、调用、token、
  平均/P95 时长，不只报告净 correct。

未满足则 `NO_GO`。满足也只表示进入后续正式门候选；两个 48 题窗和 3 小时限制不自动满足
`external70_v1 + confirm30_v2` 正式晋升纪律，不自动改默认或发布。

## 10. 工件与处置

计划工件：

```text
docs/experiments/FESF-V1-CODE-ACCEPTANCE-001/
docs/experiments/FESF-SKILL-EXACT-EVAL-QUAL-001/
docs/experiments/FESF-V1-LOCAL-AB-001/
docs/experiments/FESF-V1-LOCAL-AB-002/
docs/experiments/FESF-EXPERIENCE/
```

每个真实模型窗口至少包含 `run_manifest.json`、`answers.jsonl`、`report.json`、`result.md`。
代码验收包含 `spec.md`/测试清单/结果和源码 hash。每个阶段结束后先把结果写回
`docs/excluded_approaches.md`，再决定是否启动下一阶段。

## 11. 实施顺序

1. 冻结本规格并确认回退/发布授权边界；完成标准：Spec 不再有未决口径。
2. 在干净发布快照做前向回退并验收；完成标准：FSDF v1 行为对齐。
3. 实现 FESF relay 与单题记忆；完成标准：零模型架构测试通过。
4. 实现 `exact-evaluation` Skill 和 DSL；完成标准：独立 Skill 工程门通过。
5. 扩展 runner 臂、冻结 Q/W1/W2 manifests；完成标准：题组/hash/配置不可变且互斥。
6. （后续可选）启动 180 分钟实验计时，严格按 Q→W1→W2 条件推进；本轮暂缓。
7. 归档所有工件并更新排除表；完成标准：结果可由逐题记录重算。
8. 向用户报告基线回退、Skill、记忆、能力和成本五类结论；不把其中一类替代另一类。
9. 只有在新的明确授权后，才执行 GitCode 推送、默认切换或正式评测提交。

## 12. 主要风险与对应止损

| 风险 | 止损 |
|---|---|
| Skill 描述宽泛导致误触发 | 12 正/12 负资格集；不适用题 NONE ≥11/12 |
| Skill 合规但数学错误 | 产物/工具/证据/最终 correct 分层验收 |
| B/C 融合形成矛盾汤 | D 只合成带 ID 命题；主线唯一，辅助/反证/未决分栏 |
| 错误工具请求被当真 | scope/assumptions 明示；错误证据为 0 的硬门 |
| 记忆把模型自述升级为事实 | trust 状态只由宿主和工具更新 |
| 跨题状态污染 | 每次 solve 新建状态；并发与连续 solve 隔离测试 |
| 错题本变成样例特判/RAG | runtime 不加载账本；经验必须去特化并晋升为 Skill 新版本 |
| 本地 thinking off 无法迁移官方 | 发布前独立验证官方公开契约；未验证则保持部署阻塞 |
| 进程再次被外部终止 | answers 逐题 flush、同 manifest resume、30 分钟 buffer |
| 三小时内追逐好结果 | 阶段硬停、NO-GO 后停止、禁止临场改方法或追加样本 |
