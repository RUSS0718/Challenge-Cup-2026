# FSDF-V2-DIAG-SMOKE-001 诊断窗口结果

方法：双臂同窗交错诊断（`v1` = 未改动 SUBMISSION_CONFIG（FSDF v1 锚点，P0 诊断关闭）；
`v2` = 同一基线 + FSDF-RELIABILITY-V2 四个候选全开（P0+P1+P2a+P2b 合并探索臂））。

结论：`DIAGNOSTIC_ONLY / ZERO_TOPLEVEL_ERROR / NO_CAPABILITY_CONCLUSION / NO_PROMOTION`

- 运行参数：60 题（3 个冻结外部难题池 × 20，种子 20260905，round-robin 交错分派各 30 题），
  workers=3，request timeout 300s，hard-stop 160 min；实际 7671.3s（≈128 min）全部完成，无任务崩溃。
- 题库身份：`sample_data/external_hard_sets` 冻结池（SHA256 见 run_manifest.json）；这是 spec 定义
  "已查看、仅用于诊断与回归"的题库。**两臂题目为同一冻结采样的不相交两半（各 30 题），是分布级对比，
  不是逐题配对；n=30/臂，无任何统计功效。**
- manifest：git_head `b95bbf1`（双臂运行器），arm 开关快照与逐题清单见 run_manifest.json。

## 按臂结果（本地 native 判定）

| 臂 | n | correct | incorrect | invalid(UNKNOWN) | mean_calls | mean_dur | p95_dur | contract_correct | native↔contract 不一致 |
| --- | - | - | - | - | - | - | - | - | - |
| v1 | 30 | 7 (23%) | 18 (60%) | 5 (17%) | 5.0 | 385s | 449s | 7 | 11/30 |
| v2 | 30 | 4 (13%) | 2 (7%) | 24 (80%) | 5.0 | 374s | 480s | 3 | 1/30 |

## 主要诊断观察

1. **v1 的错误答案主要来自未确认候选回退**：v1 臂 30 题中 16 题的终答来源是
   `deep_candidate`（D 的未确认 CANDIDATE_D），其中 12 incorrect、仅 3 correct——
   未确认候选充当终答基本等价于"错误的兜底猜答"。这正是 spec Problem Statement
   与 P2a 针对的失效模式。
2. **P2a fail-closed 达到设计意图**：v2 臂 incorrect 18→2（分布级对比），2 个 incorrect
   全部来自 `finish_final`（E 的已确认终答，真实推理错误，而非抽取垃圾）；24 题返回
   UNKNOWN（23 来源 `unknown`，1 来源 `finish_unknown` 显式弃答）。v2 的全部 4 个
   correct 均来自显式确认来源（3 `finish_final` + 1 `deep_final`）。
3. **correct 7→4 的下降符合预期交换**：v1 的 7 个 correct 中 3 个来自未确认候选回退；
   v2 不再接受该来源。两臂题目集不同（各 30 题），此为分布级观察，不能逐题归因，
   更不能区分 P1/P2a/P2b 各自贡献（合并探索臂）。
4. **输出卫生显著改善**：native↔contract 完整判定不一致 11/30 → 1/30；v1 有 16 题
   final_response 被严格抽取契约判 invalid 而 native 仍给 incorrect（prose/垃圾终答），
   v2 的 final_response 只有"确认值或 UNKNOWN"两种形态，两套判定几乎完全一致。
5. **成本与预算不变**：两臂 mean_calls 均 5.0、时长 374s vs 385s（P95 480s vs 449s），
   未放宽任何调用/token 上限；整轮远低于 6 小时风险线。
6. **P0 可归因性生效**：v2 臂记录到 3 次 `stage_protocol_failures`、4 次阶段 client
   异常（solve 顶层仍 0 error）、12/30 finalize 事件含交接字段缺失（P1 严格解析视图）、
   1 次交接裁剪。注意：v1 臂 P0 诊断关闭，其 `handoff_missing=0` 是"无记录"而非
   "无缺失"，两臂该指标不可直接对比。协议失败率（2/30、3/30）与历史 150 题 16 次
   （≈10.7%）量级一致。
7. **跨窗口对照仅作参考**：EXTERNAL-HARD-SETS-SMOKE-001（FSDF v1，同池 150 题，不同
   窗口）native 31 correct / 93 incorrect / 26 invalid（21%/62%/17%），与本窗口 v1 臂
   （23%/60%/17%）构成相近；按仓库纪律，跨窗口数字不构成任何增益/回退证据。

## 边界与未做事项

- 本窗口是诊断窗口：预注册门阈值仍未冻结（见
  [`../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`](../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md)），
  本结果不判定任何能力门，不构成对 `SUBMISSION_CONFIG`、提交仓库 main 或作品的任何修改依据。
- v2 为合并探索臂（P0+P1+P2a+P2b 同时开启），无法单变量归因；任何正式双轮 A/B 必须
  按预注册草案以独立臂执行并先冻结门槛。
- 本地 native/contract 均为本地近似判定，非官方 judger 等价实现（judge_note 随报告输出）。
- 正确数下降与 UNKNOWN 上升均不单独构成门判定；"只降低 invalid 或 UNKNOWN 不算过能力门"。
