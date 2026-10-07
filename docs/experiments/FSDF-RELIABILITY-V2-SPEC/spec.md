# FSDF：修复交接与终答可信度，建立可归因的能力改进入口

状态：规格草稿；待确认测试边界后发布至 GitHub，并标记 ready-for-agent。

## Problem Statement

参赛者需要在保留 FSDF v1 已出现的积极官方成绩信号的同时，降低推导交接失败和非答案输出，并能判断后续改动是否提高数学正确率。

2026-09-05 用户提供的官方评测日志记录提交 de74934bf58c20a825af43e251da4c2eb9033b8c：112 题中 correct 14、incorrect 61、invalid 37，accuracy 12.5%；560 次请求、563 次尝试、471 次截断，agent stage 约 4 小时 29 分，runner error 为 0。相对历史 C0 的 9/112，多出 5 个正确答案；跨窗口差异不能证明某个阶段的因果收益。

当前实现及本地外部难题工件暴露出以下问题：

- 字段抽取会丢失多行推导；空字段可能跨行读取下一字段；重复字段优先取首次值，无法清晰表达候选更新。
- D 的交接内容在进入 E 前进一步裁剪，缺乏字段级完整性与裁剪诊断。
- 答案选择可能在 E 明确输出 UNKNOWN 后重新采用先前候选，也可能接受占位符、字段回显或冲突终答中的第一项。
- 本地 150 题中有 16 题发生 D 协议失败，最终均为 invalid。该关联不能解释为修复后必然新增 16 个正确答案。
- 本地 native 与 contract 均有 31 个正确答案，但完整判定有 68 题不一致；保存的 trace 丢失了阶段、失败类别和终答来源。记录还含 5 个 failed 阶段，不能凭顶层 0 model_error 宣称内部调用全部健康。

主要矛盾同时包含推理能力与工程可靠性。把 invalid 改成 incorrect、降低 UNKNOWN 或通过单元测试，均不构成提分证据。

## Solution

保留 Analyze → B/C Fork → D Select/Deepen → E Finish 主体，用可独立验证的增量解决问题：

1. P0：修复评测诊断与报告口径，保留既有阶段信息，使后续实验能够归因。该增量不得改变模型请求和最终答案。
2. P1：建立字段边界明确、保留多行推导的交接处理；把已完成推导、未解步骤与检查结果优先传给 E。
3. P2a：明确终答确认、候选回退、UNKNOWN 与冲突处理规则，避免把未确认内容输出为答案。
4. P2b：单独验证 E 收尾提示词改动，让 E 完成原题所问的最后一步并输出唯一确认答案，避免强制提前填写猜测候选。
5. P3：仅登记后续候选 fsdf_branch_probe_v1。B/C 在原预算内各提供一个实际中间关系、适用条件和未解障碍，供 D 选择；本规格不实施或运行这一能力实验。

本规格的完成交付为 P0–P2 的隔离候选、零模型代码验收及实验预注册文档。实现期间不得改变 SUBMISSION_CONFIG 的求解行为；真实模型实验、正式门、提交与发布分别受项目既有授权约束。ready-for-agent 仅表示上述工程范围可执行。

## User Stories

