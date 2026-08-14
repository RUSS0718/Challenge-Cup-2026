# 开发任务清单

目标：不改变竞赛接口，不增加未验证的大型框架；在已固化的基线上用数据驱动后续演进。

最近更新：2026-07-30（P3-lite 实现与 139 项单测通过；审计确认 112 题全部被分类为 `calculation`，只能作为 18 方向短题知识覆盖集。当前后台运行“异构 + P3 验证、无修正”参考评测；该配置不会改变已选答案，且 evaluator 尚未汇总 P3 状态，因此不作为 P3 收益验收。下一步先修复复验 fail-open 和评测可信度，再建立复杂能力冻结集并执行四组双轮 A/B）。

# 第一部分：已固化基线（2026-07-25 ~ 2026-07-27，验收通过，修改时不得回退）

## 0. 已固化基线（验收通过，修改时不得回退）

当前工作区实验配置：answer-first Prompt；固定 3 次生成、`max_tokens=1024` 与按答案组审核；受控算术 L0 使用 1 次生成；异构 Reasoner 开启；P3 逐步验证临时开启、修正关闭。`enable_sympy_evidence`、`enable_dynamic_budget`、`enable_l2_routing`、`enable_local_repair`、`enable_uncertain_repair` 均关闭。异构与 P3 是否保留为正式默认，等待四组双轮 A/B 决策。

当前有效基线（`docs/p1_1/p1_1_multi_root_*`，23 题）：

- 23/23 有最终响应、0 超时、双轮 **15/23 与 18/23**（均值约 16.5/23 ≈ 71.7%）。

### 第一轮固化（2026-07-25）

- [x] 文本编码修复；固化本地解释器；client 脱敏失败分类；`evaluate_dev.py` 不向 `solve` 传 `answer`。
- [x] 无模型调用的答案提取与保守规范化；候选显式五字段；“首错 + `VERDICT`”审核；trace 卫生。

### 第二轮固化（2026-07-26）

- [x] API 超时根因诊断（`max_tokens=4096` 不返回、256 正常）；默认生成上限固定 256。
- [x] 三态等价判断（UNKNOWN 不合并）；答案组去重审核；REFUTED 不凭共识优先（有测试、对照无回归）。
- [x] 依赖精简至 `requests` + `sympy`；`failed` 判定修正；答案解析测试覆盖方程/集合/区间/向量/矩阵。

### 第三轮固化（2026-07-26）

- [x] 开发集扩至 23 题（3 道原始样例 + 20 道 `local_handcrafted_2026-07-26`，含 6 道受控算术）；非隐藏评测题，`answer` 仅本地评分。
- [x] 六组评测完成并归档：默认基线、SymPy（35 次工具检查）、动态预算（3.348 调用/10.923 秒，单次观测）、局部修正（0 次触发）、L2 路由（13 次升级）、uncertain 修复（4 次触发）。各组准确率均为 0，所有实验能力保持默认关闭。
- [x] L2 路由（冲突触发 +1 生成、独立 8 次调用上限）与 uncertain 受限修复，均有触发/不触发单元测试，默认关闭。
- [x] 评测报告新增 `answer_not_extractable_rate`、工具调用、组审核、修正计数；`baseline_a` 旧报告标注 `superseded_timeout_only`。
- [x] 36 项单元测试与提交验收通过；方案文档状态表与开发记录已同步。

## 1. P0：正确率为零的根因诊断与首个非零基线（当前最高优先级）

阻塞原因：23 题 × 6 种配置准确率全部为 0，且 `answer_not_extractable_rate=0`——答案均能提取但全错。问题不在样本量或架构，而在默认求解路径的推理输出质量。准确率接近 0 时，任何架构 A/B 都无意义（0 的任何变体仍是 0）。

- [x] 逐题分解 23 题失败：`docs/development_failure_diagnosis_2026-07-27.json` 为每题记录分类标签与一句依据（格式占位符回显、显式错误答案、缺最终标记）。
  - 验证：每题有分类标签和一句依据；区分“模型做错”与“链路做错”。
- [x] 抽样人工核查模型原始解答质量（本地调试用途，不进 trace）：256/512 的原始输出均在最终答案前截断；1024 在约 11 秒内给出算术题正确最终答案。
  - 验证：至少覆盖受控算术与非算术各若干题；若截断是主因，评估分级 token 上限并 A/B。
- [x] 检查开发集难度分布：新增 6 题 `sample_data/basic_arithmetic_dev.jsonl`。L0-256 两次均为 0/6，L0-1024 为 3/6、6/6；基础链路下限已确认非零。
  - 验证：基础题子集上默认配置准确率 > 0，否则定位链路问题。
