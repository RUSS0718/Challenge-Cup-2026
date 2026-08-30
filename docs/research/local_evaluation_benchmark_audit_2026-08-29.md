# 本地评测体系与开源数学 Benchmark 审计（2026-08-29）

状态：**仓库审计 + 一手来源联网核对**。本次没有运行模型评测，没有修改
`SUBMISSION_CONFIG`、运行时代码或现有数据集。外部事实只采用 benchmark 官方仓库、
官方数据卡、论文和 evaluator 源码。本文约定：

- **事实**：可由当前仓库或一手来源直接核对；
- **推断**：基于事实对本项目适用性的判断，不冒充官方结论；
- **未核项**：证据不足，进入数据前必须补齐。

## 一、结论

当前体系的**实验执行框架基本可用，题集与统计证据不够用**。具体说：

- 同题交错 A/B、臂顺序轮换、错误熔断、invalid/error/成本并报，方向正确；它可以继续
  作为实验 runner。
- 现有三个主本地集不能组成“短题 + 中等 + 复杂”的三个独立能力门：
  `medium60` 与 `complex48` 重合 24 题，两集合只有 84 道唯一题；`complex48`
  一半为 AI 生成；其 30 道 derivation/proof/explanation 中 28 道最终只按标量判分；
  `public112` 又全部被运行时分类成 `calculation`。
- 现有 AnswerJudge 对整数、简单分数和少量简单集合够用，但不够覆盖 MATH-500、
  OlymMATH、HMMT 中的区间、元组、多答案、复杂 LaTeX 与符号表达式。因此“下载新题”
  之前必须先把**抽取、等价判分、统计单元**分开。
- 不能直接采用此前“五件套整包落库”的表述：MATH-500 没有明确数据许可；AIME
  镜像声明了许可但没有说明其是否有权为 MAA 原题授权；LiveMathBench 的 CC BY 4.0
  元数据与“仅限非商业使用”的访问门并存；GSM-Plus 明确禁止作为训练集。

最终建议是：**不替换自建集**。把自建集降级为稳定的工程回归与历史对照；新增一个
去重、带 manifest、按 benchmark 原生答案类型判分的外部能力层；把 2026 题集保留为
只对最终候选运行的新鲜 shadow set。

## 二、当前本地体系审计

### 2.1 已经做对的部分

1. runner 只保存紧凑诊断，不持久化原始模型回复；连续 `model_error` 有熔断，避免把
   服务故障误判为方法退化（[`evaluate_protocol_ab.py:16`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_protocol_ab.py:16)、
   [`evaluate_protocol_ab.py:50`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_protocol_ab.py:50)）。
2. 同一道题的两臂背靠背执行，并按题号轮换先运行的臂，能显著降低时间窗漂移与固定
   顺序偏差（[`evaluate_protocol_ab.py:514`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_protocol_ab.py:514)）。
3. 逐题工件已包含 `input_file`、`round`、`variant`、`idx`、verdict、时延和失败原因，
   原始信息足以构造可复现配对键（[`evaluate_protocol_ab.py:475`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_protocol_ab.py:475)）。
4. 当前 judge 是保守三态；不可证明的符号等价返回 `unknown`，没有靠猜测美化分数。
   简单有理数、简单数值集合和受限 SymPy 等价各自有明确边界
   （[`evaluate_dev.py:53`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_dev.py:53)、
   [`evaluate_dev.py:91`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_dev.py:91)、
   [`evaluate_dev.py:157`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/evaluate_dev.py:157)）。

### 2.2 题集层的硬缺口

