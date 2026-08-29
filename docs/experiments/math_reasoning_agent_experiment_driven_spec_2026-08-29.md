# 数学推理 Agent 实验驱动推进总规范（2026-08-29）

状态：**SPEC_READY / NO_MODEL_RUN / NO_DEFAULT_CHANGE**。

本规范把能力方法、评测题集、统计协议、发布门、runtime、RAG、工具、MCP 与沙箱纳入
同一条实验链。目标是提高挑战杯官方隐藏集得分；基础设施本身不构成能力主张。

## 1. 权威来源与适用边界

执行时按以下优先级处理冲突：

1. 根目录 `AGENTS.md` 的赛事接口、资源与实验纪律；
2. `docs/excluded_approaches.md` 的机制处置与禁止复跑项；
3. 本规范的阶段、证据等级与统一门；
4. 单次实验运行前冻结的 preregistration；
5. report、manifest、逐题 answers 与官方日志中的数字事实。

进入不同分支前必须读取对应参考：

- 新方法、复跑或融合：[`excluded_approaches.md`](../excluded_approaches.md) 与
  [`math_agent_capability_methods_2026-08-27.md`](../research/math_agent_capability_methods_2026-08-27.md)；
- 判分器、外部题集或污染口径：
  [`math_agent_evaluation_final_report_2026-08-29.md`](../research/math_agent_evaluation_final_report_2026-08-29.md) 与
  [`local_evaluation_benchmark_audit_2026-08-29.md`](../research/local_evaluation_benchmark_audit_2026-08-29.md)；
- 发布：[`branches_map.md`](../branches_map.md)、官方评测记录和最近一次 release report。

本规范不授权 commit、push、修改 `SUBMISSION_CONFIG`、切换三指针或在作品页面提交。
这些动作仍需用户分别授权。

## 2. 已确认的起始状态

- 当前官方 tip 为 `46c08dd`，运行时代码父提交为 `9311d8c`；工作/证据分支为
  `b2f01ec`。commit 与指针属于时间敏感事实，执行前重验。
- 官方在役行为为 hetero adaptive k5 + refine + ARH，effective 调用上限 8；它是
  `DEPLOYED_UNVALIDATED_CANARY`。
- `9311d8c` 的 reverify skipped/inconclusive 会保留 revision，与文档声称的
  fail-closed 不一致；工作分支实现才会回滚。
- 当前 `gsa_4call` 会两票早停、只向聚合器传答案字符串，并相对 `baseline_hetero`
  同时关闭 hetero/adaptive voting。已有 `b=3,c=0,p=0.125` 只记为
  `EXPLORATORY_POSITIVE`，不是 GSA 正式通过。
- `public112` 全部走 calculation；`complex48` 与 `medium60` 完全重合 24 题，合计
  仅 84 道唯一题；`medium60` 有 8 题标签与运行时分类不一致。
- 当前多轮分析只按 `idx` 配对，会静默覆盖跨轮/跨数据集记录；formal gate 仍硬编码
  `baseline86`；runner 的连续错误熔断不等于预注册的“任一臂 error rate >10% VOID”。
- 本地能力判分使用 Agent 自己的 `extracted_answer`，不能观测 ARH 对 `final_response`
  的外部抽取效果。

以上任一事实未收敛前，不启动新的能力方法窗。

## 3. 术语与证据等级

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `STRUCTURAL_ONLY` | 无模型结构、接口、静态数据或判分器验证 | 不作能力结论 |
| `EXPLORATORY` | 健康单窗信号 | 可淘汰；不可晋升或融合 |
| `FORMAL_PASSED` | 完成固定能力门、确认门和全部卫生/成本门 | 可申请 official canary |
| `DEPLOYED_UNVALIDATED_CANARY` | 用户授权发布但官方结果未确认 | 保留回滚锚，不称提升 |
| `OFFICIAL_CONFIRMED` | 同一配置两次健康官方结果满足预注册门 | 可作为新的运营参照 |
| `VOID` | 健康、完整性或协议门失败 | 本窗不出能力结论 |
| `ARCHIVED` / `REJECTED` | 按排除表定义处置 | 不追加同协议窗口 |

