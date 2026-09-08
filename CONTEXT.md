# CONTEXT

数学推理智能体,参加挑战杯 2026 AI 赛道。官方评测在隐藏题上调用
`ReasoningAgent.solve()`,按 `final_response` 的答案正确性评分。

## Language

### 配置与部署

**SUBMISSION_CONFIG / canary profile**:
官方 runner 无参构造时唯一生效的提交配置。2026-09-03 经用户明确授权切换为
`contextual_answer_reconstruction_v1`，随后于 2026-09-04 经用户再次明确授权切换为
`fork_select_deepen_finish_v1`；运营参考锚为 `hetero_k5 @ 25f99b5`
（GitCode `34bc353`）。改它等于改变官方得分行为。
_Avoid_: 默认配置、线上配置(指代不清)

**Contextual Answer Reconstruction v1**:
历史 default-off 路径，先生成最多三路异构候选；只有无共识、无答案或输出结构不可信时，
才使用一次受限上下文重构。该路径尚未完成真实能力验证；RAG、工具、MCP、旧
BTCS/KCV/PS-C/V5 路径均关闭。

**FSDF v1**:
当前经用户授权的官方默认路径：Analyze → B/C Fork → D Select/Deepen → E Finish，
固定最多五次调用和 `[2048, 2048, 2048, 8192, 4096]` token 序列。仅完成零模型代码验收，
不产生数学能力或正确率结论；`SUBMISSION_CONFIG` 中 contextual reconstruction 保持关闭。

**异构候选**:
同一 client 下采用互补求解策略产生的候选；不等同于多模型集成。

**本地共识**:
基于答案表示的保守等价分组；不等同于语义证明一致或形式化验证。

**C0**:
实验对照臂 `VARIANTS["current"]`:answer-first + policy prompt + k5 自适应投票,
4096 token,heterogeneous 关闭。08-26 以 b8b78aa 完成官方 Run #4；当前
SUBMISSION_CONFIG 已切换到 FSDF，因此 C0 仅为历史对照。
_Avoid_: current、基线(易与 baseline86 混淆)

**精确 G(exact_g)**:
C0 的 prompt 族不变,k5 投票替换为 B1 门控重试的实验臂;effective 调用上限 2。
_Avoid_: gated_retry(那是无 answer-first/policy prompt 的旧变体)

**GR(exact_g_refine)**:
精确 G 叠加 refine(P3 verify/revise);effective 调用上限 = 2 + p3_call_boost。

### 证据效力(三级)

**探索窗(exploratory window)**:
小样本同窗配对实验;只能支持/降低信心,不能支撑晋升。
_Avoid_: R1/R2…(编号保留给具体战役)

**正式门(formal gate)**:
预注册门槛 + 冻结集 + 双轮独立 A/B;本地晋升的唯一依据。

**官方分(official score)**:
隐藏集评测结果,最终裁决;本地结论一律不得表述为官方预期。

### 比较与统计

**replacement_not_overlay**:
挑战者臂整体替换 C0 的某机制(k5→门控重试),而非在其上叠加;
混用两种比较口径是无效实验。

**配对符号检验(paired sign test)**:
逐题逐轮差分后只计分歧对:b=挑战者胜,c=基线胜;双侧 p 由二项检验给出。

**转述性历史统计**:
不在仓库落盘、不可从工件复核的历史数字;禁入晋升证据链,只能作线索。
(_2026-08-27 起 refine 战役已恢复为可复核,见 ADR-0002_)

**协议快照(protocol snapshot)**:
实验协议锚定为具体 commit hash;未提交工作区改动不得参与任何窗。

**void 门**:
窗口健康度预注册判据:任一臂错误率超过冻结阈值,整窗作废、不出结论;
判定先于任何过筛门,且不可被窗口内的好坏表现豁免。

**毒题(poison item)**:
跨轮、跨变体反复触发 model_error 的题;源于高延迟 × 客户端超时 ×
调用次数带来的失败暴露,与变体设计无关。