| 本地集 | 已确认事实 | 可以保留的用途 | 不得再主张 |
|---|---|---|---|
| `dev3` | 3 道短数值题 | client/import/最小 solve/端点健康冒烟 | 能力或泛化证据 |
| `public112` | 18 个课程方向，但 112 题全部被运行时分成 `calculation`（[`AGENTS.md:96`](D:/project/challenge_cup_2026/Challenge-Cup-2026/AGENTS.md:96)） | 短计算、答案抽取、格式卫生、历史官方相关性回归 | 证明、解释、长题或综合推理能力 |
| `complex48` | 24 道公开改编 + 24 道 AI 生成（[`build_freeze_set.py:2`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/archive/build_freeze_set.py:2)、[`build_freeze_set.py:297`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/archive/build_freeze_set.py:297)）；只与 public112 检查题干精确不重合 | 历史 A/B 连续性、路由/输出契约、长条件与跨方向压力测试 | 独立外部 benchmark、未见分布泛化、证明质量 |
| `medium60` | 明确从 complex48 过滤出 24 道公开题，再加 36 道改编题（[`build_medium_freeze_set.py:60`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/archive/build_medium_freeze_set.py:60)） | 公开来源的单窗 transfer screen | 与 complex48 合并计数或称为独立复验 |

本次逐行审计 [`complex_capability_freeze_48.jsonl`](D:/project/challenge_cup_2026/Challenge-Cup-2026/sample_data/complex_capability_freeze_48.jsonl:1)
得到：derivation/proof/explanation 共 30 题，其中 28 题的 `answer` 是数值或分数；另两题
只是“无理数”标签。换言之，当前自动分数检查的是**终结论/求值代理**，并不检查证明
是否成立、推导是否完整、解释是否回应题目。若某方法改变了 proof/explanation 正文，
这 30 题不能证明正文质量变好；最多只能证明最后的短结论没有退化。

### 2.3 当前存在一个会破坏正式池化的分析 bug

`answer_rows` 已保存 `input_file` 与 `round`，但 `paired_counts()` 在未传单轮过滤时只用
`idx` 建字典（[`analyze_paired_ab.py:19`](D:/project/challenge_cup_2026/Challenge-Cup-2026/scripts/analyze_paired_ab.py:19)）。相同 variant 下跨轮或跨数据集同 `idx` 的后写记录会静默覆盖
前一条。由此得到的 `n_paired/b/c/p` 不能作为可复现的正式池化结果。

正式分析前必须先改为：

```text
pair_key = (input_file_sha256, round, idx)
```

同一 `variant + pair_key` 重复时直接报错；不得继续覆盖。对 `complex48` 和 `medium60`
即使键修好，也必须按题目内容哈希识别那 24 道重合题，不能把它们当两次独立观测。

### 2.4 判分器的正确定位

当前 judge 可继续作为“官方短答案保守口径”，但不应强行充当所有 benchmark 的原生
判分器。最低成本的双口径是：

- `contract_score`：沿用本仓严格抽取，invalid/timeout/error 全部计入分母；回答“提交
  契约下是否稳定可判”。