“方法层突破”只用于满足以下全部条件的候选：

- `FORMAL_PASSED`；
- 固定能力门绝对正确率提升至少 5 个百分点；
- 至少三个真实题型/学科组不净负；
- 收益不是仅由 invalid→incorrect、宽松判分器或重复题加权产生。

## 4. 统一实验契约

### 4.1 每窗必备产物

每个模型窗必须产生：

1. `preregistration.md`：假设、单变量、臂、题集、轮数、门、VOID、停止条件；
2. `run_manifest.json`：
   - `run_id`、method ID、开始/结束时间；
   - commit、dirty state、Python/依赖版本、model/endpoint identity；
   - runner、`user_agent.py`、judge、resolved config 与 Prompt hash；
   - dataset revision、SHA-256、expected count、选择 seed；
   - workers、timeout、retry、总墙钟上限和完整 CLI；
3. report：逐臂 correct/incorrect/invalid/error、judge coverage、调用/token/时延平均与 P95；
4. compact answers：不保存完整 Prompt/模型原文，只保存判分与诊断所需字段；
5. result：逐窗与聚类后的 `b/c/p`、Wilson CI、处置；
6. 完成后补 report/answers SHA-256，并先更新排除表再开始下一个方法。

### 4.2 逐题记录与配对键

唯一配对键固定为：

```text
(dataset_sha256, round, item_id, variant)
```

同一键重复、任一臂缺题、`completed_n != expected_n`、题集 hash 不符或 partial report
均 fail-closed，禁止进入统计。

平行翻译、GSM-Plus 扰动、重复年份变体另带 `problem_group_id`。跨轮与相关变体按
`problem_group_id` 聚类，不能把 item-round 当独立样本。

### 4.3 判分双口径

- `contract_score`：从最终 `final_response` 重新执行冻结的严格外部抽取，再用本仓保守
  等价判断；回答“提交契约下是否稳定可判”。
- `benchmark_native_score`：使用固定版本的原生/通行 evaluator；MATH/OlymMATH/HMMT
  使用固定 Math-Verify，AIME 用整数 exact，选择题用选项 exact。
- Agent 自带 `extracted_answer` 只用于内部诊断，不得作为唯一正式判分输入。
- 两口径不一致时记录差集；宽松口径不得覆盖严格口径。
- proof/explanation 没有校准过的自动 judge 时只作诊断，不主张正文质量提升。

### 4.4 健康、能力、卫生与成本门

判定顺序固定为：

1. **完整性门**：hash、manifest、题数、配对全部完整；
2. **健康门**：任一臂 `model_error_count / expected_n > 10%` 即整窗 VOID；
3. **能力门**：候选 `b>c`；正式池聚类双侧 exact sign test `p<0.05`；
4. **数据集门**：每个固定数据集不净负；
5. **卫生门**：候选 `invalid+error` 不高于对照，judge coverage 不降低；
6. **成本门**：mean calls ≤对照×1.10，P95 不超预注册上限，预计官方整轮≤5.5h；
7. **接口门**：断网干净环境 import、构造、三并发 solve、JSON 和非空
   `final_response` 全部通过。

资源熔断只标记 `aborted_resource_guard`，不能代替正式 VOID。每个候选最多一次因端点
健康失败的预注册复跑；再次失败即 `ARCHIVED_VOID`。

### 4.5 重复轮次统计

每轮单独报告 same-item McNemar。正式合并时，以题目为聚类单位：

```text
delta_i = 候选在各轮的正确次数 - 对照在各轮的正确次数
b = delta_i > 0 的题目数
c = delta_i < 0 的题目数
```

对 `b/c` 做双侧 exact sign test；`delta_i=0` 不计分歧。item-round 池化只作描述，不作
正式显著性证据。

## 5. 评测题集架构

### 5.1 保留的自建层

| 层 | 内容 | 用途 | 禁止主张 |
| --- | --- | --- | --- |
| endpoint smoke | `dev3` | import/client/最小 solve/端点健康 | 能力优劣 |
| engineering regression | `public112` | 中文短计算、抽取、格式、预算 | 证明、解释、长题或英文泛化 |
| legacy development | `complex48` | 路由、终结论、历史 A/B | 复杂能力或证明质量 |
| public transfer | `medium60` | 额外探索回归 | 与 complex48 独立池化 |

