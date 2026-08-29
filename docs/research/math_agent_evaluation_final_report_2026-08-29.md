# 数学推理 Agent 评测方法学最终报告（2026-08-29）

状态：**只读调研最终报告**。本次（2026-08-28/29 两日）未运行任何模型评测、未修改
运行时代码、未触碰 `SUBMISSION_CONFIG` 与提交仓库。全部结论基于一手来源：论文
arXiv 页/API、开源项目源码与 README（存档 `tmp/research_verify/`）、数据集 API
可达性实测。标注：**✅** = 已核对原文/源码；**⚠️** = 未核对或有缺口。

支撑文件（本报告不重复其细节）：
- 主笔记：[`math_agent_evaluation_methods_2026-08-28.md`](math_agent_evaluation_methods_2026-08-28.md)
- 基准与协议缺口核对（两轮）：[`evaluation_gaps_a_基准与协议细节.md`](evaluation_gaps_a_基准与协议细节.md)
- 鲁棒性与争议核对：[`evaluation_gaps_b_鲁棒性与争议细节.md`](evaluation_gaps_b_鲁棒性与争议细节.md)
- 相邻能力侧调研（本报告刻意排除能力方法）：[`math_agent_capability_methods_2026-08-27.md`](math_agent_capability_methods_2026-08-27.md)

---

## 一、执行摘要

1. **判分实现已源码级覆盖 13 个**（本次从 9 个扩展到 13 个，新增 OpenAI
   simple-evals、lm-eval AIME 任务、MathArena、ProcessBench 侧）。判分器分
   三主范式 + 一个短数值小类，且**系谱清晰**：hendrycks 原版 → ToRA
   math-evaluation-harness → DeepSeek-Math → Qwen2.5-Math 一条线；Minerva 归一化 →
   lm-eval 一条线；Math-Verify 独立成派并被 Open LLM Leaderboard v2 采纳；
   OpenAI simple-evals 独树一帜地用 **LLM judge 回退 + 16 次重复**。
2. **"判分对齐"是本仓库最大且最安全的非答题杠杆**：13 个实现中，
   `\boxed{}` + 最简规范形 + 明确答案句式在**全部口径下安全**；而表示不一致
   （0.5 vs \frac{1}{2}、无序集合、单位、前缀等）在字符串相等族（hendrycks/
   OpenCompass/MathBench 开放题）下直接判错。官方判分器黑盒，无法投机对齐，
   只能落在"全口径共识区"。
3. **本地评测集选型完成**：按"可程序判分、中英覆盖、难度分层、新鲜抗污染、
   预算适配"五条标准，推荐五件套组合（MATH-500 / AIME24+25 / OlymMATH 双语 /
   CMATH 中文 / GSM-Plus 扰动 / LiveMathBench 新鲜集），全部经 hf-mirror 实测
   可达（本机 huggingface.co 不通，hf-mirror.com 通——这本身是重要工程事实）。
4. **评测方法论有三方先例可抄**：重复方差控制（simple-evals 16×、MathArena 4×、
   OlymMATH pass@1/cons@x）、抽取失败告警三分类（MathArena 的 💀/⚠️/❕ 旗标）、
   判分器间差异量化（Math-Verify 重评 leaderboard、双判分器并行）。全部映射为
   本仓库纯评测侧改进，不触答题逻辑。

---

## 二、判分实现全景（13 个，含系谱）

### 2.1 主范式

