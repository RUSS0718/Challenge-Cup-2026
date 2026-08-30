# PRE0-EXT-001 预注册：外部题集与 native judge 烟测

- 窗口 ID：`PRE0-EXT-001`
- 类型：模型校准窗，**不产生任何能力结论、不设正确率门**
- 预注册冻结时间：2026-08-30（下载、选题与运行之前）
- 上位规范：`math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6、§5.2/§5.3
- 依据：`local_evaluation_benchmark_audit_2026-08-29.md` §3.4（OlymMATH 逐项核对）
- 启动前置：PRE0-STATIC/JUDGE/PARITY 通过；PRE0-AA-001 整窗关闭（含任何复跑）
  之后**串行**开跑（共享端点纪律）。

## 1. 假设与动机

外部题层（OlymMATH 等）+ native 判分是 P1 正式门的前提。本窗用 12 题 OlymMATH
烟测端到端链路：hf-mirror 拉取 → 首发修订固定 → 静态验收 → baseline_hetero
单臂求解 → Math-Verify native 判分 → contract/native 双口径落盘。回答的不是
"答对几题"，而是"链路是否可复现、判分是否 fail-closed、成本是否可测"。

## 2. 数据与许可

- 上游：HF `RUC-AIBOX/OlymMATH`，**固定首发 revision `5f83d12`
  （5f83d12e63ee3267f35044461a6cebad58ec3be1）**，四文件
  `data/OlymMATH-{EN,ZH}-{EASY,HARD}.jsonl`（论文口径 4×100 行）；当前 Hub
  多出的第五 subset **不得混入**。
- 许可：HF 卡声明 MIT（审计已核）；下载日期、原始文件 SHA-256、行数（应各 100）、
  许可声明记入 manifest。**仓库不提交原始题面**：原始文件只存本地缓存
  `tmp/pre0_ext_001/cache/`，仓库只保留选题 ID、hash 与本 manifest。
- 题目不进入 few-shot、训练、RAG 或方法 Prompt。

## 3. 静态验收门（先于任何求解）

1. 四文件行数各 =100；`unique_id` 非空且文件内唯一；`problem/answer/subject`
   非空。
2. 全 400 行（200 唯一问题 × 平行语言）按 `problem` 文本存在性抽验非空；
   平行语言对按同题不同语言登记 `problem_group_id`。
3. native evaluator（Math-Verify，与 gold 方向固定）对全部 gold 自判 100%
   （解析+等价全通过）——不通过的金标行从"合格条目"池剔除并记录清单。
4. 记录答案类型分布（实数/区间/其他）。

## 4. 选题算法（冻结 seed）

- 池：gold 可自判的条目（按唯一问题计，双语均可入选）。
- 单元：唯一数学问题（同题双语只算一个；每组任取其一语言入选，不重复同一数学
  问题）。
- 目标：**12 个唯一问题**：easy 6、hard 6；四领域各 3；ZH/EN 各 6。
- 分配：领域配额 Algebra 3、Geometry 3、Number Theory 3、Combinatorics 3，
  其中每领域 easy/hard 分配为 {2,1} 或 {1,2} 交替（Algebra 2/1、Geometry 1/2、
  Number Theory 2/1、Combinatorics 1/2），语言 ZH/EN 在 12 题间交替指派并保证
  每语言恰 6。
- 随机源：`random.Random(20260830)`；池内候选按 `unique_id` 排序后取样。
- 产物：选题清单（unique_id、subject、语言、答案类型）+ 数据文件 SHA-256 落
  manifest；`aa24` 式全量记录本窗选题对应的 `problem_group_id`。

## 5. 运行协议

- 臂：单一 `baseline_hetero`（与 AA 窗同配置语义）；12 solves 上限；理论模型
  调用上限 12×5=**60**；workers=3；timeout=120s；temperature=0.6；熔断同前。
- 运行面：实验 runner（同 AA 窗的修复后工作树）；判分：contract（本仓 judge）
  与 native（Math-Verify）**双口径并行**记录，另记 invalid、答案类型、调用数、
  时延。
- 复跑规则：健康失败（模型错误、熔断）允许恰好一次整窗复跑；再失败 →
  `ARCHIVED_VOID`。

## 6. 通过门

1. manifest 完整（上游 revision、文件 hash、下载日期、许可、选题算法、seed）；
2. 12/12 完成且 model error=0（健康失败按复跑规则处理）；
3. native judge 对 12/12 给出 verdict、无 parser crash、无 fail-open；
4. contract/native 差集、invalid、答案类型、调用与时延成功落盘；
5. **本窗不设正确率门，不据错题调整 Prompt/方法**（错题只入诊断）。

## 7. 产物与边界

- 产物：`selection_manifest.json`、`run_manifest.json`、`pre0_ext_result.md`、
  逐题 contract/native 双口径结果记录（含 native verdict 与差集）。
- 边界：本窗分数**不得**与 OlymMATH 公开榜横比（官方 32k 预算 vs 本仓 4096）；
  12 题样本不得用于任何能力主张；native 判分方向与版本一经本窗使用即冻结，
  后续 core120_v2/confirm30_v2 必须沿用同一版本。