1. As a participant, I want the official score tied to its evaluated commit, so that I can distinguish a deployed method from a local candidate.
2. As a participant, I want current FSDF submission behavior preserved during development, so that an unvalidated change cannot affect official evaluation.
3. As a solver maintainer, I want multiline derived statements retained, so that Finish can continue the selected reasoning chain.
4. As a solver maintainer, I want empty fields to remain empty, so that another field cannot become a candidate answer accidentally.
5. As a solver maintainer, I want repeated answer fields handled explicitly, so that stale or contradictory values cannot silently win.
6. As a solver maintainer, I want unfinished steps separated from established results, so that Finish knows what still requires reasoning.
7. As a solver maintainer, I want unselected branch content excluded from the handoff, so that Finish follows the selected branch.
8. As a solver maintainer, I want context limits to preserve complete high-priority statements, so that a truncated fragment is not treated as valid evidence.
9. As a participant, I want explicit abstention respected, so that a withdrawn candidate cannot reappear as a confirmed answer.
10. As a participant, I want placeholders and echoed protocol fields rejected, so that final_response contains an answer or UNKNOWN.
11. As a participant, I want conflicting final answers to fail closed, so that output order cannot arbitrarily determine the answer.
12. As a participant, I want numerical and non-numerical answers handled within their own boundaries, so that a scalar filter does not reject legitimate proofs or structured answers.
13. As a participant, I want Finish to answer the original requested quantity, so that an intermediate result does not substitute for the requested answer.
14. As an evaluator, I want stage failures retained even when solve returns successfully, so that caught exceptions do not disappear from health statistics.
15. As an evaluator, I want native and contract verdicts compared in full, so that equal correct counts do not imply identical output hygiene.
16. As an evaluator, I want compact diagnostic records without secrets or full prompts, so that failures are explainable without unsafe trace content.
17. As an experiment owner, I want each behavioral change evaluated separately, so that any observed gain or regression is attributable.
18. As an experiment owner, I want frozen problem groups and grading rules, so that language variants and changed extraction rules cannot inflate evidence.
19. As a participant, I want call, token and runtime limits preserved, so that local improvements remain compatible with official resource constraints.
20. As a future researcher, I want the branch-progress hypothesis documented separately, so that exploratory work cannot silently become a submission change.

## Implementation Decisions

- 复用现有 FSDF relay、答案检查能力、脚本化 client、时钟注入与本地评测运行器，不新建通用编排框架、协议服务或依赖层。
- 保持公开构造与 solve 契约不变：通过公开 client.chat 契约访问模型，结果为可 JSON 序列化字典，final_response 为非空字符串；metadata 不参与答案推导。
- 保留非 L0 最多五次逻辑调用及 2048/2048/2048/8192/4096 token 上限序列；L0 行为不变。不追加修复调用，不扩大重试，不读取 client 私有 usage 或控制字段。
- P0、P1、P2a、P2b 必须能够独立选择和复现；沿用最小实验配置入口，避免新增任意可组合的配置矩阵。当前 SUBMISSION_CONFIG 保持 FSDF v1 行为。
- P0 为诊断增量。保留 stage、status、error_category、fallback_source、selected_branch、model_calls 与预算信息；新增交接字段缺失、裁剪发生及候选/终答是否存在等有界摘要。只保留公开来源的 token/finish_reason 信息；不可获得时明确标记 unavailable，不以字符数推断截断。
- 将顶层 runner 失败、阶段 client 异常、非字符串/空响应、协议失败与 UNKNOWN 分开统计。历史工件已删除的字段不得事后补猜。
- 交接字段按已知标记边界解析，字段间空白不得跨过下一标记；允许字段正文包含多行。自由文本和未选分支回显不得被重新纳入 D 的可信交接包。
- 区分交接正文的多行解析与终答标记的单行读取。单行答案标记为空时不得吸收后续协议字段。
- P1 不通过任意“最后值优先”解决重复候选。相同重复值可去重；不一致值标记冲突。仅有明确完成标记的结果可以与临时候选区分；不能因为字段出现得更晚就推断完成。
- 在既有上下文总上限内，优先传递已完成推导、当前未解步骤、检查结果与明确完成结果，压缩重复的 A 摘要和方法叙述。裁剪以完整字段或完整推导项为单位；被截断项不得作为完整证据传递，缺失必须对 E 可见。
- 保持选路有效性检查。无法确认 D 选择了可用分支时继续按已有降级边界处理；不放宽为任意猜测选择，不把另一分支结果重新贴标签。
- P2a 中，有效、无冲突的 E 终答优先；E 明确给出 UNKNOWN 时最终返回 UNKNOWN，不再自动回退候选。重复冲突终答不取第一项或最后一项，返回 UNKNOWN。
- E 缺失终答与 E 明确撤回答案是不同状态。缺失情况下，仅可采用无冲突、通过适用答案检查且带明确完成标记的结果；未经确认的 CANDIDATE、任意 boxed 中间量和孤立数学行不自动成为终答。D 协议失败时，其原文不因包含答案标记而绕过来源有效性检查。
- 复用已有占位符、冲突和答案类型检查，但不得把仅适用于短标量的限制应用到证明、集合、有序结构或长表达式。不依赖样例题号、gold、来源标签或固定题面特判。
- P2b 只改变 E 的收尾职责表达，不同时改变答案解析或预算。E 应补完选定链路的局部未解步骤，回答原题实际目标并输出唯一确认终答；无法确认则 UNKNOWN。不新选分支，不把模型自述“已检查”当成确定性验证。
- P1/P2 各自通过工程验收后仍是候选。多项行为变更不默认合并为一个能力实验臂；组合必须符合方案排除表的独立过门与单变量增量要求。
- 遵循既有 ADR：仅可复核工件进入证据链；独立题组、轮次与配对数分别记录，不把历史结果追加成新的显著性证据。

