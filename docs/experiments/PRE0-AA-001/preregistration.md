# PRE0-AA-001 预注册：同配置 A/A 噪声与顺序偏差实验

- 窗口 ID：`PRE0-AA-001`
- 类型：模型校准窗，**不产生任何能力结论**
- 预注册冻结时间：2026-08-30（题集构建、代码改动与运行之前）
- 上位规范：`math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6
- 启动前置（规范 §15）：用户已明确授权启动 Pre-P0 模型窗（2026-08-30 会话指令
  "完成P0前的所有pre任务"）；PRE0-STATIC/JUDGE/PARITY 三个结构窗全部通过后
  本窗才开跑。

## 1. 假设与动机

在共享端点 + workers=3 + 真实温度 0.6 的条件下，两个**逐字段相同**的配置在同一
题集、同窗交错运行时，correct/invalid/error/成本指标应落在噪声带内。若 A/A 即
显著偏离，说明现有评测协议（轮次、交错、轮转、熔断）存在顺序或窗口偏差，一切
后续 A/B 结论不可信。

## 2. 臂与单变量

- 对照臂 `aa_left` 与 `aa_right`：均解析为官方健康锚 `baseline_hetero` 的
  **逐字段相同**配置（numeric answer-first prompt + hetero + adaptive
  k5/threshold-3 + 4096 tokens + policy prompt；`max_model_calls=5`，无 refine、
  无 ARH、无 GSA、无 Re2/CoD/salvage）。该配置即官方 Run #5（12/112）在役
  hetero_k5 canary 的实验 runner 复刻。
- 单变量：**无**。两臂配置逐字段相同；任何差异都是噪声或协议缺陷。
- 实现：在集成分支工作树（39fcd12）`scripts/evaluate_protocol_ab.py` 追加
  `aa_left`/`aa_right` 两个 Variant（字段与 `baseline_hetero` 完全一致）与
  `--schedule-seed`（仅打乱作业调度顺序，不改变同题两臂交错与配对）。除此之外
  **零 runtime 改动**；改动以未提交补丁形式存在于工作树并记入 manifest。

## 3. 题集（冻结构建算法）

1. 源池：`sample_data/complex_capability_freeze_48.jsonl` ∪
   `sample_data/medium_capability_freeze_60.jsonl`，按规范化题面
   （NFKC → 去全部空白 → lower）hash 去重 → 必须 **84 道唯一题**
   （否则立即中止，不选题）。
2. 分层：用运行时 `classify_problem_type` 分 6 类（choice/proof/explanation/
   derivation/fill_blank/calculation）。
3. 每类内按 `sha256(规范化题面)` 升序排序取**前 4** → 24 题；任一类不足 4 题
   → 中止（不降级凑数）。
4. 冻结产物 `aa24_dataset.jsonl`（字段：`idx, problem, answer, source_dataset,
   source_idx, runtime_type, norm_sha256`），整体 SHA-256 记入 manifest。

## 4. 运行协议（冻结）

- 轮数：2 轮 same-item interleaved（runner `--interleave-items`）。
  - Round 1：arm 序 `[aa_left, aa_right]`，首臂轮转 `index % 2`，
    schedule seed = **8301**。
  - Round 2：arm 序 `[aa_right, aa_left]`（**反向首臂轮转**），同 offset 规则，
    schedule seed = **8302**。
- 判分：`evaluate_dev.judge_correct`（现有实现，不改）；逐题记录沿用 runner
  answer_rows（compact，无原文）。
- 资源：workers=3；timeout=120s；retry=1；temperature=0.6；熔断 8 连续失败；
  预算上限 24 items × 2 arms × 2 rounds = **96 solves**，理论模型调用上限
  **480**（每 solve ≤5）。共享端点串行：本窗运行期间不启动其他本地模型窗。
  - **Amendment A1（2026-08-30，窗口启动前）**：dev3 冒烟实测端点单调用延迟
    均值 ~70–85s 且存在 >120s 尾部（触发 1 次 model_error/3 题）。单请求
    timeout 120s → **180s**，避免慢窗口把健康门打成假 VOID；两臂同 timeout，
    对 A/A 差异与成本比值无影响。其余资源参数不变。
- 运行代码：集成分支工作树 39fcd12 + 本窗未提交补丁；commit、dirty 文件清单、
  dataset sha、seed、完整 CLI 全部入 `run_manifest.json`。

## 5. 门（判定顺序）

1. **完整性**：两轮各自 24/24×2 臂齐全，dataset hash 一致，无 VOID 熔断标记。
2. **健康门**：任一臂任一轮 `model_error / 24 > 10%`（即 ≥3）→ 整窗 VOID。
3. **A/A 能力噪声门**：每轮两臂 correct 差绝对值 ≤2；每轮两臂
   `invalid+error` 差绝对值 ≤2。
4. **显著性门**：每轮 exact McNemar `p ≥ 0.05`；两轮合并 item-cluster
   （24 题聚类）双侧 exact sign test `p ≥ 0.05`。
5. **成本门**：两臂 mean model_calls、mean total_completion_tokens、
   P95 latency 的比值均在 `[0.90, 1.10]`（按两轮合并计；逐轮数值并列报告）。
6. **顺序偏差门**：无一臂在两轮中 correct 均严格占优（持续占优）；
   首运行臂 × 获胜臂 2×2 表 Fisher exact `p ≥ 0.05`（平局剔除）。

## 6. VOID、复跑与 BLOCKED

- 健康 VOID（门 1/2 或熔断）→ 允许**恰好一次**整窗预注册复跑（新 run_id，
  完整重跑 96 solves， seeds 不变）；再失败 → 本窗 `ARCHIVED_VOID`，Pre-P0
  停止并上报。
- 健康但门 3–6 任一失败 → 评测协议判 `BLOCKED`：**不得进入 P0**，先修协议
  （顺序/轮转/判分卫生）并以新预注册重做 A/A。
- 本窗任何结果都不得表述为能力差异；`p<0.05` 的 A/A 差异是协议缺陷信号，
  不是方法信号。

## 7. 产物

`aa24_dataset.jsonl`、`build_manifest.json`（构建算法与 hash）、
`reports.json`（2 轮 × 2 臂聚合）、`answers.jsonl`（compact 逐题）、
`run_manifest.json`（CLI、commit、dirty 清单、seeds、预算、时间戳、
INTERN_API_KEY 是否存在=布尔，不存 key 本身）、`pre0_aa_result.md`
（六门逐条判定 + Wilson CI 描述区间）。
