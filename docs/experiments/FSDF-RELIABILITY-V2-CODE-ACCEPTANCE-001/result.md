# FSDF-RELIABILITY-V2-CODE-ACCEPTANCE-001 验收结果

方法：`fsdf_diagnostics_v2`（P0）、`fsdf_multiline_handoff_v2`（P1）、
`fsdf_final_confirmation_v2`（P2a）、`fsdf_finish_prompt_v2`（P2b）；
`fsdf_branch_probe_v1`（P3）仅登记，不实现。

结论：`CODE_ACCEPTED / DEFAULT_OFF / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`

基线固定点：仓库基线 commit `9f51e12`（分支 `codex/fsdf-v1-code-acceptance-001`
工作区），验收以工作区代码 + 本目录 manifest 记录；**未提交工作区不构成有效
实验窗**，任何真实模型实验须另行授权快照。

## 测试结果（零模型，ScriptedClient / FakeClock / 合成记录）

- 既有 FSDF v1 接口与回归（`tests/test_fork_select_deepen_finish.py`）：**37/37 通过**，
  v1 行为在开关全关时逐字节保持（含 T21 v1 答案链、T33 协议失败保留 deep_final 等）。
- 本规格新增（`tests/test_fsdf_reliability_v2.py`）：**34/34 通过**。
- 本规格新增运行器报告边界（`tests/test_external_hard_sets_runner_report.py`）：**8/8 通过**。
- 全量 `pytest tests -q`：**533 passed, 4 skipped**（排除与本工作无关、且基线即失败的
  `tests/test_causal_demo.py`：该测试依赖未安装的 `mcp` 包，属于用户未跟踪的
  `causal_demo/` 工作，不在本规格范围）。4 项 skip 为既有 BTCS 归档用例。
- `py_compile` 与 `git diff --check` 通过。

## 工程验收逐项（规格 Testing Decisions / 工程验收）

- **P0 行为不变**：同一 ScriptedClient 序列（含 D 协议失败 + E 失败）在
  `fsdf_diagnostics_v2` 开关前后产生相同模型请求与 final_response（p0_02）。
- **多行交接**：多行 DERIVED 的后续关键步骤（含"第2步:"标签行）完整出现在发送给
  E 的消息中（p1_01）；空 `CANDIDATE_D:` 不吸收下一字段（p1_02）；单行
  `FINAL:` 空标记不吸收后续协议字段（p2a_10）。
- **重复字段**：相同重复值去重（p1_03）；不一致值标记
  `CANDIDATE_D_CONFLICT: true` 且不静默取首/末值（p1_04）；占位符→实值按更新
  处理而非冲突（p1_05）；候选更新、缺完成标记、显式完成结果各有覆盖
  （p1_04/p1_05/p2a_03/p2a_05）。
- **不完整交接**：预算裁剪以完整字段/完整推导项为单位（无"…[省略]…"半截内容），
  丢失对 E 可见（`HANDOFF_PARTIAL / HANDOFF_DROPPED / HANDOFF_INCOMPLETE`），
  RISK 先于 DERIVED 丢弃（p1_07）；E 上下文 6500 总上限保持（p1_08）；未选分支
  回显与自由文本不进入交接包（p1_06）。
- **终答确认**：显式 `FINAL: UNKNOWN` 不恢复旧候选（p2a_01）；冲突 FINAL 返回
  UNKNOWN（p2a_02）；字段回显、泛化占位符（TBD 等）、方法描述不进入有效终答
  （p2a_09）；未确认 CANDIDATE、boxed 中间量、孤立数学行不自动成为终答
  （p2a_04/p2a_05）；E 缺终答时仅 D 协议成功且带显式 FINAL_D 的无冲突结果可
  回退，D 协议失败的原文不绕过来源检查（p2a_03/p2a_06/p2a_07）；混合
  UNKNOWN/实值终答 fail-closed（p2a_11）。
- **答案类型边界**：整数、分数、表达式、集合/有序结构、非数值结论
  （`{1, 2}`、`x > 5`、`\frac{1}{2}`、`命题成立`、`(1, 2)`）不被误拒、不套用
  标量规则（p2a_08）；v1 正向回归用例（T21 等）在关闭态全部保持。
- **预算与隔离**：新候选保持 ≤5 次逻辑调用、token 序列
  `[2048,2048,2048,8192,4096]`、L0 单调用 4096、solve 间状态隔离与
  soft/hard deadline 门（p1_10、p2a_12、rg_01、rg_04）。
- **P2b**：仅 E 阶段 system prompt 替换为 `FINISH_PROMPT_V2`，解析与预算不变
  （p2b_01/p2b_02）。
- **报告口径**：压缩 trace 保留 `stage/status/error_category/fallback_source/
  selected_branch/max_tokens` 等（runner R1）；顶层 runner 失败、阶段 client
  异常、非字符串/空响应、协议失败、deadline 跳过分开统计（R2）；native 与
  contract 判定逐题完整对比（correct/incorrect/invalid、逐题不一致数、正确数
  一致性），并附"本地近似判定，非官方 judger 等价实现"声明（R3/R4）；旧格式
  记录安全兼容（R2/R4）；本地 client 公开诊断按任务对齐并有界（≤8，R5）。
- **P0 诊断卫生**：finalize 摘要只含固定词表字段名、布尔与 `unavailable`
  标记；公开契约拿不到 token/finish_reason 时显式标记 unavailable，不以字符数
  推断截断（p0_03/p0_05）。

## 边界与未做事项

- 未运行任何真实模型、官方评测、健康窗口或双轮 A/B；本结果只证明工程行为。
- `SUBMISSION_CONFIG` 未修改：四个新开关默认 False，官方 profile 仍为 FSDF v1 行为。
- 实验预注册（含未冻结门阈值与对照面口径冲突说明）见
  [`../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md`](../FSDF-RELIABILITY-V2-SPEC/preregistration_draft.md)；
  该草案不可执行，运行前须由用户冻结指标并另行授权。
- 提交、推送、发布作品不在本规格范围内。