- [x] 在失败分类基础上做针对性 prompt 迭代（单次单变量，逐项 A/B）：答案优先短提示在 L0-256 上为 0/6，无收益并保持非默认；分级 L0=1024 在完整集两次均为 6/23，已纳入默认。
  - 验证：任一改动须在新基线上可复现地提高准确率且不恶化调用数/延迟，否则回退并记录。

## 2. P1：待验证观测与证据质量

- [x] 重复运行动态预算对照：两次为 5/23、3/23，虽降至 2.826、2.652 次调用和约 10 秒，但低于默认 6/23，保持关闭。
  - 验证：至少两次独立运行，确认成本节省可复现且准确率不劣于默认基线。
- [x] 分析 SymPy 对照：20 次工具步骤中 4 次 `SUPPORTED`、0 次 `REFUTED`、2 次 `UNKNOWN`、14 次不适用；准确率 4/23，未发现系统性反驳但无默认收益。
  - 验证：输出按 claim_status 分组的统计；若 REFUTED 集中在特定题型，记录为适配范围结论。

## 3. P2：候选演进方向（依赖 P0 产出，未验证前不进默认路径）

- [x] 分级 `max_tokens`：L0 受控算术默认使用 1024，其余路径保留 256；两次完整集从 0/23 升至 6/23，且无超时。
- [x] 旧 L3 路由作废：新方案只使用 L0/L1/L2，不以大型编排或 Lean 构造正式 L3。
- [x] 修复闭环有效性重估：当前默认非零基线上修复尝试仍为 0，准确率 5/23，未发现“接近正确”挽救证据，保持关闭。

## 4. 文档与提交验收（每次提交前执行）

- [x] 更新 `docs/开发记录.md`：逐项记录已验证收益、未验证假设和被拒绝的方案。
- [x] 保持系统方案文档“已实现 / 开发中 / 规划中”与代码、测试一致。
- [x] 提交前检查：`user_agent.py` 可导入，`ReasoningAgent(client=official_client)` 可构造，单题异常仍返回非空 `final_response`，结果可 JSON 序列化，76 项测试通过（42 项原有 + 28 项 P0.1 评测与决策测试 + 3 项 P0.2.1 + 3 项 P1.1 多根规范化）。

# 第二部分：下一阶段规划（2026-07-28 起）✅ 全部完成（2026-07-29 验收通过）

阶段目标：保持竞赛接口和 6/23 默认基线不回退，先在当前架构内找出可复现的最优模型调用预算，再验证非 L0 路径的输出长度瓶颈，并用逐题证据选择一个后续改进方向。阶段三神经符号工具、阶段五因果模块和展示平台均不抢占当前优先级。

当前证据边界：

- **已确认事实**：重复基线为 6/23；23/23 有非空最终响应；0 次请求超时；14/23 题至少出现过一次候选答案不可提取；只有 idx 22 的三个候选全部被拒绝并触发 `no_valid_candidate`。
- **已确认事实**：当前非 L0 默认路径是 3 次候选生成、每个答案组 1 次审核，仓库配置的单题调用上限为 6；这是当前实现的基线预算，不是赛事规定。L0 保持 1 次生成和按答案组审核，实际至多 2 次调用。
- **已确认事实**：现有 256-token 单次诊断把 idx 22 归为 `format_placeholder_echo`；256/512 输出截断现象只做过抽样核查，尚未覆盖本轮 14 题的每个候选。
- **待验证假设**：在当前生成—抽取—按答案组审核—选择架构下，增加或减少候选生成次数可能提高正确率；仅修改 `max_model_calls` 而不改变生成计划不会产生更多候选。
- **待验证假设**：非 L0 路径的 256-token 上限是解析失败和低正确率的主要原因。不得在完成逐题对照前把该假设写成结论。

## 5. P0.1：模型调用预算扫描（当前最高优先级）

目标：在不改变 Prompt、token 上限、答案处理、审核方式和工具开关的前提下，比较不同候选数量，找出冻结开发集上正确率最高且可复现的调用配置。结论只代表已测试档位的开发集结果，不宣称是隐藏评测或全局最优。

| 预算档位 | 非 L0 候选生成 | 每个答案组审核 | 单题硬上限 |
| --- | ---: | ---: | ---: |
| 2 次 | 1 | 1 | 2 |
| 4 次 | 2 | 1 | 4 |
| 6 次（当前默认） | 3 | 1 | 6 |
| 8 次 | 4 | 1 | 8 |
| 10 次 | 5 | 1 | 10 |
| 12 次 | 6 | 1 | 12 |
| 14 次（条件触发） | 7 | 1 | 14 |
| 16 次（条件触发） | 8 | 1 | 16 |
| 18 次（条件触发） | 9 | 1 | 18 |
| 20 次（条件触发） | 10 | 1 | 20 |