## Testing Decisions

拟采用两个现有边界，待用户确认：

1. 主边界为 ReasoningAgent.solve()。注入现有 ScriptedClient，以公开的请求消息和返回字典验证交接与终答行为；复用已有 FakeClock 验证调用边界。必要的解析边界案例可使用现有 relay 测试，不新暴露生产 API。
2. 报告边界为本地评测运行器产生的逐题记录与汇总报告。以固定的合成结果和阶段事件验证字段保留、统计与序列化，不访问真实模型。

好测试应证明用户可观察结果或跨阶段交接契约，不断言私有数据结构、正则表达式写法或无关 prompt 全文。测试不得复制隐藏题或依赖已有错题的固定措辞。

工程验收：

- 多行 DERIVED 的后续关键步骤出现在发送给 E 的消息中；空候选后跟另一字段时，不把该字段作为答案。
- 重复一致标记可去重；重复冲突标记不能静默选值。候选更新、缺完成标记和显式完成结果各有覆盖。
- 不完整交接保持不完整标记；长字段裁剪后不存在被当成完整关系使用的半截数学内容；未选分支仍不可见。
- 显式 FINAL: UNKNOWN 不恢复旧候选；冲突 FINAL、字段回显、泛化占位符及方法描述不能进入有效终答。
- 合法整数、分数、表达式、集合/有序结构及非数值答案不被错误合并或统一套用标量规则；保留现有适用类型的正向回归用例。
- E 缺终答时，仅符合规格的完成结果能够回退；返回 UNKNOWN 不计为工程崩溃，也不计为能力成功。
- 新候选仍满足最多五次逻辑调用、既有 token 上限、L0 单调用、solve 间状态隔离与时间边界检查；不得宣称本地时钟检查能中止正在运行的公开 client 调用。
- P0 开关前后对相同 ScriptedClient 序列产生相同模型请求和 final_response；增加诊断不改变行为。
- 即使 solve 顶层返回成功，注入的阶段异常/协议失败仍体现在报告中；不可获得的信息保持 unavailable。
- 对固定 native/contract 判定矩阵，报告分别列出 correct/incorrect/invalid、完整不一致数与正确数一致性；不得把两者称为真实官方 judger 的等价实现。
- 先运行现有 FSDF 接口与回归测试，再运行本规格新增用例。通过记录只证明工程行为，交付时列明未运行真实模型实验。

实验预注册交付要求（运行不在本规格授权范围内）：

