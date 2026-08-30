# Experiment Evidence（实验证据目录索引）

> 2026-08-30 归类。**历史工件内容一律不改写**（含冻结 JSON 清单内记录的历史路径——
> 迁移映射见文末）；`git mv` 保留全部历史。

## 执行权威

- 规范：[`math_reasoning_agent_experiment_driven_spec_2026-08-29.md`](math_reasoning_agent_experiment_driven_spec_2026-08-29.md)
  （标题 = 2026-08-30 最终版；含 §6a/§6b/§6c 三项已批准 amendment）
- Pre-P0 总汇总：[`PRE0-SUMMARY-2026-08-30.md`](PRE0-SUMMARY-2026-08-30.md)
- 运营基线 profile：[`operational_baseline_hetero_k5_25f99b5.json`](operational_baseline_hetero_k5_25f99b5.json)
- 回滚准备/执行记录：[`p0_rollback_preparation_2026-08-30.md`](p0_rollback_preparation_2026-08-30.md)

## authority/ —— 官方评测权威记录（唯一事实源）

| 文件 | 内容 |
| --- | --- |
| `官方评测记录.md` | Run #1–#7 五数快照 + 逐 Run 判分/用量/分析 + 裁决 |
| `official_eval_log_run4_b8b78aa_2026-08-27.log` | C0 9/112 原始日志 |
| `official_eval_log_run5_25f99b5_2026-08-28.log` | hetero_k5 12/112 原始日志（健康锚） |
| `official_eval_log_run6_7479d47_2026-08-29.log` | Re2 回滚原始日志 |
| `official_eval_log_run7_46c08dd_2026-08-30.log` | 发4 整栈 9/112 → OFFICIAL_NEGATIVE_STACK |

命名规范：`official_eval_log_run<N>_<commit>_<评测日>.log`（旧 R 编号已弃用）。

## 活动窗口（目录即窗，遵守打包约定）

- `PRE0-STATIC-001/`、`PRE0-JUDGE-001/`、`PRE0-PARITY-001/`：结构窗（零模型调用）
- `PRE0-AA-001/`…`PRE0-AA-004/`：A/A 校准链（003=ORIGINAL_GATE_FAIL/SUPPORTS_AMENDMENT，
  004=§6c 口径最后校准窗，六门全过）
- `PRE0-EXT-001/`（描述性证据）、`PRE0-EXT-002/`（§6a 合规 PASS）
- `P1_BASELINE/`：外部能力层基线（静态层 manifest + runs/ + 预注册）

新实验打包约定：

```text
docs/experiments/<experiment_id>/
  preregistration.md
  run_manifest.json
  result.md
  answers.jsonl
```

## canary-releases/ —— canary 发布与回滚边界（5 份）

hetero_k5 / hetero_refine / hetero_refine_arh(发4) / re2 的发布边界与回滚记录。
发4 整栈官方判定与组件处置见 `authority/官方评测记录.md` Run #7 与排除表。

## screens-2026-08-27-29/ —— 本地筛窗与探针（canary 前置）

| 子目录 | 内容 |
| --- | --- |
| `g_screen/` | G 成本筛（首筛 FAIL + 复测 VOID） |
| `hetero_k5/` | hetero_k5 健康探针 ×3 + 筛窗预注册 + runtime amendment |
| `p1_salvage/` | P1 salvage 窗（ARCHIVED_VOID） |
| `candidate_screens/` | CoD / Re2(两窗) / ARH / GSA 单文件 complex48 筛结果 |
| `refine_confirm/` | refine W2/W2b/fresh 确认窗 + timeout240 预注册 |
| `battle_nights/` | 作战夜结果、健康 dev、交接与夜链日志 |

## legacy-2026-08-20-24/ —— 协议时代工件（41 份）

protocol_ab 六件、adaptive_vote 三窗、arch_bakeoff、challenger 战役、
baseline_4k5、stable_baseline、stress_set、conditional_retry、k5_model_error、
length_pressure/length_telemetry——实验驱动总规范生效前的探索时代。

## 迁移映射（2026-08-30，路径引用以此为准）

- `experiments/官方评测记录.md` → `experiments/authority/官方评测记录.md`
- `experiments/official_eval_log_run<N>…` → `experiments/authority/…`
- `experiments/p1_salvage_*` → `experiments/screens-2026-08-27-29/p1_salvage/…`
- `experiments/g_screen_*` → `experiments/screens-2026-08-27-29/g_screen/…`
- `experiments/hetero_k5_*`（health/screen/direct_release）→ `screens-2026-08-27-29/hetero_k5/…` 与 `canary-releases/…`
- `experiments/hetero_refine*_release_2026-08-29.md`、`re2_*` → `experiments/canary-releases/…`
- `experiments/{cod,re2,arh,gsa}_screen_complex48_*` → `screens-2026-08-27-29/candidate_screens/…`
- `experiments/refine_*`、`timeout240_*` → `screens-2026-08-27-29/refine_confirm/…`
- `experiments/{battle_night*,experiment_handoff,night_chain_log}*` → `screens-2026-08-27-29/battle_nights/…`
- `experiments/{protocol_ab,adaptive_vote,arch_bakeoff,challenger,baseline_4k5,stable_baseline,stress_set,conditional_retry,k5_model_error,length_*}…` → `legacy-2026-08-20-24/…`

冻结 JSON（如 `g_screen_manifest_*.json`）内记录的旧路径是**运行时历史事实**，
不回填；引用一律按本映射换算。Official release notes and raw logs remain
evidence artifacts; do not rewrite them during cleanup.