- [x] 为本地评测暴露候选生成次数和单题调用上限参数；L0 继续保持 1 次生成、1024 token，所有档位的 `verifier_voting_times=1`，其他实验开关全部关闭。
  - 验证：`evaluate_dev.py` 新增 `--policy-sample-times` / `--max-model-calls` 并接入 `AgentConfig`；报告声明 `budget_config`、`max_actual_model_calls` 与 `within_call_cap`。主扫描 2/4/6/8/10/12 档位全部 `within_call_cap=True`，tier 12 因瞬时连接故障（`model_call_failed:connectivity` 38 次）数据作废、其余 0 连接故障 0 超时。
  - 42 项原有单元测试仍通过（`scripts/scan_budget.py` 为新增扫描驱动，不改动求解链路）；新增 28 项 P0.1 评测指标、gate、排序、采纳和污染排除测试，共 70 项测试全部通过。
- [x] 在同一冻结 23 题开发集上对 2/4/6/8/10/12 次档位各完整运行一次作为主扫描；保存每题正确性、实际调用数、延迟、超时、解析失败和 fallback 数据。
  - [x] 2/4/6/8/10 档位已完成（干净，0 连接故障 0 超时）：tier2=6/23(1.57调用,5.8s)、tier4=3/23、tier6=5/23(默认)、tier8=5/23、tier10=4/23。
  - [x] tier12 干净补跑完成（2026-07-28 19:43）：3/23(6.74调用,19.7s,454s)，0 连接故障 0 超时，within_call_cap=True。准确率落入已有 3–6/23 噪音平台，无提升。
  - 已获结果中准确率不随预算单调上升，峰值在最低档 tier2。
- [x] 仅当 10 或 12 次档位相对较低档位仍有正确率提升、无请求超时且完整评测能在 600 秒内结束时，继续运行 14 次；此后只有当前档位继续提升并满足相同资源条件，才按 16、18、20 次逐级上探。任一高档位超时、耗尽总预算或正确率不再提升，立即停止并记录收益平台期。
  - 结果：条件上探**未触发**——gate 要求 tier10/12 相对低档仍有提升，而 tier10(4/23) < tier2/6/8 且无提升信号；tier12 干净补跑 3/23，同样无提升。在 23 题开发集上 2–12 档位准确率已呈噪声平台（3–6/23），提高预算无稳定增益。
- [x] 从已完成扫描的档位中选择准确率最高的两个，各再独立完整运行两次；6 次档位的历史重复基线仅作参考，不替代同一实验窗口内的对照。
  - 结果：top-2 为 tier2 与默认 tier6（主扫描 tier2=6/23、tier6=5/23）。复评：tier2=[6/23, 3/23]、tier6=[5/23, 5/23]；两者均有至少一次低于 6/23，无档位可复现优于基线。
- [x] 以重复准确率为第一选择标准；准确率无法区分时，依次选择平均调用数更少、平均延迟更低的档位。若没有档位可复现地优于当前两次 6/23 基线，则保留 6 次默认配置。
  - 决策：**保留 6 次默认配置**（KEEP 6-call default）。tier2 复评结果为 6/23 和 3/23，tier6 复评两次均为 5/23；无档位两次复评均 >6/23。所有档位 23/23 非空响应、0 超时、600s 内完成，仅满足准入门槛 2–3（门槛 1 要求两轮均 >6/23，两档均未满足；`qualified_tiers=[]`，`adopted_tier=null`）。

预算档位进入默认路径必须同时满足：

1. 候选档位的两次复评准确率均高于 6/23，才能替换当前 6 次默认配置并宣称发现正确率增益。
2. 23/23 返回非空 `final_response`，请求超时为 0，每次完整评测在 600 秒总预算内完成。
3. 不使用样例 `answer`、隐藏信息或 client 私有字段；不得根据单次随机高分直接修改默认配置。

## 6. P0.2：统一失败口径并建立可比较诊断 ✅（2026-07-28 完成）

- [x] 区分"题目中至少一个候选不可提取""全部候选不可提取"和"最终进入 fallback"三种指标；现有 `answer_not_extractable_rate` 不再被表述为"14/23 题完全没有答案"。
  - 验证：评测报告能分别给出候选生成数、候选拒绝数、全候选拒绝题数和 `no_valid_candidate` 题号；trace 仍不保存模型原文。
  - 实现：`evaluate_dev.py` 新增 `candidates_generated`/`candidates_rejected`/`all_candidates_rejected` per-item 字段；summary 新增 `candidates_generated_total`、`candidates_rejected_total`、`items_with_partial_rejection_count`、`items_with_all_candidates_rejected_count`、`all_candidates_rejected_ids`。
  - 测试：新增 3 项 P0.2.1 测试，总测试 73 项（70→73）。