分析两个 legacy 集时按规范化题面 hash 去重为 84 道唯一题；24 道共享题只计一次。
`medium60` 的 8 个运行时分类失配必须在 manifest 中列出，修正标签前不得按存储标签做
宏平均。

### 5.2 新增外部层

外部原题默认保存在本地评测缓存；许可或再分发权未确认时，仓库只保存构建脚本、选题 ID、
revision、hash 与 manifest，不提交原始题面。

1. **`core120_v2`：固定能力门**
   - MATH-500 50：level 1–5 各 10，覆盖 7 学科；过滤离开 Asymptote/图片不完整题；
   - OlymMATH 40 个唯一问题：easy/hard 各 20、四领域各 10、ZH/EN 各 20，语言间
     不重复同一数学问题；固定论文首发 revision；
   - AIME 2024 全 30：整数 exact 锚；许可与题面完整性先过门。
2. **`confirm30_v2`**：AIME 2025 全 30，独立年份确认，逐年份不净负。
3. **`robust180_v2`**：GSM-Plus 20 个 seed ×（原题 + 8 类扰动）。统计单位为 20 个
   seed；七类数值与 critical-thinking 分开。
4. **`fresh63_v1`**：MathArena AIME 2026 全 30 + HMMT Feb 2026 全 33。只跑
   `FORMAL_PASSED` finalist 一次；揭盲后封存，不参与 Prompt 调整。
5. **可选 shadow**：CMATH 60 仅作中文数值/干扰卫生；LiveMathBench 仅在许可和规则
   可判子集审计完成后使用；OlymMATH 12 个中英平行 pair 只做语言一致性。

### 5.3 外部数据静态门

每个数据集必须满足：

- 固定上游 revision、下载日期、原始/选择后 SHA-256、许可及附加条款；
- 原始 ID、`problem_group_id`、语言、答案类型、选择算法和 seed 可复现；
- 全池规范化题面零重复；平行翻译和扰动按组登记；
- 图形依赖、题面截断、多 gold、单位、百分号、集合、区间和矩阵逐类抽审；
- native evaluator 对全部 gold 自判 100%；每类答案有等价、错误近邻和不可解析反例；
- 题目不进入 few-shot、训练、RAG 或方法 Prompt。

## 6. Pre-P0：评测可信度校准实验

Pre-P0 只允许评测器校准和同配置噪声测量。禁止 GSA、KCV、RAG、工具或 runtime
候选进入模型窗。

### PRE0-STATIC-001：配对、VOID 与数据完整性自测

类型：`STRUCTURAL_ONLY`，零模型调用。

输入：合成的 2 数据集 × 2 rounds × 2 arms × 3 items 工件，以及 duplicate、missing、
partial、error-rate 9%/11% 反例。

必须验证：

- 配对键包含 dataset hash、round、item、variant；
- duplicate/missing/partial 直接失败；
- 跨轮结果不覆盖；
- 9% 健康、11% VOID；熔断与 VOID 分字段记录；
- item-cluster `b/c/p` 与手算一致；
- complex/medium 的 24 道重合被检测并拒绝独立池化；
- 所有本地集记录实际 classifier 分布与标签失配。

完成条件：全部正反例通过，产出 `pre0_static_result.md`；任一失败则 Pre-P0 停止。

### PRE0-JUDGE-001：双判分器格式校准

类型：`STRUCTURAL_ONLY`，零模型调用。

输入：12 类答案 × 10 个固定案例，共 120 例：整数、分数/小数、根式、符号表达式、
无序集合、区间、不等式、元组/向量、矩阵、选择项、单位/百分比、截断/占位符。每类包含
等价、明确不等价和不可解析案例。

比较：contract extractor + conservative judge、hendrycks-style extractor、固定
Math-Verify native judge。

通过门：