| # | 实现 | 判分核心 | 范式 | 核对状态 |
|---|---|---|---|---|
| 1 | hendrycks 原版 `modeling/math_equivalence.py` | `strip_string` 后**字符串相等**，异常回退裸串；无 sympy 无容差 | 字符串相等族 | ✅ 源码 |
| 2 | lm-eval `hendrycks_math` | 同上移植版 | 字符串相等族 | ✅ 源码 |
| 3 | lm-eval `minerva_math` | 强制句式抽取（缺失=`[invalidanswer]`）+ Minerva 附录 D 归一化 + sympy 等差 5s 超时 fail-closed；双报 math_verify | 解析+符号等价族 | ✅ 源码 |
| 4 | lm-eval `aime24/25` | 抽取：`$...$` → boxed 覆盖；`is_equiv` = hendrycks strip_string 相等；greedy、`max_gen_toks=32768` | 字符串相等族（整数题） | ✅ 源码 |
| 5 | OpenAI simple-evals `math_eval.py` | prompt 要求 `Answer:` 行且**明说不需 boxed**；抽取 `ANSWER_PATTERN`（缺失=None 判错）；等价 = 字符串相等失败后**回退 LLM judge**；**默认 16 次重复** | LLM judge 回退族 | ✅ 源码 |
| 6 | HuggingFace Math-Verify | 格式无关抽取 → SymPy 公共表示 → 等价类（数值容差/集合对称差/矩阵/不等式翻转）；`verify` 有意不对称防 reward-hack | 解析+符号等价族 | ✅ README；源码 ⚠️ |
| 7 | OpenCompass `datasets/math.py` | last-boxed → 归一化精确串匹配（hendrycks 变体），多级降级重试 | 字符串相等族 | ✅ 源码 |
| 8 | Qwen2.5-Math `evaluation/` | 抽取链（句式→last boxed→"answer is"→"答案是"→末位数字）+ `math_equal` 级联（rel_tol 1e-4、金标三向 /100×1×100、SymPy 三解析器、pebble 3s fail-closed） | 解析+符号等价族 | ✅ 源码 |
| 9 | DeepSeek-Math `evaluation/` | 全 boxed 链 + 末位数字兜底；`is_correct` = abs<1e-3 / 裸串 / `math_equal`（simplify 等差）；**多答案双列全匹配 + `\cup` 拆分** | 解析+符号等价族 | ✅ 源码 |
| 10 | CMATH `eval.py` | 位置正则抽数字（不感知 boxed）+ 相对容差 1e-2；**异常回复剔除出分母** | 抽数字+容差小类 | ✅ 源码 |
| 11 | MathBench 开放题（OpenCompass `mathbench.py`） | 触发句定位第一个数字（无则全文末数字）+ **精确串匹配**；无 boxed 感知/sympy/容差——**归一化最窄** | 字符串相等族（极窄） | ✅ 源码 |
| 12 | OlympiadBench | 数值 1e-8 容差 + SymPy 差值；证明题不自动判分；论文自认 "Incorrect Judging" | 解析+符号等价族 | ✅ 全文+仓库 |
| 13 | MathArena（NeurIPS D&B '25, arXiv 2605.00674） | final-answer 竞赛自动判分（"Requires judging: No"）；证明竞赛用 judge agent（配置含 gemini maj/norm 等消融）+ 官方榜人工校验；**每题默认 n=4 次重复**；结果页三旗标告警 | 混合（自动 + judge + 人工） | ✅ README+仓库树；自动判分具体实现 ⚠️ |

### 2.2 系谱结论

- **hendrycks 血统**：hendrycks 原版 →（移植）lm-eval hendrycks_math；→
  math-evaluation-harness（ToRA）→ DeepSeek-Math `eval_utils` → Qwen2.5-Math
  `grader.py`（文件头自述借用链）。Qwen 版是其最完整后裔。
- **Minerva 血统**：论文附录 D → lm-eval minerva_math（逐字符拷贝注释）。
- **独立派**：Math-Verify（HF，Leaderboard v2 官方采纳并全量重评）；OpenCompass
  自有变体；simple-evals（OpenAI，LLM judge 路线）；MathArena（平台化）。
- **对本仓库的意义**：主流判分收敛到"归一化字符串相等"与"解析+符号等价"两族，
  二者行为差异（无容差 vs 容差）正是本地双判分器并行的理论依据。

---

## 三、判分失败模式与"共识表示"（对 13 个实现全部成立）

1. 缺答案句式/boxed → invalid 或抓错（Minerva `[invalidanswer]`、simple-evals
   None、MathBench 无触发句抓全文末数字）。
2. 十进制 vs 最简分数：字符串相等族判错（除 hendrycks `0.5` 硬编码特例）；
   容差族（Qwen/DeepSeek/CMATH/OlympiadBench）安全。