- [x] 对本轮出现解析失败的 idx 9-22 做逐题归因，记录截断、占位符回显、缺少最终标记、显式错误答案和链路误解析；重点复现 idx 22 在默认三候选路径下的失败。
  - 验证：每题有分类、一句脱敏依据和对应 token 配置；把"模型未产出有效答案"与"代码丢失有效答案"分开。
  - 结果：11 题归类为 `model_wrong_or_extraction_captured_noise`（格式噪声/格式指令污染为首要失败模式），1 题（idx 12）为 `model_output_sufficient_but_agent_pipeline_lost_it`（1024 token 正确但 256 丢失），2 题（idx 14、22）为 `model_output_insufficient_under_256_tokens`（even 1024 仍输出占位符）。idx 22 根因是格式指令污染，非 token 不足。4 题（idx 9/12/20/21）在 1024 token 单次调用可获得正确答案，为 P0.3 提供证据。
  - 诊断脚本：`scripts/diagnose_p0_2.py`。
- [x] 归档诊断命令、配置和 JSON 报告，不覆盖 2026-07-27 的冻结基线。
  - 验证：报告不包含原始 Prompt、模型长输出、凭证或样例答案泄漏到 `solve` 的路径。
  - 归档：`docs/p0_2/p0_2_per_item_attribution_2026-07-28.json`、`docs/p0_2/p0_2_summary_report.md`。

## 7. P0.3：非 L0 输出上限单变量 A/B ✅（2026-07-29 完成，决策：ADOPT 1024）

- [x] 仅为本地评测增加非 L0 `max_tokens` 的显式实验配置：`evaluate_dev.py` 新增 `--max-tokens` CLI 参数，接入 `AgentConfig.max_tokens`。
- [x] 256 vs 512 vs 1024 三档对照完成。512 = 3/23（低于旧基线 6/23）。1024 = 12/23（首轮），三轮复评 12/11/10 均 > 6/23。
- [x] **决策：ADOPT 1024**。1024-token 三轮复评均显著高于 6/23 旧基线，`AgentConfig.max_tokens` 默认值从 256 改为 1024。该决策的开发集增益依然有效，但赛事口径已更正为单题 20 分钟；后续路由必须在约 16 分钟收敛、18 分钟停止新调用。

## 8. P1：在新基线（~11/23）上提高剩余题正确率 ✅（2026-07-29 完成，决策：ADOPT answer-first）

- [x] P0.1 与 P0.3 已完成：调用预算保持 6 次，token 上限已采纳 1024 为新默认。
- [x] 在新基线上重新分类错误题：最高收益类别为**模型求解/输出收敛不稳定**；见 `docs/p1/p1_error_reclassification_2026-07-29.md`。
- [x] 单变量 Prompt A/B：`ANSWER_FIRST_POLICY_PROMPT`。主评 12/23，两轮复评 **15/23、12/23** 均 > 11/23。
- [x] 决策：**ADOPT**。默认 `POLICY_PROMPT` 改为 answer-first；新基线约 13/23 (56.5%)。报告：`docs/p1/p1_summary_report.md`。

本阶段完成定义：产生一个高于 11/23、两次可复现且通过提交验收的新默认基线。**已达成。**

## 8.1 P1.1：无序多根数值规范化 ✅（2026-07-29，ADOPT）

- [x] 诊断 idx 0/1/2/10：仅 idx10 为表示不兼容（通用可修）；0/1/2 硬推理，不做特判。
- [x] 单变量：`normalize_answer` 无序多根有理数集合 + `final_response` 用规范形。
- [x] 双轮 15/23、18/23 均 > P1 ~13/23；报告 `docs/p1_1/p1_1_summary_report.md`。

## 9. P2：仓库与提交卫生 ✅（2026-07-29 完成；提交/推送仍需单独授权）

- [x] 将 `.vscode/` 加入 `.gitignore`，避免误提交本地编辑器配置；不删除用户现有本地目录。
  - 验证（2026-07-29）：`.gitignore` 第 5 行已有 `.vscode/`；本地 `.vscode/` 保留；`git check-ignore` 命中且未跟踪。
- [x] 每轮结束同步 `docs/开发记录.md`、系统方案文档的状态表、评测报告与本清单，严格区分已实现、实验实现和规划中。
  - 本轮：新增 `docs/p2/p2_summary_report.md`；开发记录追加 P2；方案文档 13.1 补仓库卫生口径。
- [x] 提交前执行 76 项单元测试（42 项原有 + 28 项 P0.1 + 3 项 P0.2.1 + 3 项 P1.1）、相关模块 `py_compile`、公开 client 初始化、异常降级和 JSON 序列化检查；若测试数量变化，以实际完整测试数更新文档。
  - 验证（2026-07-29）：托管 venv 上 **76 passed**；`py_compile` 通过；client 全故障仍返回非空 `final_response` 且可 JSON 序列化。
