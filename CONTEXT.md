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