3. 无序集合/多答案：hendrycks 族完全不处理；DeepSeek 有双列全匹配 + `\cup`
   拆分；Math-Verify 有对称差。**规范集合序仍是最安全表示**。
4. 单位/百分号/度：词表式覆盖不全；Qwen 金标三向（/100、×1、×100）宽容百分比。
5. sympy 解析失败 = 判错（fail-closed 是主流选择）。
6. 分母纪律：**CMATH 把异常剔出分母是反例**；MathArena 用 💀/⚠️/❕ 旗标显式
   标记解析失败/"答案在但没抽到"/截断——**本地报告应效仿 MathArena 而非 CMATH**。
7. 判分器误判是官方自认现象（Let's Verify 原句、OlympiadBench "Incorrect
   Judging"、Math-Verify "低估 40 点"）。

**结论（不变，证据更强）**：`final_response` = 明确答案句式 + `\boxed{}` 内
最简规范形 + 无解释性尾缀，在全部 13 个口径下安全；这就是本仓库抽取卫生的
目标表示。

---

## 四、开源评测项目方案盘点（工程视角）

| 项目 | 判分 | 工程特点 | 可复用点（本仓库） |
|---|---|---|---|
| lm-evaluation-harness | §2.1 #2/3/4 | task yaml 化（dataset_path/generation_kwargs/until 停止串/repeats）；AIME 配置 greedy+32k | 任务配置化思想；AIME 32k 预算警示——4096 之下"答案优先"更关键 |
| OpenCompass | #7/11 | 数据集+评测器+配置三层；CircularEvaluator（选项轮转全对才算） | CircularEval 思路可用于本地 MCQ 回归（防选项先验） |
| HuggingFace Math-Verify | #6 | 纯判分库，与 harness 解耦 | **直接引入为本地第二判分器**（不进提交环境） |
| OpenAI simple-evals | #5 | n_repeats=16 方差控制；LLM equality 回退；MATH-500 split | 重复次数先例；LLM judge 仅作差集复核的先例 |
| Qwen2.5-Math / DeepSeek-Math 自建 | #8/9 | 抽取-归一化-等价全链自包含；RL 验证器与评测同源 | `math_equal` 级联可作为本地第三口径参考实现 |
| MathArena | #13 | 平台化：竞赛 YAML、模型 YAML（成本/发布日期/max_retries=50/timeout=2000s）、agent 脚手架、三旗标告警、输出 UI | **三旗标告警分类**（💀 解析错 / ⚠️ 答案在未抽到 / ❕ 截断）直接映射为本仓库 trace 的 invalid_reason 枚举；报告加成本与模型日期字段 |
| ToRA math-evaluation-harness | （系谱节点） | 抽取+判分离散脚本 | 系谱知识，不复用 |
| GSM-Plus 管线 | GSM8K 同款 | 8 类扰动 × 1319 种子题 = 10,552 + testmini 2,400；字段含 perturbation_type/seed_* | **扰动轴分类学**：数值替换/位数扩展/整数-小数-分数转换/加运算/逆运算/改写/干扰插入/批判性思维 |
| OlymMATH 管线 | Math-Verify 官方推荐 | EN/ZH × EASY/HARD 四子集；local_tester 算 pass@1 与 cons@x（--sample 10, T=0.6, 32k）；HF 上公开 28 模型 58 万条评测日志 | 双语对照难度分层；cons@x 口径；公开日志可做判分器行为对照 |
| LiveMathBench（OpenCompass） | （论文 ⚠️ 细节未核） | 202412 期：AMC/CCEE(高考)/CNMO/WLPMC × cn/en + hard；202505 期 en——**用截断后新竞赛题抗污染** | 中文新鲜集首选 |

---

## 五、适合本仓库的数学评测集选型

### 5.1 选型标准

(a) 终答案可程序判分（数值/表达式，非证明）；(b) 无隐藏答案依赖、允许本地
使用；(c) 中文 + 英文覆盖（隐藏题大概率中文语境）；(d) 难度分层（GSM 级 →
AMC → AIME → 奥赛）；(e) 新鲜或抗污染（LiveBench/后截断题）；(f) 规模适配
预算（官方并发 3 / 单题 20 分钟 / 整轮 6 小时 → 本地也要串行且小批量）；
(g) 判分器可复用（已有成熟实现，避免自研等价判断）。

