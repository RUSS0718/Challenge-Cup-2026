# 每日官方评测归档

本目录专门保存每日官方评测的原始日志、事实记录和 agent 分析。

## 目录约定

```text
docs/official_evaluations/
├── INDEX.md                    # 跨日期总表
├── README.md                   # 归档规范
└── YYYY-MM-DD/
    ├── record.md               # 只写官方日志可直接确认的事实
    ├── agent_analysis.md       # 方法、配置、GitCode ref 和证据等级分析
    └── raw/                    # 原始日志，只复制不编辑
```

规则：

- `raw/` 文件保持原样；文件名中的 commit 是日志中记录的 commit，不代表推断。
- `record.md` 不混入本地实验分数、预测分数或因果结论。
- `agent_analysis.md` 必须分开写 `EXACT`、`TRACEABLE`、`INFERRED` 和未知项。
- `correct/incorrect/invalid`、accuracy、runner error、attempts、截断和耗时以原始日志为准。
- 代码方法与配置必须回查 GitCode commit；单次官方分数不能单独证明方法收益。
- 原 `docs/experiments/官方评测记录.md` 与 Run #4 raw log 已迁移到本目录并删除旧副本；
  本目录现在是按日期维护的官方评测归档入口。
- 如果原始下载文件不在当前 checkout，日期页必须明确标注转录状态，不能创建看似原始的
  `raw/` 文件；机器版聚合值放在日期页的 `report.json`。

## 官方评分总汇

下面只列官方隐藏集/官方评测结果；本地 A/B、official-like hard set、Math Harness
public regression 分数不放进这张表。

| 阶段 | commit / runtime | correct / incorrect / invalid | accuracy | 记录等级 | 方法摘要 |
| --- | --- | ---: | ---: | --- | --- |
| Run #1（历史重建） | `b082c36` 之前 | 未留存明细 | 9.82% | `RECONSTRUCTED` | 旧默认 k5 + 约 4096 |
| Run #2 | `b082c36` | 9 / 43 / 60 | 8.04% | `SUMMARY_ONLY` | 32k + k5，54 runner error |
| Run #3 | `9497118` | 9 / 66 / 37 | 8.04% | `SUMMARY_ONLY` | B1 gate retry + 4096 |
| Run #4 | `b8b78aa` | 9 / 83 / 20 | 8.04% | `RAW_LOG` | C0 answer-first + k5 + 4096 |
| Run #5 | runtime `18f4f5a` / release `25f99b5` | 12 / 83 / 17 | 10.7143% | `SUMMARY_ONLY` | hetero_k5 |
| Run #6 | runtime `d9203f0` / release `7479d47` | 11 / — / 27 | 9.8214%* | `SUMMARY_ONLY` | Re2 k5，随后回滚 |
| Run #7 | runtime `9311d8c` / checkout `46c08dd` | 9 / 92 / 11 | 8.0357% | `SUMMARY_ONLY` | hetero + refine + ARH，官方负整栈 |
| Harness-era 2026-09-08 | `fc1b671` | 16 / 52 / 44 | 14.2857% | `RAW_LOG` | FSDF + answer-bank-on |
| Harness-era 2026-09-09 | `dbf3b74` | 25 / 41 / 46 | 22.3214% | `RAW_LOG` | FSDF + temporary-50-bank |
| Harness-era 2026-09-11 | `3ede125` | 24 / 20 / 68 | 21.4286% | `RAW_LOG` | Harness + Deep + hybrid FSDF + bank-on |
| Harness-era 2026-09-12 | `bb31ac4` | 29 / 26 / 57 | 25.8929% | `RAW_LOG` | Harness + Deep + hybrid FSDF + bank-on |
| Harness-era 2026-09-15 | `1507d3a` | 12 / 32 / 68 | 10.7143% | `RAW_LOG` | Harness + Deep + hybrid FSDF，bank-off，Skill-on |
| Official report 2026-10-04 | `b63059ca9b64a5a49c4add4e1830f23e58a9bb79` | 21 / 6 / 73（100 题） | 77.7778%* | `TRANSCRIBED_AGGREGATE` | ARM v2.1.4 CFR |

说明：2026-10-04 行的 accuracy 只在 27 个 valid records 上计算，不能与 112 题行直接比较；
原始下载文件未在当前 checkout 中保留，精确聚合字段见日期页 `report.json`。
Run #6 的现有汇总记录只保留 correct=11、invalid=27、runner error=10，
当前 checkout 没有完整的 incorrect 数和原始 Run #6 log，因此不填未知数字；
`9.8214%*` 仅由 11/112 计算，不代表原始日志中的独立 accuracy 字段。
Run #8 的部分历史材料只保留截断/invalid 线索，未纳入伪完整分数。

## 原始日志与历史来源

- Run #4 原始日志：[`2026-08-27/raw/official_eval_log_R6_b8b78aa_2026-08-27.log`](2026-08-27/raw/official_eval_log_R6_b8b78aa_2026-08-27.log)
- Run #1–#4 汇总：本 README 的“官方评分总汇”与 `2026-08-27/record.md`
- Run #5：[`hetero_k5_direct_release_2026-08-27.md`](../experiments/hetero_k5_direct_release_2026-08-27.md)
- Run #6：[`re2_rollback_2026-08-29.md`](../experiments/re2_rollback_2026-08-29.md)
- Run #7：[`math_reasoning_agent_experiment_driven_spec_2026-08-29.md`](../experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md)
- Harness-era 原始日志：本目录各日期页的 `raw/`；每个日期页有独立 agent 分析。

## 明确排除的非官方分数

- `MATH-HARNESS-112-DIAGNOSTIC-005` 的 60/112：公开 regression 诊断，manifest 明确
  `official_evaluation=false`，不是官方成绩。
- `MATH-HARNESS-EVAL112-SMOKE-001` 的 0/10：团队自建题集 smoke，不是官方成绩。
- 外部 hard set、FSDF iteration、FESF qualification、CAR health/A-B：都是本地或
  official-like 证据，必须回到各自 report/manifest，不能填入官方评分表。
