# STATEFUL-TAIL-V1-LEGACY84-001 实验预注册

状态：**PREREGISTERED / IN_PROGRESS**
方法 ID：`stateful_tail_completion_v1`
对照基线：`baseline_hetero`（即 `hetero_k5 @ 25f99b5`，官方 Run #5 12/83/17、4h24m 健康锚）
所属阶段：P2 正式能力门第一阶段（Legacy84 双轮成对 A/B）
权威依据：
- `docs/excluded_approaches.md` §六.0e
- `docs/experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6e & §9
- 前置门通过：`STATEFUL-TAIL-V1-FIDELITY-001`（实测 75% 显式形成率，0 error，独立审查 PASS）

## 1. 实验设计与配置

### 1.1 题集与规模
- **题集**：`sample_data/legacy84.jsonl`（`complex48` 与 `medium60` 去重后 84 道唯一题）
  - SHA-256：`80f7cbd178b8415a0cb805f8261693ae5133342f40883954cc9bc17ca7645f8c`
- **轮数**：2 轮（Round 1 & Round 2），每轮 84 题，同题交错（interleaved）
- **规模**：84 items × 2 arms × 2 rounds = **336 次 solve()**
- **调度机制**：
  - 8 workers 并发；
  - Round 1 schedule seed: `4201`；Round 2 schedule seed: `4202`（名义臂顺序反转）；
  - 逐题原子化追加落盘（锁内成对写入，支持断点续测与容错恢复）。

### 1.2 对照臂与候选臂定义

| 配置字段 | 对照臂（`baseline_hetero`） | 候选臂（`stateful_tail_completion_v1`） |
| --- | --- | --- |
| `enable_heterogeneous_reasoners` | `True` | `True` |
| `enable_adaptive_voting` | `True` | `True` |
| `vote_k_max` | 5 | 5 |
| `vote_agree_threshold` | 3 | 3 |
| `max_model_calls` | 5 | 5 |
| `max_tokens` | 4096 | 4096 |
| `enable_numeric_answer_first_prompt` | `True` | `True` |
| `enable_step_verification` | `False` | `False` |
| `enable_step_revision` | `False` | `False` |
| **`enable_stateful_tail_completion`** | **`False`** | **`True`**（唯一单变量） |
| `stateful_tail_max_chars` | — | 8000 |

### 1.3 判分与统计协议
- **判分口径**：`contract_score`（从最终 `final_response` 严格抽取并按保守等价规则判分）；
- **配对统计键**：`(dataset_sha256, round, item_id)`；
- **聚合统计**：
  - 题目聚类配对差值 $\Delta_i = \text{correct}_{\text{candidate}, i} - \text{correct}_{\text{baseline}, i}$；
  - $b = \sum [\Delta_i > 0]$（候选胜题数），$c = \sum [\Delta_i < 0]$（对照胜题数）；
  - 双侧 exact sign test 计算 $p$ 值；
  - 计算各轮单轮 McNemar $p$ 值与 $95\%$ Wilson CI。

## 2. 门控判定标准

判定顺序严格遵循总规范 §4.4：
1. **完整性门**：336 次 solve() 全部完成，无丢题，配对 100% 完整；
2. **健康门**：任一臂 `model_error / 168 <= 10%`（否则整窗 VOID）；
3. **能力门**：
   - 候选臂 $b \ge c$（不净负）；
   - 双轮合计正确数 $\text{correct}_{\text{candidate}} \ge \text{correct}_{\text{baseline}}$；
4. **卫生门**：候选臂 `invalid + error` 不高于对照臂；
5. **成本门**：候选臂 `mean_calls <= baseline * 1.10`。

通过上述全量门控后，方可授予 `LEGACY84_PASSED` 并进入 `core120×2` 最终正式能力门。