- `benchmark_native_score`：按数据集声明的答案类型使用固定版本 evaluator；回答“是否
  能与公开 benchmark 同口径比较”。MATH/OlymMATH/HMMT 可使用固定版本
  [Math-Verify](https://github.com/huggingface/Math-Verify)，AIME 使用整数 exact，选择题使用
  选项 exact。
- 两者不一致时输出差集并人工抽查，不允许用更宽松口径覆盖更严格结果。Math-Verify
  支持 LaTeX、普通表达式、集合、区间、关系与矩阵，但其 `verify` 有意非对称，必须固定
  gold/pred 参数方向和版本（[官方 README](https://github.com/huggingface/Math-Verify#readme)）。
- 需要 LLM judge 或人工证明评分的题，不混入自动正式门。

## 三、候选 benchmark 逐项核对

### 3.1 总表

| Benchmark | 规模 / 语言 | 答案与官方/通行判分 | 许可与限制 | 新鲜度判断 | 与本项目契约 | 处置 |
|---|---|---|---|---|---|---|
| MATH-500 | 500；EN；7 学科、难度 1–5 | 数值、表达式、元组、文本、复数等；OpenAI grader 为归一化 + SymPy | HF 卡**未声明 license** | 2021 MATH 的 2023 固定子集；高污染/饱和风险是合理推断 | 部分匹配；须 Math-Verify，须过滤依赖缺失 Asymptote 图的题 | **值得引入，但先过许可和题面完整性门** |
| AIME 2024 / 2025 | 各 30；EN | 三位整数；lm-eval 抽 `$...$`/last-boxed 后规范化 exact | 镜像分别标 MIT / Apache-2.0；原题授权链未说明 | 到 2026 已不是新鲜集；仍是标准难题锚 | 高匹配 | **保留为稳定锚，不称抗污染** |
| OlymMATH | 200 个独立问题；EN/ZH 平行两版；100 easy + 100 hard | 仅实数与区间；官方建议 Math-Verify | MIT | 2025 发布，现已公开一年多；不保证对当前端点无污染 | 很高；图题已文本化 | **最高优先级外部能力集** |
| CMATH | 1.7k；ZH；600 val + 1.1k test；60 个 distractor seed | 数值；原 evaluator 抽末两个数字、1% 相对容差 | 数据 CC BY 4.0，代码 MIT | 2023 小学题，陈旧且容易饱和 | 高，但难度偏低 | **只做中文数值/干扰烟测** |
| GSM-Plus v1 | 10,552；EN；8 类扰动；另有 testmini | 数值；critical-thinking 为 `None`；说明沿用 GSM8K 判分 | CC BY-SA 4.0；数据卡明确禁止训练用途 | 源自公开 GSM8K，不能作为新鲜能力集 | 数值七类高匹配；`None` 类需独立协议 | **值得做 seed 级鲁棒性门** |
| LiveMathBench | v202412 238；v202505 100；含中英配置 | 短式与符号式混合；官方管线默认可接 LLM judge，规则回退只适合数值 | 元数据 CC BY 4.0，但访问门要求 non-commercial only | 设计目标是动态抗泄漏；202412/202505 到 2026-08 已衰减 | 仅规则可判子集匹配 | **暂缓正式门；许可与判分筛完后做 shadow** |
| MathArena AIME 2026 | 30；EN | 整数；final-answer 自动判，要求 boxed | CC BY-NC-SA 4.0 | 当前最有价值的新鲜竞赛锚之一，但端点 cutoff 未知 | 很高；需排查缺图题 | **最终候选 shadow，禁止调 Prompt** |
| MathArena HMMT Feb 2026 | 33；EN | 整数、分数、根式与表达式；final-answer 自动判 | CC BY-NC-SA 4.0 | 同上；比旧固定集更新 | 高，但必须用表达式等价判分 | **与 AIME26 组成 fresh63** |

### 3.2 MATH-500

**事实。** [HuggingFaceH4 数据卡](https://huggingface.co/datasets/HuggingFaceH4/MATH-500)
显示单一 test split 500 题，字段包括 `problem/solution/answer/subject/level/unique_id`；
[OpenAI PRM800K](https://github.com/openai/prm800k#math-splits) 说明它从 MATH 原 test 5,000
题中均匀随机保留 500 题，其余 4,500 被并入训练；[官方 grader](https://github.com/openai/prm800k/blob/main/prm800k/grading/grader.py)
先做规范化，再尝试 SymPy 等价，并承认可能拒绝正确答案或接纳错误答案。HF 卡没有
license 字段，且其[公开讨论](https://huggingface.co/datasets/HuggingFaceH4/MATH-500/discussions/2)
仍在询问原 MATH 数据许可。

**推断。** 它适合做跨学科、跨难度固定能力回归，但不适合证明“新方法没有利用记忆”。
题集中存在 `\text{Evelyn}`、元组、多根、区间、复数和 Asymptote 图题，当前本仓 judge
无法完整覆盖；盲抽 60 题还可能把缺图题送给纯文本 agent。

**处置。** 许可澄清前不把原题提交进公开仓库。可预注册 50 题：每个 level 恰好 10
题、7 学科均有覆盖；先排除离开 Asymptote/图片就不完整的题，再固定选择清单和上游
commit。发布结果时同时给 native 与 contract 两个分数。

### 3.3 AIME 2024 / 2025

**事实。** [AIME 2024 数据卡](https://huggingface.co/datasets/Maxwell-Jia/AIME_2024)
为 AIME I/II 共 30 题、英文、整数答案并声明 MIT；[AIME 2025 数据卡](https://huggingface.co/datasets/math-ai/aime25/raw/main/README.md)
为 30 题 test split 并声明 Apache-2.0。lm-eval 的 [aime24 配置](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/aime/aime24.yaml)
使用 greedy、单次、32,768 token；[evaluator](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/aime/utils.py)
从数学环境/last-boxed 抽取后做 hendrycks 规范化字符串相等。

**未核项。** 两个数据卡没有解释镜像上传者如何获得 MAA 原题的再授权权利。数据卡
声明的开源许可不自动证明底层竞赛内容的授权链完整。AIME 2024 中也确有 Asymptote
图面；题面完整性必须逐题检查。

**处置。** 两年各只有 30 题，不应再抽小样本。AIME24 全 30 用作固定 core 锚，
AIME25 全 30 用作独立年份确认；但它们到 2026 都不能称“fresh”。若授权链无法澄清，
不要把题面复制到公开仓库，只保留 manifest 与受控构建步骤。

### 3.4 OlymMATH

**事实。** [论文](https://arxiv.org/abs/2503.21380)给出 200 个经人工核验的独立问题，
每题有中英文平行版本；easy/hard 各 100，代数/几何/数论/组合四领域；答案被限制为
实数和区间，图题被文本化，无法文本化的题被排除。官方
[仓库](https://github.com/RUCAIBox/OlymMATH) 使用 Math-Verify，本地例程支持
EN/ZH × EASY/HARD。HF 数据卡声明 [MIT](https://huggingface.co/datasets/RUC-AIBOX/OlymMATH)。

**版本风险。** 论文原始数据是 200 个数学问题，即 400 个平行语言行；原始四文件
各 100 行可由[首发 commit `5f83d12`](https://huggingface.co/datasets/RUC-AIBOX/OlymMATH/commit/5f83d12e63ee3267f35044461a6cebad58ec3be1)
核对。当前 Hub 已多出第五个 subset、总行数高于原始 400；新增部分不应在未审计时
混进冻结集。

**处置。** 这是本项目最值得优先引入的外部集。固定首发 commit；选 40 个**唯一问题
ID**（easy 20、hard 20，四领域各 10），其中 20 题取中文、20 题取英文，语言两组
不得出现同一个数学问题。另设 12 个平行双语 pair 只分析语言一致性，不计作 24 个
独立样本。官方建议 32k 只说明公开榜的生成预算；本项目在 4096 官方约束下跑出的分数
不能与其公开榜直接横比。

### 3.5 CMATH

**事实。** [官方仓库](https://github.com/XiaoMi/cmath)声明 1.7k 道中文小学应用题，
首批 600、后续 1.1k，并有 60 个干扰 seed，每个 seed 含原题和 5 个增广题；数据
CC BY 4.0，代码 MIT。[官方 `eval.py`](https://raw.githubusercontent.com/XiaoMi/cmath/main/eval.py)
把异常回复从分母剔除；[`utils.py`](https://raw.githubusercontent.com/XiaoMi/cmath/main/utils.py)
只取末尾最多两个数字候选，整数 exact、其他数用 1% 相对容差。

**推断。** 难度远低于当前赛事目标，且原 evaluator 会因剔除错误而美化结果。它不应
进入“方法级突破”的总正确率门，但非常适合低成本检测中文题面、单位、百分数、小数、
干扰信息与答案抽取回退。

**处置。** 可选 60 题（每年级 10）作为中文卫生集；干扰集按 seed 成组报告，不使用
上游剔除分母口径。它不替代 OlymMATH-ZH。

### 3.6 GSM-Plus

**事实。** [官方仓库](https://github.com/qtli/GSM-Plus)从 GSM8K 1,319 道 test 题为
每题制作 8 类扰动，总计 10,552；v1 修正了 v0 的不现实数字和歧义。字段包含当前题、
答案、扰动类型和 seed 题/答案；[数据卡](https://huggingface.co/datasets/qintongli/GSM-Plus/raw/main/README.md)
把新增内容置于 CC BY-SA 4.0，并明确“可用于商业测试、禁止当训练集”。critical-thinking
题的 gold 是 `None`，可在[官方数据查看器](https://huggingface.co/datasets/qintongli/GSM-Plus)
直接核对。上游说明其评测沿用 GSM8K；lm-eval 的 [GSM8K evaluator](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/gsm8k/gsm8k.yaml)
按末尾 `####` 数字 exact。

**数据卡内部不一致。** README 说 testmini 从 200 个 seed 抽出 2,400 个变体，但同页
又说每个 seed 只有 8 类变体；`200×8≠2400`。因此不能只凭描述生成抽样清单，必须
实际按 `seed_question + perturbation_type` 审计行数和唯一性。

**处置。** 不把 10,552 个高度相关变体当独立题。固定 20 个 seed，每个 seed 保留原题
和全部 8 类，得到 180 行；统计单位仍是 20 个 seed。七类有数值答案的结果合并报告，
critical-thinking 单列“正确识别信息不足”率，不把字符串 `None` 混进数值准确率，也
不得把任何内容送入训练、Prompt few-shot 或 RAG。

### 3.7 LiveMathBench

**事实。** [数据卡](https://huggingface.co/datasets/opencompass/LiveMathBench/blob/main/README.md)
称 v202412 有 238 题，来源为 CNMO、CCEE、AMC、WLPMC；v202505 有 100 题。配置同时
包含 CN/EN 和 hard 子集，部分配置引用同一文件，不能把所有 Hub row 直接相加。
元数据写 CC BY 4.0，但访问表单要求勾选“non-commercial use ONLY”。官方
[GPassK 仓库](https://github.com/open-compass/GPassK)默认用 Qwen2.5-72B-Instruct judge，
仅在没有 judge URL 时退回可能只适用于数值答案的规则判分。

**推断。** “动态 benchmark”这个设计值得借鉴，但 202412/202505 到 2026-08 已经不再
天然新鲜；本项目也不应为了一个本地分数引入 LLM judge。中文配置、许可字段和访问门
之间还存在需要人工确认的不一致。

**处置。** 暂不纳入正式晋升门。只有在确认允许本项目使用、固定版本、按来源 ID 去重、
人工筛出规则可判短答案、排除需要 judge/证明评分/缺图题后，才可作为季度 shadow。

### 3.8 2026 新鲜竞赛集：MathArena

**事实。** MathArena 官方仓库把 [AIME 2026 与 HMMT Feb 2026](https://github.com/eth-sri/matharena#current-website-competitions)
列为无需额外 judge 的 final-answer competitions，并要求最终答案放在 `\boxed{}`；
parser 异常、答案存在但未抽到、疑似截断会分别告警。HF 数据卡显示
[AIME 2026](https://huggingface.co/datasets/MathArena/aime_2026) 为 30 道英文整数题，
[HMMT Feb 2026](https://huggingface.co/datasets/MathArena/hmmt_feb_2026) 为 33 道英文题，
答案覆盖整数、分数、根式和表达式；二者均为 CC BY-NC-SA 4.0。

**边界。** “2026”只能证明题目发布日期较新，不能证明当前官方模型端点没有见过；
端点版本和知识截止日期未知。AIME 数据还可能含依赖图形的题，纯文本可解性必须逐题
验收。MathArena 代码 MIT 不等于其竞赛数据也是 MIT。

**处置。** 两集合组成 `fresh63`：只在一个方法已经通过固定 core、确认窗与健康门后
运行一次；结果揭盲后不得针对错题改 Prompt，再把同一 `fresh63` 称作新鲜复验。
USAMO 2026 需要 judge，故不进入自动门。

## 四、最小推荐组合 v2

### 4.1 保留而不替换

| 层 | 内容 | 规模/统计单位 | 运行时机 | 结论边界 |
|---|---|---|---|---|
| endpoint smoke | `dev3` | 3 | 每个模型窗前 | 仅健康与接口 |
| engineering regression | `public112` | 112 | 输出、抽取、预算、runtime 改动 | 仅短计算与卫生 |
| historical stress | `complex48` | 48 | 需要与历史实验连续比较时 | 路由/终结论代理，不是证明质量 |
| public-source transfer | `medium60` | 60 | 任选其一的探索确认窗 | 不与 complex48 池化，不称独立复验 |

### 4.2 新增的最小外部层

1. **`core120_v2`：固定能力门**

   - MATH-500 50：level 1–5 各 10，7 学科都有覆盖；过滤缺图题；许可未澄清前
     不公开落库。
   - OlymMATH 40 个唯一数学问题：easy/hard 各 20、四领域各 10、ZH/EN 各 20，
     两语言不重复同一问题；固定首发 commit。
   - AIME 2024 全 30：作为整数 exact 锚；题面与授权链验收后进入。

2. **`confirm30_v2`：独立年份确认**

   - AIME 2025 全 30。不得与 AIME24 合并后只报一个总分；逐年份要求不净负。

3. **`robust180_v2`：扰动门**

   - GSM-Plus 20 个 seed ×（原题 + 8 扰动）。正确率以 seed 为统计单元；七类数值
     与 critical-thinking 分开；每种扰动仍给逐类结果。

4. **`fresh63_v1`：最终 shadow**

   - AIME 2026 全 30 + HMMT Feb 2026 全 33。只跑 finalist，不参与迭代；先确认
     CC BY-NC-SA 对当前项目及存储/发布方式的适用性。

5. **可选而非阻塞**

   - CMATH 60 题只做中文数值卫生；
   - LiveMathBench 仅在许可与 rule-verifiable 筛选完成后进入季度 shadow；
   - OlymMATH 12 个中英平行 pair 只做语言一致性，不进入独立样本总数。

这一组合不会盲目抛弃自建集：自建集负责发现工程回归、保持历史可比；外部集负责提供
难度、语言与题型的外部效度；fresh63 负责降低“在固定集上反复微调”的自污染风险。

## 五、落地前的不可跳过门

### 5.1 数据 manifest

每个冻结集必须记录：上游 URL、commit/revision、下载日期、原始与选择后 SHA-256、
声明许可与附加访问条款、行数、唯一 `problem_group_id` 数、语言、答案类型、选择算法与
seed、是否依赖图/LLM judge、是否允许公开再分发、是否禁止训练。题目不得进入 Prompt
few-shot、RAG 或训练语料。

### 5.2 静态验收

- 每行字段完整、gold 非空、ID 唯一；上游题数与 manifest 一致。
- 全池按规范化题面 hash 去重；平行翻译、扰动、同年 I/II 的关系另存 group ID。
- 图形依赖、题面截断、答案歧义、多个 gold、单位/百分号、区间和集合逐类抽审。
- benchmark-native evaluator 对全部 gold 自判 100%；为每类答案准备正确等价、错误近邻、
  不可解析三组反例测试。
- Math-Verify 版本、ANTLR runtime 与超时固定；任何解析超时 fail-closed。

### 5.3 运行与统计验收

- 先修复配对键；唯一键固定为 `(dataset_sha256, round, idx, variant)`，重复即失败。
- same-item interleaved A/B 保留；每个 dataset 单独报 `b/c/p`，重叠集不池化。
- GSM-Plus 以 seed 聚合或做 cluster bootstrap；OlymMATH 中英平行题以数学问题 ID
  聚合。禁止把相关变体当独立样本套普通 Wilson/McNemar。
- 正确、incorrect、invalid、timeout、model_error 全计入固定分母；同时报告
  contract/native 差集、调用数、token、时延与数据/配置 hash。
- `fresh63` 揭盲后立即封存；若针对其错题修改方法，下一次结果只能叫回归，不再叫
  新鲜泛化证据。

## 六、仍未核实的事项

1. MATH/MATH-500 底层数据的可再分发许可；当前 H4 卡无 license。
2. AIME 2024/2025 镜像许可是否覆盖 MAA 原始题面与解答。
3. LiveMathBench “CC BY 4.0”与“non-commercial only”并存时的实际适用条款，以及
   哪些行能在完全无 LLM judge 下可靠判分。
4. OlymMATH 当前第五个 subset 的来源、规模与相对论文首发 400 行的变更说明。
5. AIME26/HMMT26 中纯文本不可解、缺图或题面转写异常的精确题数。
6. 官方模型端点的发布日期/知识截止时间；因此任何“无污染”只能写成风险降低，不能
   写成已证事实。

在上述事项未解决前，最稳妥的近期动作不是下载所有 benchmark，而是先修复配对池化、
建立 manifest/答案类型层，然后优先落 OlymMATH 的 pinned 40；其余数据逐项过许可、
完整性与 evaluator 门。