### 5.2 候选总表（全部 ✅ 本会话核对可达性/规模/语言）

| 数据集 | 规模/形式 | 语言 | 答案/判分 | 定位 | 来源 |
|---|---|---|---|---|---|
| MATH-500 | 500 题选择题外全开放 | EN | boxed+hendrycks 族 everywhere | 通用标准回归 | HF `HuggingFaceH4/MATH-500` ✅；出处 2305.20050 |
| AIME 2024/2025 | 各 30 题 | EN | 整数 exact | 整数答案天花板 + 新鲜（25 期） | HF `Maxwell-Jia/AIME_2024` / `yentinglin/aime_2025` ✅；lm-eval aime24/25 任务 ✅ |
| GSM-Plus | test 10,552 / testmini 2,400（8 类扰动） | EN | 数值，GSM8K 同款判分 | **扰动鲁棒性回归**（唯一成体系扰动轴） | HF `qintongli/GSM-Plus` ✅；论文 2402.19255 |
| OlymMATH | EN/ZH × EASY/HARD（含 LEAN 附加） | **双语** | boxed + Math-Verify 官方推荐 | 中文奥赛级 + 双语对照 | HF `RUC-AIBOX/OlymMATH` ✅；论文 2503.21380 |
| CMATH | 1.7k（600 val + 1.1k test；60 题干扰子集） | ZH | 数值容差（自有 eval.py） | 中文数值卫生回归（注意其异常剔出分母的反例口径） | HF `weitianwen/cmath` ✅；论文 2306.16636 |
| LiveMathBench | 202412：AMC/CCEE/CNMO/WLPMC × cn/en + hard；202505 en | **双语** | 短答案 | **新鲜/抗污染主力** | HF `opencompass/LiveMathBench` ✅；论文 2412.13147 |
| MathArena 各期竞赛 | AIME 2026、HMMT Feb 2026、Apex 等（公开金标） | EN | 自动判分（实现 ⚠️） | 季度新鲜补充 | github.com/eth-sri/matharena ✅；论文 2605.00674 |
| OlympiadBench | 8476（开放 79%/证明 21%） | 双语 | 1e-8+SymPy | 拉伸极限（可选） | ✅ 前核 |
| ProcessBench | 过程错误定位 | EN | 判分器评审基准 | **仅评测侧知识**（不进运行时） | HF `Qwen/ProcessBench` ✅；论文 2412.06559 |
| GSM8K | 1319 test | EN | `####` 精确 | GSM-Plus 的种子对照 | ✅ 前核 |
| AGIEval / GAOKAO-Bench | 高考数学 MCQ/填空 | ZH | MCQ 精确 | 中文选择题回归（可选；判分细节 ⚠️ 未核） | 2304.06364 ✅；OpenLMLab/GAOKAO-Bench 仓库存在 ✅ |

### 5.3 明确不推荐

- **DynaMath**（2410.08195）：实为**视觉**数学基准（VLM 专用），文本不适。
- **证明类**（miniF2F/IMO/USAMO/Putnam）：无自动判分；MathArena 也只能 judge
  或人工。与本赛事 outcome 判分形态不符。
- **Project Euler**（MathArena 期）：金标不公开。
- **FrontierMath**：题目与 checker 私有。
- **需 logprobs 的污染检测**（Min-K%，2310.16789 ✅）：官方 client 无 logprobs，
  不可用；用 10-gram 自检与"后截断新鲜题"替代。
- **GSM-Symbolic 原文**：有 2026 批评文（GLMM 重评、整数分布偏移），扰动结论
  须谨慎；其扰动思想已由 GSM-Plus 更规范地实现。

### 5.4 推荐本地组合 v1（预算适配）

官方约束映射：本地共享端点必须串行；若隐藏集规模接近 112 题、整轮 6 小时，
则平均每题预算 ≈3 分钟——本地回归的单轮全量也要按此裁剪。