**refine_fresh**:
在冻结可见集上全新编号的 refine 复制研究(refine_fresh_r1/r2),
不回接任何历史 b/c 计数,亦不复用已废弃的 R4/R5 编号。

### Thinking-on harness（规划中的候选架构）

**正确率优先序**:
默认按 `correct > valid/可解析 > 截断率/成本` 观察；这不是把后两项丢弃，
而是只有在健康门和官方时限约束满足时，才接受正确数的候选提升。任何单项截断下降
都不能单独证明能力提升。

**自适应候选优先 (adaptive candidate-first)**:
thinking-on 下的首选候选架构。先用短调用形成一个或多个有界候选，只有候选缺失、
冲突或不确定时才启动深推/裁决；不把固定五阶段协议设为每题必经路径。
_Avoid_: 把“候选已形成”与“完整证明已完成”混为同一状态。

**并行候选对照 (parallel-candidate arm)**:
自适应候选优先的独立第二候选，允许以互补策略并行或交错产生候选，先作为本地对照，
不得与主候选架构同时叠加后宣称单变量收益。

**截断可恢复 (truncation-recoverable)**:
若截断文本已经包含明确候选，宿主保留候选并最多执行一次短 finish/continuation；
续写失败时仍可按候选来源规则返回已有候选。没有候选时不得凭空补答案。

**单题记忆账本 (per-solve ledger)**:
一次 `solve` 内的短结构化状态，记录候选、冲突、阶段状态和来源；正式评测题间丢弃，
不假设进程复用或题目顺序。

**离线错题本 (offline error notebook)**:
本地审核阶段从逐题记录中提炼的可审计错误经验。它可以跨本地实验持久化，
正式评测可以读取评测开始前冻结的版本，但运行期间不得写入、更新或让前题影响后题；
是否注入正式路径仍需独立资格门和明确授权。

**shadow verifier/skill**:
skill 首版允许以短建议路线和适用边界进入提示，但不阻塞候选形成或最终答案；
verifier 只记录 claim/verifier 结果和可用性。只有通过独立能力门后，才另开实验测试
强制 skill 或把 verifier 结果提升为选择器输入。

**候选梯度 (candidate ladder)**:
`CAR-001` 的有界调用政策：先生成一次短候选；仅在候选缺失、冲突或低置信时追加
第二候选；仍无法裁决时最多追加一次短裁决/恢复。单题默认最多三次模型调用。

**短候选协议 (short candidate protocol)**:
模型输出以 `CANDIDATE:` 标记一个当前答案，附不超过三行理由；它是答案候选的
可解析边界，不是完整证明，也不等于已验证正确。

**候选冲突账本 (candidate conflict ledger)**:
冲突时同时保存候选、来源和检查状态；宿主先做确定性等价/数值检查，无法判定时
才调用短裁决器，禁止按分支顺序静默丢弃一方。

**冻结错题本 (frozen error notebook)**:
本地审核可追加经过复核的题型经验；正式评测只能读取评测前冻结的版本，运行期间
不得写回、跨题更新或依赖题目执行顺序。

**skill 晋升**:
skill 先以软建议进入候选提示并记录使用情况；只有独立 A/B 显示正向能力收益、
且没有显著错误反转，才另立硬执行实验，不把软提示合规率当作能力证据。

**CAR-001 安全并行边界**:
首版只在评测 runner 层使用固定 3 workers 交错题目和实验臂；单题内部按候选梯度
串行调用，不假设公开 client 线程安全。单题并行候选属于后续独立实验，不与 CAR-001
的能力变量混合。

**CAR-001 确定性检查**:
候选冲突时只允许现有安全的规范化、精确等价和有限数值代入；无法判定就交给短
裁决器，不允许无界 SymPy/搜索或工具链替代模型选择。

**CAR-001 实验排程**:
F0 零模型代码门 → F1 baseline/CAR 各 6 题健康探针 → F2 24 题配对探索 →
F3 48 题 fresh A/B。窗口串行、每窗先判 VOID 再判能力/卫生/成本；RPM/TPM
只用于缩短交错窗口和提高实验吞吐，不放宽单题调用、token 或官方时限。
