# 评测缺口核对 B：格式约束 / 鲁棒性 / 争议细节（2026-08-28）

状态：**只读网络核对**。本次没有运行任何模型评测、没有修改运行时代码；只新增本笔记，
不编辑主笔记 [`math_agent_evaluation_methods_2026-08-28.md`](math_agent_evaluation_methods_2026-08-28.md)。
本文仅负责主笔记中标 ⚠️ 的证据缺口里属于"格式约束/鲁棒性/争议"分工的 5 项，
逐条把 ⚠️ 升级为 ✅（或标注仍未能核对）。标注约定沿用主笔记：✅ = 本会话核对过一手原文，
⚠️ = 未核对或有缺口；社区复现/二手讨论会明确标注"二手"。

## 1. Let Me Speak Freely（2408.02442）主张范围与社区复现/反驳

### 1.1 原文主张范围（✅ 本会话核对 arXiv 摘要页）

- 题名/作者：[Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models](https://arxiv.org/abs/2408.02442)，Zhi Rui Tam, Cheng-Kuang Wu, Yi-Lin Tsai, Chieh-Yen Lin, Hung-yi Lee, Yun-Nung Chen（Appier；v3 2024-10-14）。
- 摘要级主张：结构化输出下 "we observe a significant decline in LLMs reasoning abilities under format restrictions"；且 "stricter format constraints generally lead to greater performance degradation in reasoning tasks"；示例格式为 "structured formats like JSON and XML"。注意：**摘要页不含任何基准数字**（GSM8K 等具体降幅需读正文，本次未读正文，此缺口保留 ⚠️）。
- 官方代码仓库：[appier-research/structure-gen](https://github.com/appier-research/structure-gen)（✅ 仓库元数据核对）。

### 1.2 社区反驳（一手博文，利益相关方，已通读原文）

[dottxt "Say What You Mean: A Response to 'Let Me Speak Freely'"](https://blog.dottxt.ai/say-what-you-mean.html)（作者 Will Kurt；**博客而非 arXiv 论文**，dottxt 是结构化生成库 outlines 的开发商，属一手但非中立方）。核心内容：

- 用同模型（Llama-3-8B-instruct）重跑原文的三个争议评测，结果与原文相反（structured 略优）：

  | 任务 | Unstructured | Structured |
  |---|---|---|
  | GSM8K | 0.77 | 0.78 |
  | Last Letter | 0.73 | 0.77 |
  | Shuffle Object | 0.41 | 0.44 |

- 指出的原文问题（原文引用）：①原文自己在分类任务上发现结构化更优；②NL 与结构化用的 prompt **不相同**，非同口径比较；③结构化 prompt 信息不足（示例 prompt 只说 "You must use the tool" 但未给任何 tool 定义，且全篇未提 JSON）；④原文真正比较的是"用第二个 LLM（claude-3-haiku，原文称 'Perfect Text Parser'）解析第一个 LLM 的输出"；⑤把 constrained decoding 意义上的 structured generation 与 API 的 "JSON-mode" 混为一谈。
- **对本仓库最有价值的证据**：解析器选择本身就大幅改变分数——Last Letter（150 题）同一批生成结果，strict regex 0.35 / AI parser 0.57 / 手写宽松 regex 0.61；被 strict regex 漏掉但被恢复的例子如 "The answer is e-S-S-E." → ESSE。
- 复现材料：博文给出 GitHub 复现 notebook 链接（本次未逐个运行核对）。

### 1.3 官方仓库的社区复现情况

- [appier-research/structure-gen](https://github.com/appier-research/structure-gen) 的 issue 区**没有任何公开的复现争议 issue**（✅ 经 GitHub API 列出全部 issue/PR，仅 1 个已关闭 PR "[feat] test Osmosis-Structure-0.6B"）。争议主要存在于 dottxt 博文与社区讨论（二手：[Reddit r/MachineLearning 讨论串](https://www.reddit.com/r/MachineLearning/comments/1gwswn7/r_say_what_you_mean_a_response_to_let_me_speak/)、HF papers 页对 2408.02442 的评论区链接 dottxt 回应）。
- 后续独立文献（二手引用关系，本次未读原文）：arXiv:2501.10868（Generating Structured Outputs from LLMs）、arXiv:2509.21791（Navigating the Impact of Structured Output Format on Reasoning）等继续引用该争议，说明 2025 年后仍未有定论。

### 1.4 对本仓库的适用性/边界（对主笔记 ⚠️ 的升级）

- 主笔记 5.3 的"强制 JSON 等格式约束可损伤推理性能——作方向性证据"**维持不变**：定量主张处于未决争议（原文 vs dottxt 反驳各有实验、无中立第三方复现定论），不得作为定量依据。
- 双方**共同**支持的结论可用：无论哪方，"答案抽取/解析方式的选择"都显著影响评测分数（dottxt 的 0.35→0.57→0.61 是最直接的一手证据）。这与主笔记"抽取卫生决定分数"主线一致，可放心引用。
- dottxt 强调"instruct 模型需在 prompt 中显式给出目标结构并给匹配的示例"——对提交侧的启示是：最终答案格式纪律应在 Prompt 中显式声明并给示例，与"自由文本 + boxed"路线不冲突。
- 边界：dottxt 是商业利益相关方（outlines 作者），其反驳数字未获独立复现；本笔记维持"方向性证据"定位。



## 2. GSM-Symbolic 批评文（2605.28700，Statistically Earnest）

**✅ 本会话经 arXiv API 核对摘要全文**：[The Importance of Being Statistically Earnest: A Critical Re-evaluation of GSM-Symbolic](https://arxiv.org/abs/2605.28700)（v2 提交于 2026-05-28）。

它批评 GSM-Symbolic（Mirzadeh et al.）的三点：

1. **统计方法薄弱**：原文对 25 个模型得出"跨模板变体一致性掉分 → 模型缺乏真正推理能力"的结论；批评文用带每题随机效应的广义线性混合模型（GLMM）重评 20 个开源权重模型，发现**只有一半模型**在原始 prompt 格式下表现出统计显著的性能变化。
2. **数据集本身有分布偏移**：主 GSM-Symbolic 数据集的题面整数分布相对 GSM-Base **系统性偏向更大的整数**（K-S 统计量 = 0.12，p < 0.001），与原作者的声明矛盾；控制这个"大数效应"后，约再有一半的显著性变化被解释掉。
3. **失败模式是模型特异的**：在仍有显著差异的模型中识别出不同的失败画像（变量绑定脆弱、算术限制、双任务干扰），认为"对 LLM 推理能力的一揽子论断在统计上过早、在机制上有误导"。

**对本仓库的适用性/边界**：主笔记 5.3 已把该文定位为"GSM-Symbolic 扰动结论需谨慎引用"——核对后可把 ⚠️ 升级为 ✅（摘要级）：扰动评测仍可做本地回归，但"扰动后掉分 = 记忆/脆弱"的推断要控制题面统计量（如数值大小分布），且显著性要按题建模，不能只看均分。这同时支持 AGENTS.md"扰动实验不得逐题调 Prompt"的红线：批评文正好说明扰动差异里混着混杂因素。

## 3. Adding Error Bars to Evals（2411.00640）→ ✅

**✅ 本会话经 arXiv API 核对摘要全文**（代理 B 中断后由主会话补核）：[Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations](https://arxiv.org/abs/2411.00640)（Miller, 2024）。

- 核心主张：评测本质是实验，但评测文献基本忽略了其他学科的实验分析与规划方法。把评测问题概念化为"来自不可见超总体的抽样"（super-population），给出分析评测数据、**度量两个模型之间差异**、规划评测实验的公式。
- 明确输出：一组"运行语言模型评测并报告实验结果"的具体建议，目标是最小化统计噪声、最大化信息量。
- 对本仓库的适用性/边界：摘要级核对（正文公式未逐条核对 ⚠️）。支持主笔记 5.2 与 AGENTS.md"双轮独立 A/B"预注册的统计学依据：112 题规模下两模型正确数差 1–3 题可能只是抽样噪声，报告应给区间而非点值。

## 4. PromptBench 库（2312.07910）支持的扰动类型清单

**✅ 本会话核对**：arXiv 摘要（[PromptBench: A Unified Library for Evaluation of Large Language Models](https://arxiv.org/abs/2312.07910)，v3 2024-08-20）确认它是统一评测库（prompt 构建、prompt engineering、数据/模型加载、对抗 prompt 攻击、动态评测协议、分析工具；代码在 [microsoft/promptbench](https://github.com/microsoft/promptbench)）；其 [README](https://github.com/microsoft/promptbench) 的 Adversarial Attacks 一节列出支持的扰动类型：

- **字符级**：DeepWordBug、TextBugger
- **词级**：TextFooler、BertAttack
- **句子级**：CheckList、StressTest
- **语义级**：Human-crafted attack

另外两条与污染相关的库能力（README 原文）：Prompt Attacks 部分依赖 TextAttack；集成了动态评测框架 DyVal（arXiv:2309.17167），"generates evaluation samples on-the-fly with controlled complexity"——即官方定位里动态生成本身就是缓解测试数据污染的手段。

**对本仓库的适用性/边界**：README 的字符/词/句子/语义四级清单可直接作为本地扰动回归（同题改写、子句顺序、数值替换）的分类参照；注意库跑攻击需要 TextAttack 依赖，本仓库提交版不得引入（提交环境只应依赖已声明的最小依赖集），本地实验使用即可。



## 5. Open LLM Leaderboard v2 使用 Math-Verify 的官方出处 → ✅ 出处定位 / ⚠️ 正文逐字

- **出处定位（✅ 经检索确认）**：
  - v2 公告：["Performances are plateauing, let's make the leaderboard harder"](https://huggingface.co/spaces/open-llm-leaderboard/blog)（Open LLM Leaderboard 官方博客，2024-06）——v2 换用更难基准（MATH L3–5、GPQA、MMLU-Pro、MuSR、IFEval、BBH）；
  - Math-Verify 采纳：["Fixing Open LLM Leaderboard with Math-Verify"](https://huggingface.co/blog/math_verify_leaderboard)（HF 官方博客）——官方用 Math-Verify 重新评测榜单模型，修复既有解析缺陷造成的系统性低估。
- **边界**：本机网络无法直连 huggingface.co（HTTP 000），两条博文**正文未逐字核对**（⚠️）；"重评 3751 个模型、部分 MATH 分数翻倍以上"等细节来自检索摘要与社区讨论（二手），引用具体数字前需打开原文。结论方向与 Math-Verify README 的判分器差异表（✅ 已核）相互印证。

## 6. 来源表

| 来源 | 核对状态 | 关键内容 |
|---|---|---|
| [Let Me Speak Freely?](https://arxiv.org/abs/2408.02442) | ✅ 摘要页（缺口 B） | 格式约束下推理下降、约束越严降幅越大；摘要无基准数字（正文数字 ⚠️） |
| [dottxt "Say What You Mean"](https://blog.dottxt.ai/say-what-you-mean.html) | ✅ 通读（一手、利益相关方） | 同模型重跑反转结果；解析器选择 0.35→0.57→0.61；原文 NL/结构化口径不等 |
| [appier-research/structure-gen](https://github.com/appier-research/structure-gen) | ✅ issue 区核对 | 官方仓库无公开复现争议 issue |
| [Statistically Earnest](https://arxiv.org/abs/2605.28700) | ✅ arXiv API 摘要 | GLMM 重评仅约半数模型显著；变体题面整数分布偏移（K-S=0.12）；失败模式模型特异 |
| [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) | ✅ arXiv API 摘要 | 评测=实验；两模型差异度量与实验规划公式 |
| [microsoft/promptbench](https://github.com/microsoft/promptbench) | ✅ 摘要 + README | 四级攻击清单；集成 DyVal 动态生成（缓解污染的官方定位） |
| [Open LLM Leaderboard 博客](https://huggingface.co/spaces/open-llm-leaderboard/blog) / [Math-Verify 采纳公告](https://huggingface.co/blog/math_verify_leaderboard) | ✅ 出处定位；正文 ⚠️（本机网络不通） | v2 换难基准；官方用 Math-Verify 全量重评 |