| 层 | 内容 | 规模 | 频率 |
|---|---|---|---|
| 核心回归 | MATH-500 分层抽样 60 + AIME24 全 30 + OlymMATH ZH-EASY 30 | ~120 题 × k1 贪婪 | 每次配置变更 |
| 扰动回归 | GSM-Plus testmini 每类扰动抽 20（8 类 × 20=160）+ 对应种子题 20 | ~180 题 | 候选晋升门 |
| 中文/新鲜 | CMATH test 抽 60 + LiveMathBench 202412 `*_cn` 各子集抽 10 + AIME25 全 30 | ~130 题 | 双周/季度更新新鲜部分 |
| 极限拉伸 | OlymMATH ZH-HARD 20 + CNMO（可选） | ~30 题 | 月度，不进晋升门 |

判分与报告：双判分器并行（hendrycks 口径 + Math-Verify），逐题差集 = 表示
不一致清单；报告字段 = 正确数 + Wilson 95% CI + invalid 三分类计数
（💀 解析失败 / ⚠️ 金标在但未抽到 / ❕ 截断，MathArena 旗标语义）+ 平均/P95
调用、completion tokens、墙钟（沿用仓库既有口径）。

---

## 六、评测方法论采纳清单（纯评测侧）

1. **方差控制**：simple-evals 16 repeats、MathArena n=4、OlymMATH pass@1/cons@x
   先例 → 本仓库 k5 已具备；补正确数 Wilson CI 与"双轮独立 A/B"显著性检查
   （Error Bars 论文，摘要 ✅）。
2. **告警三分类**：MathArena 💀/⚠️/❕ → 本地与官方评测 trace 统一 invalid_reason
   枚举，报告并列（不得像 CMATH 那样剔除出分母）。
3. **判分器差异量化**：Math-Verify 重评 leaderboard（分数翻倍案例）→ 本地双
   判分器差集即"表示不一致"的直接量化。
4. **LLM judge 的正确位置**：Omni-MATH（98% 人工一致，需 100 题元集校准）、
   simple-evals（等价回退）、MathArena（judge agents + 消融）三方先例 → 本仓库
   只允许把 LLM judge 用作**双判分器差集的复核器**（抽查用），永不作主判分口径；
   本地无人工元集，须报告其与规则口径的一致率。
5. **污染防护**：LiveMathBench/MathArena 用截断后新题（结构性抗污染）+
   DeepSeek-Math 10-gram 自检（本地集扩充时）；GSM1k 证明固定题集分数含记忆。
6. **成本归一化**：MathArena 模型配置含 read/write cost 与 release date →
   实验报告保留 tokens/调用/墙钟并列，并为候选记录配置日期。

---

## 七、提交侧非答题工程做法（最终清单）

1. fail-closed：任何异常路径返回非空字符串 `final_response`（官方零分排查 +
   Minerva `[invalidanswer]` 双重依据）。
2. 答案表示纪律：答案句式 + `\boxed{}` 最简规范形（13 口径共识）。
3. 截断防护：lm-eval AIME/OlymMATH 都把 max_gen_toks 提到 32k——4096 预算下
   "答案优先输出"是关键缓解（已有 C0）。
4. invalid 与 model_error 分治重试（判分语义 vs 端点语义；仓库 P1 已有）。
5. trace 卫生 + JSON 可序列化 + 确定性（AGENTS.md 约束）。
6. 预算与并发：官方并发 3 → 共享端点实验串行；单题墙钟留 fail-closed 余量。
7. 分母纪律：invalid/超时/截断计入分母（CMATH 反例为鉴）。

---

## 八、行动路线（P0→P2，全部不触答题逻辑）

- **P0（可立即做）**：本地判分升级为 hendrycks 口径 + Math-Verify 双判分器；
  invalid_reason 三分类计数进 trace 与报告模板；报告加 Wilson CI。
- **P1（一周内）**：经 hf-mirror 拉取五件套数据集（MATH-500、AIME24/25、
  OlymMATH、CMATH、GSM-Plus），按 §5.4 抽样落盘为固定回归集（冻结哈希）；
  跑一次基线双判分器差集报告。
