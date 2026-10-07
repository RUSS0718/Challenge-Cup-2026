# V5-HARD20-TYPED-CAPSULE-001 实验预注册（草案）

状态：`DRAFT / USER_GO_REQUIRED`

## 1. 目的与因果边界

本实验针对 `V4-HARD20-DUAL-001` 暴露的输出协议故障：候选生成成功率低、KCV 选择器 schema 失败、PS-C 计划误拒绝，以及请求超时。目标是提高“正确答案进入可判输出”的概率，而不是继续增加选择器或自由 self-refine。

本窗不运行 `hetero_k5` 基线，因此不能产生相对官方基线的因果结论；历史 `hetero_k5 @ 25f99b5` 仅作离线参考。即使本窗通过，也只能进入下一次与基线同窗复验，不能直接修改 `SUBMISSION_CONFIG` 或申请 official canary。

## 2. P0：零模型调用的评测契约修复

在任何新模型窗前完成并单测以下修复：

1. **typed scalar parser**：对 AIME、数值型 OlymMATH 只接受独立答案标记行（`最终答案:` / `Final answer:` / `ANSWER:`）后的纯数学 token；禁止把自然语言句子或任意尾部整数当答案；不做正文 salvage。
2. **AIME judge hygiene**：删除“从预测文本提取最后一个整数”的判分方式；没有合法 typed answer 时记 `invalid`，不能把自然语言中的中间整数记为 `incorrect`。
3. **plan validator**：计划中的中间数值、`ANSWER_TYPE` 或模型回显不再导致整题提前终止；计划永远不直接作为答案。仅当计划缺少必需字段或为空时才跳过第二阶段，并记录原因。
4. 为以上三类观察到的失败字符串添加回归测试；原 `V4` 报告数字不回写，只另存 `REPARSE_DIAGNOSTIC`。

P0 通过条件：单测全通过，旧实验工件可重放，任何 parser 变化都不会从截断正文或尾行猜答案。

## 3. 新方法：`typed_answer_capsule_v1`

### 3.1 核心机制

每题最多两次**独立求解**，不使用 KCV、GSA、普通 k2/k3 投票、尾段续推或自由修正：

1. **Primary**：`max_tokens=4096`。提示要求第一行输出
   `ANSWER: <纯数学结果>`，随后可给最多 10 条关键推理；禁止 Thinking Process、计划回显和多个最终答案。
2. **Compact retry**：仅当 Primary 没有合法 typed answer、明确被截断或返回占位符时启动；`max_tokens=2048`，重新读取原题独立计算，第一行立即给答案，不携带 Primary 正文，不从 Primary 尾段恢复。
3. 只接受答案标记行中通过 typed parser 的值；两个阶段都失败则 `UNKNOWN`。不得从正文、计划、`\boxed{}` 片段或自然语言尾部捞答案。
4. 若 Primary 已产生合法答案，不调用 retry；retry 不能覆盖 Primary 的合法答案。

该方法的唯一能力假设是：**把答案位置前置并在失败时使用一次短、独立的重新求解，能够减少长推理截断和协议失配；不会依赖宽松抽取获得表面分数。**

### 3.2 超时与预算

- 单题最多 2 次模型调用；
- Primary 4096 + retry 2048 token；
- 客户端请求 timeout：900 秒；单题 hard deadline：1080 秒；
- 官方并发模拟：3 workers；总实验硬停止：180 分钟；
- 客户端重试若发生必须计入 attempts，不得隐式增加调用上限。

## 4. 题集与调度

使用已冻结的 `official_like_hard20_v1`（SHA-256 `3cf90e65…12dd`）做第一轮；不改题、不挑题、不按历史对错调 Prompt。该题集只用于诊断新机制，不能把 20 题视为正式显著性样本。

- 单轮 20 题，题目顺序和阶段 seed 冻结；
- 记录 OlymMATH/AIME、语言、领域、答案类型分层；
- 如 P0 通过且首轮完成率/健康门通过，才可另行预注册第二轮；不得在结果出来后追加轮次追求显著性。

## 5. 记录与判分

每题记录：`final_response`、typed parser 状态、native verdict、contract verdict、`finish_reason`（若 client 暴露）、retry 触发原因、调用数、token、耗时和 compact trace。

正式判分：

- AIME：integer exact；
- OlymMATH：固定 Math-Verify；
- `contract_score` 和 `benchmark_native_score` 分开报告；
- 模型自带 `extracted_answer` 只作诊断，不作为唯一判分来源。

## 6. 门与停止条件

### 6.1 先行 VOID 门

- 题集 hash、20/20 题面、gold 和 evaluator 静态门通过；
- 20/20 solve 完成，0 duplicate/missing；
- model error ≤10%；
- JSON、非空返回、trace 卫生通过；
- 超过 180 分钟或任一 hard deadline 失控立即停止并记 `VOID`。

### 6.2 探索性能力门

本窗无基线，故只使用绝对和诊断门，不宣称提升：

- typed answer 形成率相对 V4 同题记录提高至少 20 个百分点；
- native correct 至少 4/20（仅作继续实验的筛选线，不是正式晋升线）；
- `invalid + model_error` ≤16/20；
- 平均调用 ≤1.50，P95 耗时 ≤900 秒。

任一候选门失败则 `EXPLORATORY_NO_GO`；通过则 `EXPLORATORY_CONTINUE_TO_BASELINE_MATCHED`，下一步必须与 `hetero_k5` 同窗复验。

## 7. 预期与风险

- P0 parser/评分修复能消除一部分“伪 incorrect/伪 invalid”，但不会凭空提升模型数学能力；
- 900 秒 timeout 可能减少 V4 的 8 次 KCV 超时，但会增加墙钟风险；
- OlymMATH hard 上一轮两臂均为 0/12，若修复后仍接近 0，说明主要瓶颈是底层推理能力，停止继续做协议微调；
- 预估 native correct 达到 4/20 的概率：约 25%–35%；预估直接超过官方基线的置信度：低于 20%。