- [x] 提交作品前重新核对赛事飞书文档中的 AtomGit `main` 分支流程和当日评测时间；提交、推送和作品页面操作均需单独授权。
  - 核对：评测拉最新 `main`；北京时间每日 12:00 与 24:00；须先在作品页点「提交作品」；准确率为主、trace 可选；参赛代码须在 AtomGit 组织仓。当前 `origin` 仍为 GitHub，**正式参赛推送前须确认 AtomGit 远端**（本轮不执行）。

## 明确暂不开展

- [ ] LangGraph、AgentScope、前端、数据库、常驻 HTTP 服务和大规模多 Agent 编排；本条不禁止 P4 规划的仓库内置 stdio MCP。
- [ ] Lean 4 只允许本地研究；禁止进入正式 `solve` 链路和正式 `requirements.txt`。
- [ ] Z3 与结构化数值执行器：待 SymPy 工具集覆盖率与收益验证后再评估。
- [ ] 因果模块默认接入：先定义独立任务、对照实验和可复现增益后再评估。
- [ ] 没有开发集数据支撑的复杂架构重构。

# 第三部分：新系统方案实施路线（2026-07-29 起）

执行主线：**题型识别 → 互补策略求解 → 合并式逐步与完整性验证 → 单轮定点修正 → 复验回滚 → 按题型输出**。

当前证据边界：

- [x] 当前工作区安装已声明依赖后 139 项测试通过。
- [x] P1.5 资产迁移已完成：默认本地集合切换为 112 题短题知识覆盖集（`sample_data/public_regression_112.jsonl`），dev.jsonl 缩减为 3 题冒烟测试，旧 23 题实验资产已退役（历史通过 Git 追溯）。该迁移 Gate 不是模型效果 Gate。
- [x] 单题时间口径为 20 分钟；Lean 4 只允许本地研究，不得进入正式 `solve` 或正式 `requirements.txt`。

## 10. P0：修正输出与规则冲突 ✅（2026-07-29 完成）

- [x] 实现 `choice | fill_blank | calculation | derivation | proof | explanation` 题型识别。
- [x] 实现 task-aware `final_response`：选择/填空输出规范答案；计算题保留简洁步骤；推导题保留关键推导链；证明/解释题输出完整但紧凑的选中解答。
- [x] 证明题不再因无法抽取单一数值而被拒绝；`trace` 仍只保留脱敏摘要。
- [x] 用 `time.monotonic()` 记录单题耗时；约 16 分钟进入收敛，约 18 分钟后不再发起新调用，最终输出由代码保底。
- [x] 验证：补充各题型输出测试、证明题入池测试、时间收敛测试，并运行全量测试与公开 client 接口验收。
  - 70/70 user_agent 测试通过（含 41 项新增 P0 测试）；117/117 全量通过
  - 公开 client 接口验收全部通过

## 11. P1：建立 18 方向短题知识覆盖集（数据与 evaluator 基础链路已完成）

- [x] 将符合公开 18 方向分布的 112 道题冻结为 `sample_data/public_regression_112.jsonl`；迁移验收期间，当前 23 题只用于新旧评测链路双轨对照。
  - 题目由本项目依据公开定义/定理重新选参和表述，不复制、也不冒充官方 samples；每行保留 `source`、`source_url`、`source_ref`、`adaptation`、`verification`。来源目录见 `docs/p1_eval/public_regression_sources_2026-07-29.md`。
- [x] `subject` 和 `answer` 只保留在 evaluator，绝不传入 `solve`。
  - 验证：测试记录 `solve` 的 metadata 仅含 `idx`；全仓特判扫描未发现 `metadata.subject`、`metadata.answer` 或按 idx 求解分支。
- [x] 使用 5 大策略家族统计：离散—代数—优化、连续纯数学、数值—微分方程、概率—统计、通用高级。
- [x] 输出总体、5 大家族、18 方向和题型宏平均结果。
  - 实现：`scripts/evaluate_dev.py` 输出 `strategy_families`、`subjects`、`problem_types` 及三类宏平均；完整 112 题分布由 `validate_regression_items` 校验。
- [x] 严格禁止按题号、题面、`subject` 或样例 `answer` 编写求解特判。
  - 验证：新增数据集实文件测试；112 行、idx 5000–5111、18 方向计数、逐题追溯字段、HTTPS 来源、重复项均通过 Gate；全量 **121/121** 测试通过；求解路径未新增题号、题面、学科或答案特判。
- [x] 2026-07-30 能力审计：112/112 均被 `classify_problem_type` 识别为 `calculation`；题面长度中位数约 30、P95 约 48、最长 63。
  - 结论：该集合不能单独验证证明、推导、解释、长题面、跨方向混合题、P3 修正或隐藏评测风格。