- gold self-score 120/120；
- 明确错误样本假阳性 0；
- 不可解析样本无异常外泄且 fail-closed；
- ARH 双形态在位置抽取和 last-boxed 抽取下得到同一 canonical；
- 记录各 judge coverage 与差集，不修改阈值追求一致。

### PRE0-AA-001：同配置 A/A 噪声与顺序偏差实验

类型：模型校准，不产生能力结论。

对照臂：`aa_left` 与 `aa_right`，均解析为官方健康锚 `baseline_hetero` 的逐字段相同配置。

题集：从去重 legacy84 按运行时六题型分层；每类按规范化题面 SHA-256 排序取前 4，固定
24 题。两轮 same-item interleaved；第二轮使用不同冻结 schedule seed 和反向首臂轮转。

预算上限：24 items × 2 arms × 2 rounds = 96 solves；每 solve 最多 5 次模型调用，理论
模型调用上限 480。workers=3，共享端点实验串行。

通过门：

- 两轮各自完整、任一臂 error rate≤10%；
- 每轮两臂 correct 差绝对值≤2，`invalid+error` 差绝对值≤2；
- 每轮与 item-cluster exact test 均 `p≥0.05`；
- mean calls、tokens、P95 latency 比值均在 `[0.90,1.10]`；
- 无一臂持续占优、无题型与先运行臂的系统性关联。

健康 VOID 可按预注册复跑一次；健康但 A/A 仍显著偏离则评测协议 `BLOCKED`，不得进入 P0。

### PRE0-EXT-001：外部题集与 native judge 烟测

类型：模型校准，不产生能力结论。

题集：OlymMATH 首发 revision 的 12 个唯一问题；easy/hard 各 6、四领域各 3、ZH/EN
各 6，语言间不重复同一问题。按固定 seed 从合格条目抽取。

臂：单一 `baseline_hetero`；最多 12 solves、理论 60 次模型调用。

通过门：

- manifest、题面完整性、许可记录和 native gold self-score 全过；
- 12/12 完成，model error=0；健康失败可复跑一次；
- native judge 12/12 给出 verdict，无 parser crash；
- contract/native 差集、invalid、答案类型和耗时成功落盘；
- 此窗不设置正确率门，不据错题调整 Prompt。

### PRE0-PARITY-001：实验面与发布面行为签名

类型：`STRUCTURAL_ONLY`，零模型调用。

用 FakeClient 覆盖 L0、hetero 早共识、k5 跑满、model error、fallback、verify all-clear、
revise、reverify pass/fail/skipped/inconclusive、ARH 和非数值输出。记录有序 client transcript、
调用数、temperature、max_tokens、final response 与 trace 摘要签名。

通过门：实验候选与 release candidate 除预注册的 `SUBMISSION_CONFIG` 单变量外签名完全一致；
reverify 未决语义必须先冻结，不能在发布时顺带改变。

### Pre-P0 总退出门

只有以下全部完成才进入 P0：

- PRE0-STATIC、JUDGE、AA、EXT、PARITY 全部通过；
- 自动 manifest 和现行 formal gate 已能消费这些工件；
- 当前指针、官方记录、排除表和候选状态已对齐；
- 用户收到 Pre-P0 汇总并授权继续模型能力实验。

Pre-P0 理论模型调用上限为 540；实际早共识可低于该值。任一结构门失败时停止消耗模型。

## 7. P0：当前官方栈与语义收敛

### 7.1 官方日志判读

核对实际 tip、行为父提交、input hash 和五数。input hash 与历史一致时：

- `correct≥12、invalid≤17、runner_error=0、耗时≤5.5h`：保留整栈为未验证 canary；
- 仅 `invalid>17` 且其余健康：ARH 未命中目标，只撤 ARH，回到 `95d5700`；
- `correct<12`、runner error>0 或耗时>5.5h：撤 refine+ARH，回到官方健康锚
  `25f99b5`；
- invalid≤13 只称“强栈级输出卫生信号”，不能归因给 ARH 单组件。

input hash 改变时禁止历史因果比较；健康则暂留 canary，异常则回滚，不发布下一候选。

### 7.2 refine 未决语义