- **P2（按需）**：LiveMathBench/各期竞赛新鲜集季度轮换；GSM-Plus 扰动回归进
  候选晋升门；LLM-judge 差集复核小实验（预注册后进实验闭环）。
- 每项改动按 AGENTS.md 实验闭环登记（排除表、预注册、双轮 A/B），且**不自动
  修改默认路径**。

## 九、证据登记与最弱处

- 全部 13 个判分实现、12+ 基准、10+ 开源项目条目均有一手链接（见主笔记与两份
  缺口文件的来源表；本报告只列新增条目的来源）。
- **本次新增的最弱处**：
  1. MathArena final-answer 竞赛的自动判分具体实现未读源码（README 只标
     "Requires judging: No"）；其 💀/⚠️/❕ 旗标的精确触发条件也未读源码。
  2. Math-Verify 判分器间差异的 README 对比表未注明被评模型（引用时须说明）。
  3. LiveMathBench 论文（2412.13147）只核了题名与数据集文件清单，各子集题数、
     判分实现细节 ⚠️。
  4. simple-evals 的 `common.ANSWER_PATTERN` 正则细节未读（已知其为 "Answer:" 系）。
  5. AGIEval / GAOKAO-Bench 判分细节未核。
  6. huggingface.co 本机不通，Leaderboard v2 两条博文正文未逐字核对（出处经
     检索定位）；数据集经 hf-mirror 实测可达。
- 继承的最弱处：官方判分器黑盒（最大空白，见主笔记九-1）。

## 十、本次新增一手来源

| 来源 | 核对内容 |
|---|---|
| [openai/simple-evals math_eval.py](https://raw.githubusercontent.com/openai/simple-evals/main/math_eval.py) | Answer: 格式、LLM equality 回退、n_repeats=16、math_500 split |
| [lm-eval aime24.yaml](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/aime/aime24.yaml) + [aime_utils.py](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/aime/utils.py) | greedy/32k/until 配置；$..$→boxed 抽取；hendrycks 等价 |
| [eth-sri/matharena README](https://github.com/eth-sri/matharena) | n=4 默认重复、judge 配置（maj/norm 消融）、三旗标告警、成本/日期字段、2026 期竞赛 |
| [qtli/GSM-Plus README](https://github.com/qtli/GSM-Plus) | 5 视角 8 类扰动、10,552/2,400 规模、seed_* 字段 |
| [RUCAIBox/OlymMATH README](https://github.com/RUCAIBox/OlymMATH) | EN/ZH×EASY/HARD、Math-Verify 官方推荐、pass@1/cons@x、28 模型公开日志 |
| [QwenLM/ProcessBench](https://github.com/QwenLM/ProcessBench) | ACL 2025 过程错误定位（评测侧知识） |
| [arXiv:2605.00674](https://arxiv.org/abs/2605.00674) | MathArena 平台论文题名 |
| [arXiv:2402.19255](https://arxiv.org/abs/2402.19255) / [2412.13147](https://arxiv.org/abs/2412.13147) / [2503.21380](https://arxiv.org/abs/2503.21380) / [2412.06559](https://arxiv.org/abs/2412.06559) / [2407.08733](https://arxiv.org/abs/2407.08733) / [2406.19314](https://arxiv.org/abs/2406.19314) / [2304.06364](https://arxiv.org/abs/2304.06364) / [2310.16789](https://arxiv.org/abs/2310.16789) | GSM-Plus / LiveMathBench（Stable Reasoning）/ OlymMATH / ProcessBench / MathCheck / LiveBench / AGIEval / Min-K% 题名核对 |
| hf-mirror API 实测 | `HuggingFaceH4/MATH-500`、`Maxwell-Jia/AIME_2024`、`yentinglin/aime_2025`、`qintongli/GSM-Plus`、`RUC-AIBOX/OlymMATH`（含 EN/ZH×EASY/HARD+LEAN 文件）、`opencompass/LiveMathBench`（202412 全子集+202505）、`weitianwen/cmath` 全部可达；`huggingface.co` 本机直连不通 |
| [OpenLMLab/GAOKAO-Bench](https://api.github.com/repos/OpenLMLab/GAOKAO-Bench) | 仓库存在（判分细节 ⚠️） |