## 11.5 P1.5：旧评测资产退役 ✅（2026-07-30 完成）

- [x] 迁移 Gate：112 题数据完整性与答案校验通过（13/13 测试）；`subject` / `answer` 未传入 `solve`（测试通过）；新 evaluator 端到端运行通过（3 项 smoke 验证）；结构确定性已验证。
- [x] `sample_data/dev.jsonl` 缩减为官方 3 题，仅作快速 smoke test。
- [x] `sample_data/public_regression_112.jsonl` 为独立冻结回归集；`evaluate_dev.py` 和 `scan_budget.py` 默认运行该集合。
- [x] 删除旧 20 道手工题（`basic_arithmetic_dev.jsonl`，原 dev.jsonl idx 3-22）、baselines（25 文件）、diagnosis、budget_scan（25 文件）、p0_2/p0_3/p1/p1_1 实验 JSON、sample_outputs 旧产物。
- [x] 迁移摘要：`docs/p1_5/p1_5_migration_summary.md`；历史详情通过 Git 追溯。
- [x] 同步修改评测脚本默认路径（4 脚本）、README 示例命令、AGENTS.md 数据集描述、scan_budget.py docstring；全仓扫描无残留对已删资产的引用；121/121 全量测试通过。

## 12. P2：两个异质 Reasoner（实现完成；默认晋升证据待补）

- [x] `DIRECT_REASONER_PROMPT`：标准正向推导（定义→定理→逐步推演，检查边界条件）。
- [x] `ALTERNATIVE_REASONER_PROMPT`：互补策略（反证/构造/边界检查/模型交叉验证）。
- [x] `AgentConfig.enable_heterogeneous_reasoners` 默认 `True`（官方构造即走异构路径）。
- [x] `_generate_heterogeneous()`：L0=1 direct；非 L0 分配 1 alt + (total-1) direct；total≤1 不溢出。
- [x] 题型 Prompt 融合：choice/proof/explanation 等题型约束附加到异构 Prompt 末尾，不丢失。
- [x] Trace `_tr()` helper 消除 6 处重复分支；`reasoner` 标签（"direct"/"alternative"）。
- [x] 技术文档："程序化验证"→"模型交叉验证"（P4 承担真正工具执行）。
- [x] 8 项 P2 单元测试（含调用数边界、题型融合）+ 129/129 全量通过。
- [ ] 在同一评测窗口完成“同 Prompt 三采样 vs 2 Direct + 1 Alternative”至少双轮 A/B，记录准确率、题型宏平均、平均/P95 调用和延迟。
- [ ] A/B 未完成前不得把 `enable_heterogeneous_reasoners=True` 解释为已验证优于旧路径；若提交前仍无法完成，恢复最后一个有重复证据的默认配置。

## 13. P3：逐步验证 + 整体检查 + 单轮修正（实现验收通过；效果与晋升待验）

P3-lite 路线：单次合并验证 + 单轮修正 + 复验。放弃 LemmaRecord 结构化抽取。

- [x] `_verify_solution()`：单次调用完成逐步检查（ERROR:行）和完整性评估（ALL_OK:COMPLETE/GAPS）。
- [x] `_verify_and_revise()`：验证→修正（仅当可抽取答案时接受）→复验（预算法允许时）。
- [x] `_revise_with_guidance()`：接收首错+遗漏，输出修正解答；空答案拒绝（保护输出契约）。
- [x] `enable_step_verification` / `enable_step_revision` 开关已实现；当前后台评测临时开启验证、关闭修正。
- [x] 预算预留：`p3_call_boost=3`（启用 P3-lite 时 max_model_calls 6→9），覆盖 3 生成 + 3 审核 + 验证 + 修正 + 复验的最坏路径。
- [x] Trace 状态：budget 耗尽 verify→skipped；畸形或截断验证→inconclusive；修正无答案 revise→rejected；复验明确发现错误/遗漏→回滚原答案。
- [x] 10 项 P3 测试（含空答案拒绝、纯预算耗尽、终止协议、复验与回滚）+ 139/139 全量通过。
- [ ] 修复复验 fail-open：复验 `skipped`、`inconclusive`、超时或无剩余预算时回滚修正；只有复验明确通过或确定性工具明确支持时接受修正。
- 当前“仅验证”路径发生在候选选择之后且不改变答案；其运行只作调用/延迟参考，不能宣称 P3 正确率收益。

## 13.1 P3 后评测可信度修复（高优先级）✅（2026-07-30 完成）