- 每个候选记录独立 method ID、假设、唯一变化、协议快照、数据/gold/题组身份及评分器版本；提交快照须另有授权，不以未提交工作区作为有效实验窗。
- 直接对照为本次评测的 FSDF v1；C0 仅作历史锚，不继承跨窗口收益。方案排除表若仍含旧的 C0-only 构造要求，须在正式预注册时明确解决口径冲突，不能默默绕过。
- 已查看的 150 题只用于诊断与回归；能力确认集须事先冻结并与开发题组隔离，同一题的中英版本属于同组。小样本探索不能替代正式门。
- 同窗口按题交错运行双臂、轮换首臂；固定 workers=3，禁止运行中改并发；共享端点不同实验窗串行。
- 运行前明确健康 VOID 阈值、样本量/功效依据、双轮规则、配对检验及聚类口径、正确数/卫生/成本门和停止规则。不得填入未经本次讨论确认的提分目标，指标未冻结则协议不可执行。
- 先判 VOID，再判能力、卫生与成本；记录平均/P95 调用、token、时长及六小时整轮风险。只降低 invalid 或 UNKNOWN 不算过能力门。
- 每窗结束先归档报告、manifest 与处置，再进入下一方法。任何双轮 A/B 过门也不自动修改 SUBMISSION_CONFIG、提交 main 或发布作品。

## Out of Scope

- 本轮实际运行真实模型、官方评测、健康窗口或双轮能力 A/B。
- 自动提交、推送、修改提交仓库 main、切换 SUBMISSION_CONFIG 或提交赛事作品。
- 一次启用交接、终答、分支提示词和预算的组合改动。
- 实施 fsdf_branch_probe_v1、增加分支搜索、动态预算路由或扩大 token/重试上限。
- 原样重启 REJECTED/ARCHIVED 方法，包括方法卡 RAG、机械加长 token、旧 P3/refine 与工具救援协议；因果 MCP/Demo 不进入数学正式求解路径。
- 根据题号、题面、来源、标准答案或隐藏评测信息特化求解。
- 修改已有金标、放宽判分器来美化正确率，或把本地 native/contract 结果等同官方判分。
- 无关工作区文件、领域词汇表与历史 ADR 的顺手重构。

## Further Notes

- 当前测试边界确认是发布本规格前唯一待确认事项；无需重新访谈需求。GitHub 目标为 RUSS0718/Challenge-Cup-2026，发布标签为 ready-for-agent。
- 现有 Issue #14 属于旧弱点修复包，已受方案排除表限制；本规格另建 issue，不把旧包恢复为可执行队列。
- 当前领域文档的“FSDF 仅完成零模型验收”是历史状态。本次日志提供了实际官方结果，但不追认此前本地正式门通过；本规格不覆盖或修改用户现有文档改动。
- fsdf_branch_probe_v1 后续假设：用可检查的中间进展替代仅列方法的分支包，提高 D 的选路质量；保持 B/C 各 2048 token、同一 client 和五调用上限。它需要独立预注册，不因本规格发布而自动实施。
- 原始证据：用户附件 eval_log_3f0ff48ae6dd47b69b39831d7bd1e45a.log；其中官方汇总仅支持聚合结论，不支持逐题失败归因。发布正文不包含隐藏题、标准答案或私有附件路径。
- 可复核源码与本地工件：[FSDF v1 评测版本](https://github.com/RUSS0718/Challenge-Cup-2026/blob/de74934bf58c20a825af43e251da4c2eb9033b8c/reasoning_agent/fork_select_deepen_finish.py)、[外部难题逐题记录](https://github.com/RUSS0718/Challenge-Cup-2026/blob/9f51e12ca4135f1d0850943fe6b3a46eb9874be9/docs/experiments/EXTERNAL-HARD-SETS-SMOKE-001/answers.jsonl)、[本地运行器](https://github.com/RUSS0718/Challenge-Cup-2026/blob/9f51e12ca4135f1d0850943fe6b3a46eb9874be9/scripts/run_external_hard_sets_smoke.py)。固定提交链接是证据定位，不替代正式门的 manifest。