统计可用工件中 `revise=ok` 且 `reverify=skipped/inconclusive/budget_exhausted` 的触发数：

- 为 0：把真正 fail-closed 视为当前样本上行为不活跃的契约修正，补行为测试但不称提分；
- 大于 0：另立 `refine_unknown_rollback_v1` 单变量正式实验，不能与 GSA/runtime 同改。

### P0 完成条件

- 唯一 `operational_baseline_id`、profile manifest 与回滚锚已冻结；
- fail-closed 语义、排除表、README/指针地图和官方记录一致；
- 没有未处置的在役 canary；
- P1 使用的基线配置可由 manifest 重建。

## 8. P1：完整外部评测层与基线锚

按第 5 节构建 `core120_v2`、`confirm30_v2`、`robust180_v2`、`fresh63_v1`。许可未
澄清的数据仅保存在本地缓存，不提交原题。

运行 P0 冻结的 operational baseline：

- `core120_v2` 两轮，记录 run-to-run 方差、contract/native 差集和成本；
- `confirm30_v2` 一轮，只建立年份锚；
- `robust180_v2` 暂不全跑，仅对 2 个 seed 做结构烟测；
- `fresh63_v1` 保持未揭盲。

P1 完成条件：所有静态门通过，baseline 工件完整，双轮 item-cluster 统计可复现，预计官方
成本有锚；此后新的能力候选才可获得 `FORMAL_PASSED`。

## 9. P2：GSA 机制重证与融合

### 9.1 独立机制三臂

- `O`：`hetero_k5 + ARH状态`，refine 关闭；
- `M`：`hetero_k4_sc + ARH状态`，四次生成后确定性选择；
- `G`：`hetero_k3_gsa + ARH状态`，前三次 reasoner 顺序与 M 相同，第四次聚合。

三臂的 ARH 状态由 P0 决定且必须一致。GSA 不早退；聚合输入使用每份最多前 6000 字符
的候选解答；聚合失败回退前三候选确定性选择。refine、CoD、RAG、工具全部关闭。

先跑固定 12 题 fidelity probe：3+1 transcript 正确、聚合可抽取≥11/12、context/model
error=0。通过后依次运行 legacy84 探索窗、`core120_v2` 两轮正式门和
`confirm30_v2` 确认。

正式机制门：`G vs M` item-cluster `b>c,p<0.05`；整包门：`G vs O` 各数据集不净负；
mean/P95 calls≤4、聚合解析率≥98%、context overflow=0、成本/卫生过统一门。

### 9.2 与 refine 融合

GSA 独立 `FORMAL_PASSED` 后，才比较最强单方法栈与“用 GSA 替换 k5、保留同一
refine/ARH/fail-closed”的融合栈；effective 上限 7。完整重跑正式门与确认门。融合失败
只归档组合，不反向否定独立组件。

## 10. P3：方法级突破队列

一次只执行一个方法；完成报告、manifest 和处置后才进入下一个。

| 顺序 | 候选 | matched control | 硬边界 |
| --- | --- | --- | --- |
| 1 | Key-Condition Verification | 三候选普通复核 vs 关键条件反推 | ≤5 calls，schema≥95%，wrong→right>right→wrong |
| 2 | Step-Back | 题意摘要→求解 vs 原理抽象→求解 | 同为两调用，原则长度受限 |
| 3 | Least-to-Most | 普通计划→求解 vs ≤3子问题→一次求解 | 禁止按子问题循环调用，解析≥95% |
| 4 | Self-Discover | 固定四阶段 vs 动态四阶段 | ≤4 calls，结构 schema≥95% |
| 5 | PS+ | 当前 Prompt vs 计划/缺步/计算检查 | token、截断或延迟增加>10%即归档 |

每项执行 fidelity probe → legacy84 探索 → core120×2 正式 → confirm30 确认 → 适用时
robust180。第一个正式通过者优先申请官方槽，停止无目的扫榜。

## 11. P4：来源定理 RAG

旧 `method_rag` 保持 `REJECTED`。只允许新假设 `source_theorem_rag_v1`：显式命名
定理/定义的问题可能因缺少准确前提失败；检索带来源的定理事实可能改善终答案。