- [x] CLI 开关：`--enable/disable-heterogeneous`、`--enable/disable-step-verification`、`--enable/disable-step-revision`，按默认值显式设置。
- [x] 报告 `budget_config`：记录实际 P2/P3 开关、`effective_max_calls`（基础上限 + boost）、去重 `max_tokens`。
- [x] 评分统计：`strict_accuracy` / `decided_accuracy` / `unknown_rate` / `verdict_counts`。
- [x] 性能指标：`p95_model_calls` / `p95_latency_seconds`。
- [x] P3 可观测：`verify_call_count` / `verify_error_count` / `revise_attempt/accepted/rejected_count` / `reverify_call/error_count`。
- [x] 三级 AnswerJudge：规范化精确 → 结构化有理数 → UNKNOWN（SymPy 待 P4 工具接入）。
- [x] `within_call_cap` 使用 `effective_max_calls` 而非 `max_model_calls`。
- [x] 紧凑答案保存：`--save-answers-to` 输出 `{idx, extracted_answer, verdict}` JSONL。

## 13.2 复杂能力冻结集

- [ ] 新建独立 `challenge_holdout`（目标 40–60 题，最终数量由题源与验算质量决定），覆盖六种题型、至少 15 道证明/推导、至少 10 道跨方向混合题，并包含长条件、多解、反例和存在性问题。
- [ ] 冻结集题面/答案不得进入 RAG 卡库，不按单题结果调 Prompt；仅用于里程碑 A/B，防止反复查看造成开发集泄漏。
- [ ] 逐题保留公开来源、改编说明、答案/证明验算和题型/风险标签；不得冒充官方题型分布。

## 13.3 四组消融与默认晋升 Gate

- [ ] A：同 Prompt 三采样；B：异构；C：异构 + P3 验证；D：异构 + P3 验证和修正。
- [ ] 每组至少两轮；112 短题集报告知识覆盖结果，复杂能力集报告六题型与混合题结果，两者不得合并成单一结论。
- [ ] 只有准确率收益可复现、P95 成本可接受、0 空响应/接口回退正常的配置才能进入正式默认路径。

## 14. P4：受控本地工具与离线 RAG（依赖 13.1–13.3）

- [ ] 首先实现普通 Python tool gateway 与三个确定性工具：`check_symbolic_equivalence`、`solve_or_verify_equation`、`evaluate_numeric_expression`；单测和收益不依赖 MCP 传输层。
- [ ] 只有协议隔离确有价值时再增加仓库内置 stdio MCP 适配；不使用 HTTP、固定端口或共享可变状态，并完成锁版本、Docker 冷安装/冷启动与降级测试。
- [ ] 工具失败时降级到普通模型推理；禁止执行模型生成的任意 Python；限制输入、复杂度、运行时间和输出长度。
- [ ] 先建立 20–40 张 BM25 或 SQLite FTS5 定理卡试点；索引随仓库提交，每题 Top 2–4，约 1200–1500 token，验证检索覆盖和净收益后再扩到 100–200 张。
- [ ] RAG 只存定义、条件、证明骨架、反例和来源，不存 112/holdout 的题目—答案对；Reasoner 与 Verifier 可分别检索正向定理卡和条件/反例卡。
- [ ] 完成无工具 / 直接工具 / RAG / 直接工具 + RAG 消融；若增加 MCP，再单独验证传输层冷启动与故障成本。无可复现额外收益的能力不进入默认链路。

## 15. P5：依赖引导修正

- [ ] 将引理依赖 DAG 用于错误根因定位和受影响范围计算。
- [ ] 在证明稳定收益前，只称为“依赖引导修正”，不宣称为真正因果推断。

## 16. 参赛提交与文档验收（持续执行）

- [ ] 每轮同步 `docs/开发记录.md`、系统方案、技术文档、评测报告与本清单，严格区分已实现、实验实现和规划中。
- [ ] 提交前运行全部单元测试（当前 159 项，数量变化以实际为准）、`py_compile`、公开 client 初始化、异常降级与 JSON 序列化检查。
- [ ] 提交作品前再次核对 AtomGit `main` 流程和当日评测时间；提交、推送和作品页操作均需用户单独授权。

## 17. P0 止血版本（官方评测 0 分根因修复）✅ 2026-08-13 完成

官方评测出现「评分任务超过系统负载主动终止」与 112 题仅 2 正确的 0 分现象。已确认根因不是单纯模型数学能力差，而是：**1024 token 截断 → 末行兜底抽取 → 多个伪候选 → 审核+验证 → 请求膨胀 → 最终仍输出截断文本**（约 780 次请求 / 98.7% finish_reason=length）。

