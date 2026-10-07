# EXTERNAL-HARD-SETS-SMOKE-001 实验结果

状态：**SMOKE_COMPLETED / REGRESSION_SUITE_ESTABLISHED / NO_PROMOTION_CLAIM**

- 运行日期：2026-09-05
- 方法：`SUBMISSION_CONFIG`（FSDF v1，官方 solve 路径，未做任何改动）
- 题池：`sample_data/external_hard_sets/`（冻结于同日，SHA 见 MANIFEST 与 run_manifest）
- 抽样：每套分层随机 50 题（seed 20260905，4 领域每格保底 ≥2，set_a 组级抽样 ZH/EN≈1:1）
- 并发：workers=3（官方并发模拟）完成前 75 题；为提速在用户要求下以 workers=6
  续跑后 75 题（断点续跑、不重做题；请求超时/FSDF 配置不变）。两阶段 0 模型错误，
  逐题时长分布在两阶段无系统差异（阶段均值见 answers.jsonl），报告中已注明该变更。
- 判分：官方口径双轨——native（AIME 整数 exact；OlymMATH/HLE 用 Math-Verify + 仓库
  answer_equivalence + 归一化字符串）与 contract（final_response 严格抽取器）。

## 1. 总体结果（150 题）

| 指标 | 值 |
|---|---|
| native 正确 | **31/150（20.7%）** |
| incorrect / invalid | 93 / 26 |
| contract 正确（final_response 严格抽取） | 31（与 native 完全一致） |
| format_ok（final_response 非空非 UNKNOWN） | 131/150 |
| JSON 可序列化 | 150/150 |
| 模型错误 / runner 崩溃 | **0 / 0** |
| 平均调用数 | 5.0（FSDF 上限 5，难题全部用满） |
| 平均 / P95 单题耗时 | 477 s / 617 s（全部 < 20 分钟上限） |
| 总墙钟 | 阶段一约 200 分钟（3 并发）+ 阶段二约 114 分钟（6 并发） |

## 2. 分套结果

| 套 | 体系 | n | 正确 | 准确率 | invalid |
|---|---|---:|---:|---:|---:|
| set_a_olymmath_hard | 多国奥赛 HARD 档（ZH25/EN25） | 50 | 7 | **14.0%** | 6 |
| set_b_aime | AIME 2024/2025（整数 exact） | 50 | 22 | **44.0%** | 12 |
| set_c_hle_math | HLE Math 科研前沿 | 50 | 2 | **4.0%** | 8 |

分领域宏平均：Algebra 20.0%、Combinatorics 26.2%、Geometry 20.5%、Number Theory 14.7%；
无单领域空转（每领域每套均有判分样本，符合抽样分层设计）。

## 3. 口径解读（不得过度声明）

1. **难度对齐成立**：三套外部题把官方难度区间撑开——AIME 44%（可解尾部）、
   OlymMATH HARD 14%（贴近官方难题带）、HLE 4%（前沿超纲）。混合 20.7% 与官方
   隐藏集历史 8-9.8% 同一数量级且略高，说明题池难度落在官方难题附近，可用作
   提交前回归与 A/B 小窗。
2. **invalid 率 17.3%（26/150）与官方 Run#4 的 17.9%（20/112）几乎一致**：
   UNKNOWN fail-closed 行为在外部难题上复现了官方形态，链路无格式层异常。
3. **contract 与 native 完全一致**：31 个正确答案全部由 final_response 严格
   抽取直接命中，无 salvage 依赖；19 个 UNKNOWN 为预算内未解出的 fail-closed。
4. 本轮是回归冒烟，不是晋升实验：不产生 FSDF 相对任何基线的能力结论，
   不修改 `SUBMISSION_CONFIG`，不进入 excluded_approaches 的能力处置表。

## 4. 复现与产物

- 池构建：`scripts/build_external_hard_pools.py`（seed 20260905，HLE 领域标签
  人工复核记录在脚本内，所有选题在模型调用前冻结）
- 运行器：`scripts/run_external_hard_sets_smoke.py`（分层抽样 + 判分 + 断点续跑）
- 逐题明细：`answers.jsonl`（final_response、pred、native/contract 判定、
  调用数、时长、紧凑 trace；trace 无 API key、可 JSON 序列化已逐题校验）
- 运行清单：`run_manifest.json`（workers=6 阶段）、`run_manifest_workers3_phase1.json`
  （阶段一存档）、`console log`、`report.json`

## 5. 后续使用约定

- 回归门：提交前用固定 seed 跑 `set_a`+`set_b`（100 题，约 4 小时 @3 并发），
  关注 correct 数、invalid 数、model_error 数三项无回退。
- 方法对比：同 seed 同题集、同窗口交错，两臂同 workers；不得跨窗比较。
- 扩池：AIME 池当前 52 题（用户裁定不扩充）；HLE 池 80 题（清洗后有效池约
  396 题，可按同协议扩到 150+）。