顺序与门：

1. 预注册错误池规则；eligible 少于 12 题即停止；
2. baseline vs 人工锁定、不含答案的 oracle context；`b≤c` 即停止；
3. 语料只含事实性定理/定义、条件、别名、来源和许可，不含例题/答案；
4. 至少 50 个独立正负查询：Recall@2≥85%、Precision@2≥90%、负查询空返回≥90%、
   Top-2≤1500 字符、P95≤20ms；
5. 模型正式门：调用数不变、各池不净负、合并 `p<0.05`、P95 延迟≤1.2×。

不得把冻结评测题或其答案放入 RAG，亦不得用 LangGraph 包装复活旧方法卡机制。

## 12. P5：工具、沙箱与 MCP

### 12.1 直接工具优先

PoT/TIR 和模型生成约束程序有效率已有 0/36，保持归档。新工具先用进程内直接 adapter
做 shadow：决定性假阳性为 0、wrong→right>right→wrong、失败时答案与无工具基线一致，
并完成正式门。未过能力门前不建设传输或沙箱。

### 12.2 沙箱触发门

默认 `NO-GO_PENDING_CAPABILITY`。只有已过门工具确需不可信 DSL 时，才试短生命周期
子进程：1s 硬杀、2KB 输出、无凭证/用户路径/网络/文件写入；异常只返回 `UNKNOWN`。
500 正常 + 200 攻击样本、三并发各100次必须零假证据、零孤儿进程、零串状态。官方式
环境无法可靠限资源时停止，绝不开放任意 Python。

### 12.3 MCP 触发门

MCP 仅是 transport。至少一个直接工具 `FORMAL_PASSED` 且出现第二个真实调用者/adapter
后，才做本地 stdio MCP；不使用 HTTP，不进入正式 runtime 依赖。直接调用与 MCP 在
500 输入上结果100%一致、冷启动≤1s、P95额外≤250ms、server异常回到无工具基线，否则
保留直接 adapter。

## 13. P6：runtime 与 LangGraph

默认保留当前 imperative runtime。至少两个已过门动态分支需要共享预算、超时、trace 和
fallback 时，先做零依赖 stdlib FSM sidecar；若只是增加包装立即停止。

FSM 与原实现必须在 L0、hetero早共识、k5跑满、model error、fallback、refine各状态、
ARH、非数值输出和同实例三并发上满足：final response、extracted answer、有序client transcript、
调用数、temperature、max_tokens 100%一致；100次重复零串状态；P95额外开销≤5ms。

只有 FSM 证明图状态有真实 leverage 后才做 LangGraph sidecar；不启用 checkpointer、stream、
memory、interrupt、框架 retry 或外部 tracing。再加断网 Python 3.11 安装、`pip check`、冷
import增量≤250ms。runtime 迁移必须是独立兼容性变更，不能与能力方法同提交；验证后删除
双栈。

## 14. 官方发布与停止纪律

- 同一时刻最多一个未判 official canary；读完上一日志后才能申请下一槽。
- 发布前运行全量 unittest、目标 profile 行为测试、三并发、断网干净安装、import、最小
  solve、JSON、trace卫生、manifest与实验hash一致性。
- official canary 只增加一个已正式过门变量，保留明确回滚锚并标注
  `DEPLOYED_UNVALIDATED_CANARY`。
- 官方结果必须核对实际 tip、input hash、correct/incorrect/invalid、runner error、截断、
  attempts、token与总耗时；跨 input hash 只作健康观察。
- VOID、正式失败或官方回退后按预注册处置；不追加同协议窗口追显著。
- 本地通过只产生官方候选，不自动修改默认路径；官方单次正向结果也不自动升级为方法突破。

## 15. 本规范的完成标准

本规范被视为可执行，仅当：

- Pre-P0 每项都有单独 preregistration、实现任务和验收测试；
- 外部数据许可/缓存策略由用户确认；
- 当前排除表与在役状态完成事实对齐；
- 用户明确授权启动 Pre-P0 模型窗。

在此之前，本文件只定义执行顺序和门槛，不代表任何实验已经运行或任何候选已经晋升。