- [x] 默认配置压缩为单次主调用：`policy_sample_times=1`、`verifier_voting_times=0`、`max_model_calls=2`；关闭 heterogeneous / step_verification / step_revision / l2_routing / local_repair。理想 112 次、最坏 224 次（较 780 减少约 71%–86%）。
- [x] 收紧 `extract_final_answer`：去掉「最后一个非空行兜底」，仅接受 `\boxed{}`、`最终答案：`/`Final answer:`/`答案：` 标记、独立短答案行（数字/分数/方程/集合/选项字母）；自然语言截断末行不再作为答案。
- [x] 计算题 `final_response` 返回紧凑规范化答案；证明/推导/解释保留完整解答（占位符回显仍拒绝）。
- [x] 主调用无明确答案 → 最多一次条件重试；记录截断代理信号（答案标记/闭合 boxed/结尾标点与连接词/未闭合公式）。
- [x] 回归测试：`P0StopBleedingTest` 覆盖「截断触发 ≤2 调用、清晰答案跳过重试、严格抽取、紧凑输出、截断信号」；全量 159/159 通过。
- [x] P0.1 实验脚本：`llm_client.InternChatClient` 增加 `finish_reasons` 记录；新增 `scripts/evaluate_token_ladder.py`（按题切片统计主调用/重试 length 率、答案标记覆盖率、Gate 1/2）+ `tests/test_evaluate_token_ladder.py`（4 项，全量 163/163）。
- [x] P0.1 token 阶梯实验执行并决策：1536/2048/3072 干净跑 112 题，准确率 67.9% / 75.0% / 80.8%（3072 双轮 81.2%/80.4%）；仅 3072 通过 Gate 2（length 10.7%/17.9% ≤ 20%、marker ≥ 95%）。**ADOPT 3072**，`max_tokens`/`l0_max_tokens` 默认 2048→3072。报告 `docs/p0_1/p0_1_summary_report.md`。
- [x] P1 方向诊断（2026-08-14）：3072 下 judge 三层判定 **incorrect=0**（三轮均 0），未知题 20–22 个中约 15 个是「数学等价但表示不一致」（LaTeX 残留/变量名/符号形式），约 5–7 个是「thinking process 泄漏到答案标记」或抽取残留。**结论：模型能力不是瓶颈，P1 的「多候选/审核/验证」无恢复空间；剩余 gap 在表示规范化与提示词泄漏治理，不在求解能力。**
- [x] 确定性工具覆盖面评估：`_extract_simple_arithmetic_expression` 在 112 题覆盖面 = 0（题面全自然语言），`enable_sympy_evidence` 无默认收益，保持关闭。
- [x] 评测侧 SymPy 等价层 + 规范化清理：`judge_correct` 增加 Level 3 严格 SymPy 等价（radical/代数式，不猜）；`normalize_answer` 清理 `$`/`\(\)`/`**`/尾引号；`is_placeholder_answer` 拒绝「明确写出答案」等提示词回显。全量 166/166。
- [ ] 后续（可选）：P3 修正仍按原 Gate 执行；表示规范化的剩余项（`\pi`/π、`e^{}` 分组、变量名归一）需逐项单测、双轮 A/B，且不绑定题号。

## 18. 复杂能力冻结集 13.2 ✅ 2026-08-14 完成建设 + 双轮基线

112 题全为短 calculation，无法证明证明/推导/解释、长题面、跨方向题与 P3 的收益。新建 48 题冻结集。

- [x] 建集：`sample_data/complex_capability_freeze_48.jsonl`（choice6/fill_blank6/calc6/derivation10/proof10/explanation10；长条件12、跨方向12；公开教材改编24 + AI生成24；纯命题2）。校验全过（分布/隔离/分类一致性/答案自洽）。设计 `docs/13_2/freeze_set_design.md`；脚本 `scripts/build_freeze_set.py`、`validate_freeze_set.py`、`analyze_freeze_set.py`。
- [x] 双轮纯基线（3072，未改任何开关）：choice 91.7% / fill_blank 100% / calc 83.3%；**derivation/proof/explanation 全 0%**（60 题次全 unknown）。报告 `docs/13_2/freeze_baseline_report.md`。
- [x] 诊断（命中决策规则 #2）：根因=输出卫生，非能力。三 prompt 缺「不要输出 thinking」压制语 → InternLM thinking 吃光 3072（length 47.9–50%）→ 答案标记被截断 + 非数值题型 `extracted_answer`=完整响应 → judge 拿 thinking 开头 vs 数值 → unknown。incorrect=0。
- [ ] 待决策方向（通用、不绑题号）：① derivation/proof/explanation 三 prompt 补 thinking 压制语；② 答案标记前置 + 非数值题型改走标记抽取（完整解答仍进 final_response，判分取标记后答案）。实施前需在冻结集双轮 A/B 验证。

## 明确不进入正式链路

- [ ] Lean 4、任意代码执行、LangGraph、AgentScope、前端、数据库、常驻 HTTP 服务和大规模多 Agent 编排。
- [ ] 为任何具体题号、题面或学科写特判。
- [ ] 把 `metadata.subject` 当作正式路由先验，或将 18 个方向直接拆成 18 个 Agent。
