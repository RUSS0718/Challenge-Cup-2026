# V4-HARD20-DUAL-001 实验预注册（草案）

状态：`PREREGISTERED / IN_PROGRESS`（用户 2026-09-03 指示按本 spec 执行；题集 `official_like_hard20_v1` SHA-256 `3cf90e65ef9239a70d9675b3807a01692d19aef27fa7cd1e5ffcefdc70ef12dd`，seed `20260903`）

目的：在不重复运行官方基线的前提下，用最接近官方隐藏评测的难题小窗，筛选两个互斥的升级方法。该实验是候选筛选，不产生相对官方基线的正式能力结论，也不授权修改 `SUBMISSION_CONFIG`、提交或申请 official canary。

## 1. 实验问题与边界

问题：在相同端点、相同题目和相同官方并发约束下，哪一个升级方法更能把长推理题收束为正确、可判的最终答案？

本窗不运行 `baseline_hetero`。历史官方基线 `hetero_k5 @ 25f99b5` 只作为外部参考，不参与本窗调用、配对统计或晋升判定。因此本窗最多得到：

- 两个候选之间的描述性/配对筛选结果；
- 协议、健康、截断、成本和输出卫生证据；
- 不能得到“超过基线”的因果结论。

## 2. 题集：official-like hard20

### 2.1 固定组成

建立一次性冻结的 `official_like_hard20_v1`：

- OlymMATH hard：12 题；ZH/EN 各 6 题，四个数学领域各 3 题；
- AIME 2024：8 题，整数 exact 判分；
- 总计 20 题，题面、答案和选择结果写入构建 manifest；运行时只读取题面，不读取 gold。

选择规则必须在模型调用前冻结：固定上游 revision、下载日期、许可、原始 ID、`problem_group_id`、选择 seed 和 SHA-256。不得按历史模型对错、题号或答案调 Prompt；不得与 AIME 2025 fidelity 样本重复。

### 2.2 题集静态门

以下任一项失败，整窗 `VOID_DATASET`，不启动模型：

- 20/20 题面和 gold 完整，native evaluator 100% 可判；
- 规范化题面零重复，图形/表格/单位/百分号/集合逐题抽审；
- 语言、领域、答案类型和来源计数与 manifest 一致；
- 题集 hash 与 preregistration 一致。

## 3. 两个候选方法

两臂均使用同一端点、同一题集、同一调度器；只比较候选方法，不设置基线臂。

### A：`condition_checked_selection_v1`（KCV）

- 最多 3 个异构解题候选；
- 若候选已有确定性等价共识，直接选择共识；
- 无共识时追加 1 次结构化关键条件检查，只能在已有候选中选择或返回 `UNKNOWN`；
- KCV 不能创造新答案、改写答案、从正文 salvage 或放宽 parser；`UNKNOWN` 直接 fail-closed；
- 每题最多 4 次模型调用，单次 `max_tokens=4096`。

假设：部分错误来自定义域、边界、符号或题目约束遗漏；受限检查可减少错误选择，同时不把 verifier 的猜测当成新解。

### B：`plan_solve_compact_v1`（PS-C）

- 第 1 次调用生成不超过 600 token 的结构化计划：变量、约束、目标和预计答案类型；
- 第 2 次调用携带该计划完成求解，要求答案优先、证明/计算最小充分，并在末尾给出单一明确答案；
- 不要求 BTCS `FINAL` 帧，不从截断正文 salvage；无法得到明确答案则返回 `UNKNOWN`；
- 每题最多 2 次模型调用，总 token 预算 600 + 3072。

假设：先固定解题骨架可降低长题中无界铺陈造成的截断；若计划失败，第二阶段不得把计划当作答案。

RAG、工具、MCP、沙箱只保留工程接口和 trace 字段，默认关闭，不进入本窗方法变量。

## 4. 调度与预算

- 轮数：1 轮筛选；每题两臂交错，臂顺序由冻结 seed 生成；
- 官方并发模拟：`workers=3`；不得使用 8 workers 作为正式结论；
- 单题硬超时：20 分钟；实验总硬停止：180 分钟；
- 不自动重试 model error；客户端重试由 runner 统一记录且计入预算；
- 预计上限：20 × (4 + 2) = 120 次模型调用，实际以 trace 为准；
- 超过总时限、题数不完整或任一方法健康错误率 >10%，整窗 `VOID`。

若 90 分钟时两臂均已完成且健康门通过，可再运行第 2 轮；第 2 轮必须使用新 seed、同一冻结题集，并在启动前写入 manifest。第 2 轮不是必需项，不能事后为了显著性追加。

## 5. 判分与记录

每题同时计算：

1. `benchmark_native_score`：OlymMATH 使用固定 Math-Verify，AIME 使用整数 exact；
2. `contract_score`：冻结的严格提交抽取器；
3. `invalid`、`model_error`、`finish_reason`、调用数、completion token、耗时和阶段 trace。

`extracted_answer` 只作诊断。模型正文、尾段、计划内容不得直接作为答案；不得因本窗结果修改判分器。

## 6. 门与处置

### 6.1 结构/健康门

- 完整率 100%，无重复键、无缺题，manifest/hash 一致；
- 两臂 model error ≤10%，否则整窗 `VOID`；
- JSON、非空 `final_response`、接口和 trace 卫生全部通过。

### 6.2 候选筛选门（只用于两候选排序）

定义 `delta_i = correct_A_i - correct_B_i`，报告胜负题数、双侧 exact sign test、Wilson CI，并分别报告 OlymMATH、AIME 和语言/领域子集。

优先候选须同时满足：

- native correct 不低于另一候选，且至少净胜 2 题；
- `invalid + model_error` 不多于另一候选 2 题；
- 平均调用数不超过另一候选的 1.10 倍，P95 耗时不超过预注册上限；
- 任一主要子集不出现明显净负（描述性门，不宣称显著性）。

若两者未满足上述条件，处置为 `EXPLORATORY_NO_WINNER / NO_PROMOTION`。

### 6.3 因果边界

本窗无官方基线臂，故无论结果如何都不得标记 `FORMAL_PASSED` 或 `ENGINEERING_CANDIDATE`，不得声称超过 `hetero_k5`，不得直接提交获胜方法。若产生清晰 winner，下一步必须以该 winner 与 `hetero_k5` 在同一官方-like hard 窗做成对复验。

## 7. 必备工件与停止条件

必须生成 `run_manifest.json`、逐题 compact answers、阶段 trace、report、result 和 SHA-256。任何 partial、题集漂移、重复键、模型错误超门或 180 分钟到时，立即停止并标记 `VOID`；不得挑选好看题目或累计样本直到通过。

