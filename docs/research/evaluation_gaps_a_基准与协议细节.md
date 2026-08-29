# 评测缺口核对 A：基准与判分协议细节（2026-08-28）

状态：**只读网络调研**。未运行模型评测、未修改运行时代码、未编辑主笔记
[`math_agent_evaluation_methods_2026-08-28.md`](math_agent_evaluation_methods_2026-08-28.md)。
本文件只负责把主笔记"九、证据最弱处"中标记 ⚠️、且属于**基准与判分协议分工**的
缺口逐条升级为 ✅（或明确标注仍缺口）。证据标注约定沿用主笔记：

- **✅** = 本轮已核对原文/源码（下列核对均在本会话内以 arXiv HTML 全文、
  `raw.githubusercontent.com` 源码、GitHub API 完成）；
- **⚠️** = 仍未核对或论文未公开该细节，引用前需补核。

---

## 缺口 1：FrontierMath 每题程序化 checker 机制 → ✅

来源：arXiv:2411.04872 摘要页 + HTML 全文 v1 + Epoch AI 官方页（均本会话核对）。

**核对到的机制（原文引用）：**

- 每题随附验证脚本："Each submission included both a verification script for
  automated answer checking"。
- 答案被刻意设计为可程序化验证："definitive, computable answers that could be
  automatically verified"；"we often structured problems to have integer solutions,
  which are straightforward to check programmatically"；非整数值时答案表示为
  任意 SymPy 对象（符号表达式、矩阵等）。
- 判分实现两条路："A script then automatically verifies this answer by either
  checking for exact matches in the case of integers"，或 "using SymPy evaluation
  to check that the difference between the submitted answer and the actual answer
  simplifies to 0"。
- 防猜测设计："there should not be a greater than 1% chance of guessing the
  correct answer"。
- 评测协议：主结果为全基准单次评测；token 上限 "we set to 10,000 tokens"；
  触顶后追加 "a final prompt requesting an immediate final answer submission"，
  仍失败即记错；提交用标记注释 `# This is the final answer` 并以 pickle 保存、
  要求提交代码自包含。
- 明确代价（与证明题相关）："we cannot include problems that require mathematical
  proofs or formal reasoning steps, as these would demand human evaluation to
  assess correctness and clarity."
- 题目作者方的验证脚本有运行预算："must cumulatively run less than a minute on
  standard hardware"。

**补充事实（Epoch AI 官方页）：** 题目 "unpublished, highly challenging"，由专家
数学家出题并同行评审；页面注明 "On 2026-06-12, we released v2 which addressed
errors in 42% of problems"——即便这种重金打造的基准也有大面积题目错误修订，
引用其结论时需注意版本。

**来源：**
- https://arxiv.org/abs/2411.04872 （摘要：automated verification）
- https://arxiv.org/html/2411.04872v1 （全文机制细节）
- https://epoch.ai/frontiermath 、https://epoch.ai/frontiermath/tiers-1-4

---

## 缺口 2：Omni-MATH / CMATH / MathBench / OlympiadBench 判分方式 → ✅（CMATH、MathBench 各留一个子缺口）

### Omni-MATH（arXiv:2410.07985）→ ✅（HTML v3 全文核对）

- 主评测用 judge 模型而非规则："querying GPT-4o to determine whether the model
  solution is consistent with the reference answer"；可靠性用 100 题人工金标元集：
  "GPT-4o acquires a 98% accuracy with human annotations"。
- 开源判分模型 Omni-Judge：以 GPT-4o 评测结果构造训练数据（约 17618/2200/2200），
  默认底座 LLaMA-3.1-8b-Instruct；一致性 "over 91% consistency with GPT-4o and
  86% consistency with human judgments"——即仍有约 14% 与人工不一致。
- 规则法只覆盖部分答案形态：200 题抽样中 Number 95 / LaTeX 51 / Text 34 /
  Function 9 / Multi-LaTeX 8 / Tuple 2 / Multi-Function 1，
  "problems formatted in Number, LaTex and Tuple ... account for only 74% of the
  total"；规则子集 Omni-MATH-Rule 用 Qwen2.5-math rule evaluation 仓库
  （"primarily utilizing SymPy"）+ last_boxed 抽取，筛出 2821 题可规则评测、
  1607 题不可。
- 参考:  https://arxiv.org/html/2410.07985v3

### CMATH（arXiv:2306.16636）→ ✅ 身份与构成；⚠️ eval.py 内部逻辑

- **身份澄清（重要）**：DeepSeek-Math/模型报告引用的 CMATH 是
  "Can Your Language Model Pass Chinese Elementary School Math Test?"（小米，
  Wei et al. 2023），**小学**数学应用题集，**不是**高考级——DeepSeekMath 参考文献原句
  "Cmath: Can your language model pass chinese elementary school math test?, 2023"。
  arXiv API `ti:"CMATH"` 检索不存在"graduation-level"版本；此前笔记若按
  "高考/毕业级"理解需更正。
- 规模构成（HF 卡核对）：1.7k（数据页实计 1,698 行：validation 600 + test 1.1k），
  覆盖小学 1–6 年级各 100 题；字段 `grade / question / golden / reasoning_step /
  num_digits`，`golden` 为 1–8 字符短答案（数值型）；另有 60 题干扰信息鲁棒性子集
  （"we manually created a small 'distractor dataset' comprising 60 examples"）。
- 判分："We provide a script eval.py that implements automated evaluation."；
  eval.py 内部是否为纯 exact match ⚠️ 本轮未逐行核对（仓库
  https://github.com/XiaoMi/cmath ）。
- 来源：https://arxiv.org/abs/2306.16636 、
  https://huggingface.co/datasets/weitianwen/cmath

### MathBench（arXiv:2405.12209）→ ✅ 判分主口径；⚠️ 开放题匹配规则

- 规模：3709 题（MathBench-T 理论 2209 + MathBench-A 应用 1500），五阶段
  Arithmetic/Primary/Middle/High/College，双语。
- 题型：选择题 "typically with four options"，但部分子集为 Open-ended QA
  （GSM-X-CN、GSM-X-Plus、Arithmetic-HG）。
- 判分：Chat 模型用 **CircularEval**（N 选项题打乱选项测 N 次，
  "deeming a question correct only if all attempts are accurate"）；Base 模型用
  **PPL**；开放题用 few-shot CoT 评测，但**开放题答案匹配规则正文未给出** ⚠️。
- 来源：https://arxiv.org/abs/2405.12209 、https://arxiv.org/html/2405.12209v1

### OlympiadBench（arXiv:2402.14008）→ ✅（HTML v2 全文 + OpenBMB README）

- 规模与子集：8476 道奥赛级数学/物理题（含中国高考题），双语；开放题 6,728（79%）
  / 证明题（Theorem Proving）1,748（21%）；仓库文件名即子集命名
  （如 `OE_MM_physics_en_COMP.json`、`TP_TO_maths_zh_CEE.json`；OE=Open-ended，
  TP=Theorem proof，COMP=竞赛，CEE=高考）。
- 开放题自动判分（无 LLM judge）：答案先归为数值/符号两类："numeric values,
  handled through floating-point operations, and symbolic expressions"；数值
  "verified against a small tolerance of error, defaulting to 1e-8 but adjustable
  for physics problems"；符号 "use the SymPy library to confirm if the subtraction
  of two expressions approaches zero"；方程先移项、区间/元组逐元素比较。
- 证明题不自动判分："As no accurate automatic evaluation method for theorem
  proving exists"，仅人工抽样（如 GPT-4V 在 Math-Zh_COMP 抽 81 题仅对 6 题）。
- 判分器自身缺陷被论文承认：Limitations 写明判分 "makes logical judgments solely
  based on the two symbols or numerical expressions inputted"，附录列有
  "Incorrect Judging"（如 √(ab) 类等价式无法判定、精度设置致误判）。
- 来源：https://arxiv.org/html/2402.14008v2 、
  https://github.com/OpenBMB/OlympiadBench

---

## 缺口 3：MATH-500 子集是否出自 Let's Verify Step by Step（2305.20050）→ ✅

来源：arXiv:2305.20050（ar5iv HTML 全文本会话核对）。

- 出处确认，原文："we include data from 4.5K MATH test problems in the PRM800K
  training set, and we therefore evaluate our models only on the remaining 500
  MATH test problems."
- 抽样方式："We selected these 500 test problems uniformly at random."（附录 C）；
  难度/科目分布与完整 MATH test set 一致（Figure 5 直方图对比）。
- 该论文同时确认最终答案判分的不可靠性："correctness is determined solely by
  checking the final answer, a process which occasionally leads to misgraded
  solutions"——即官方自己承认存在误判样本。
- 关联工具侧事实：lm-evaluation-harness 的 minerva_math 任务组内含
  `minerva_math500` 子任务（任务 README 列出），说明 MATH-500 已成为
  可复现的标准评测口径。
- 来源：https://arxiv.org/abs/2305.20050 、
  https://ar5iv.labs.arxiv.org/html/2305.20050 、
  https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/minerva_math/README.md

---

## 缺口 4：Qwen2.5-Math 与 DeepSeekMath 评测节判分协议 → 部分 ✅（各留一个 ⚠️）

### Qwen2.5-Math（arXiv:2409.12122，HTML v1 全文核对）

- 已核对（✅）：
  - 基座模型全部 "few-shot chain-of-thought prompting"；指令模型零样本 CoT，
    "We report greedy, Maj@8, and RM@8 performance on all benchmarks in the
    zero-shot setting"（MMLU-STEM 除外为 5-shot）；
  - 竞赛题更大规模采样：AIME24 / AMC23 用 maj@64、rm@64、rm@256；
  - 强化学习奖励用规则验证器："The rule-based verifier extracts potential
    answers from each response and compares them against the gold-standard
    answer."，且 "The core implementation of our rule-based verifier is similar
    to the one used in our evaluation"（脚注指向 QwenLM/Qwen2-Math 仓库
    evaluation 目录）；
  - 附录评测案例的最终答案均呈 `\boxed{}` 形式；覆盖数据集含 Minerva Math、
    OlympiadBench、GaoKao（Math-QA/Math-Cloze）、CMATH、CN Middle School 24、
    CollegeMath、AIME 2024、AMC 2023 等。
- 仍未核对（⚠️）：HTML 正文**未明说**抽取是否以 boxed 为准、**未点名**
  等价判断工具（SymPy 及其归一化细节）。这两点需查
  https://github.com/QwenLM/Qwen2-Math 的 evaluation 源码，本轮未核对。

### DeepSeekMath（arXiv:2402.03300，HTML v1 全文核对）

- 已核对（✅）：
  - 基准清单：GSM8K、MATH、SAT、OCW、MMLU-STEM；中文 MGSM-zh、CMATH
    （引用即上文小学版）、Gaokao-MathCloze、Gaokao-MathQA；形式数学 miniF2F
    （Isabelle + Sledgehammer 补全）；
  - 工具题判分："The execution result of the program is evaluated as the
    answer."（PoT 以程序执行结果为答案）；
  - 采样口径：表注 "Scores in gray denote majority votes with 32 candidates;
    The others are Top1 scores."；摘要 "Self-consistency over 64 samples from
    DeepSeekMath 7B achieves 60.9% on MATH"；
  - 去污染："any text segment containing a 10-gram string that matches exactly
    with any sub-string from the evaluation benchmarks is removed"（覆盖 CMATH）。
- 仍未核对（⚠️）：CoT 文本答案的具体抽取正则与等价判断工具（是否 SymPy）
  正文未给出，需查其开源评测代码，本轮未核对。

- 来源：https://arxiv.org/html/2409.12122v1 、https://arxiv.org/html/2402.03300v1

---

## 缺口 5：OpenCompass 数学评测的判分实现 → ✅（源码通读）

来源：`opencompass/datasets/math.py`（main 分支，raw.githubusercontent.com 本会话
抓取通读）。

- **抽取两级**：
  - v1 `math_postprocess`：按 `.` 分句，优先取含 "final answer" 的句子，否则取
    第一句，再交给 `normalize_final_answer`；
  - v2 `math_postprocess_v2`：先 `extract_boxed_answer`（`last_boxed_only_string`
    用 `string.rfind('\\boxed')` 定位**最后一个** boxed，花括号计数配对取内层，
    兼容 `\fbox`），失败才回退 v1，回退时正则放宽为
    `re.search('final answer|answer is', ...)`。
- **归一化** `normalize_final_answer`：删单位词（square、dollars、cm 等）、剥
  `\text{}/\textbf{}/\overline{}`，按序抽取 `finalansweris(.*)`、`answer?is:?(.*)`、
  `oxed\{(.*?)\}`、`\$(.*?)\$`，修 TeX 简写（`frac`/`sqrt` 补花括号），去千分位逗号。
- **判分**：`MATHEvaluator.is_equiv` 为**规范化后的纯字符串相等**（无 SymPy）：
  双 None 判对；`_strip_string`/`_strip_string_v2` 清洗（去 `\left\right`、
  `^\circ`、空格，`tfrac/dfrac→frac`，`0.5→\frac{1}{2}`，整数 `a/b→\frac{a}{b}`）
  后比较；不等再各套 `normalize_final_answer` 比较；最终兜底裸串相等。
  即 OpenCompass 的 MATH 判分本质是"归一化 exact match"，不是 sympy 等价——
  修正主笔记"判分器只有三类"之外的一点：OpenCompass 属 hendrycks 口径的
  自有变体。
- 另有 judge 式抽取 `math_judement_preprocess`：`ANSWER_PATTERN =
  r'(?i)ANSWER\s*:\s*([^\n]+)'`。
- 来源：https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/math.py

---

## 缺口 6：hendrycks/math 原仓库 math_equivalence.py 真实路径 → ✅

- **路径定位（GitHub API 核对）**：仓库 `hendrycks/math` 的默认分支是
  `main`（不是 master）；`git/trees/HEAD?recursive=1` 列出文件
  `modeling/math_equivalence.py` 与 `modeling/math_equivalence_test.py`、
  `modeling/eval_math_gpt.py`。主会话根目录 404 的原因：文件不在根目录，
  而在 `modeling/` 子目录下。
- **源码通读（raw 抓取）**：`is_equiv(str1, str2)` 流程 = 双方 `_strip_string`
  归一化后**字符串相等**；归一化链条为：去换行、去 `\!`、`\\→\`、
  `tfrac/dfrac→frac`、去 `\left/\right`、去 `^{\circ}`/`^\circ`、去 `\$`、
  右侧单位（按 `\text{ ` 切分）、去 `\%`、` .`→` 0.`、`{.`→`{0.`、行首
  `.` 补 0、左侧 ≤2 字符的 `k =` 前缀剥离、`_fix_sqrt`（`\sqrt3→\sqrt{3}`）、
  去空格、`_fix_fracs`（`\frac1b→\frac{1}{b}`）、特判 `"0.5"→"\frac{1}{2}"`、
  `_fix_a_slash_b`（整分数 `a/b→\frac{a}{b}`）；任何异常回退裸串相等。
  **无 sympy、无数值容差**——1/√3 与 √3/3 这类 sympy 才能判等的写法会判错。
- 来源：
  https://api.github.com/repos/hendrycks/math （default_branch=main）、
  https://raw.githubusercontent.com/hendrycks/math/main/modeling/math_equivalence.py

---

## 对主笔记九、证据最弱处的逐条升级结论

| 主笔记编号 | 缺口 | 本轮结论 |
|---|---|---|
| 九-2 | FrontierMath checker | ✅ 升级（整数 exact match / SymPy 差值→0，双路脚本） |
| 九-2 | Omni-MATH 判分 | ✅ 升级（GPT-4o judge 为主 + Omni-Judge + 74% 规则子集） |
| 九-2 | CMATH 判分 | ✅ 身份与构成；⚠️ eval.py 内部逻辑仍未逐行 |
| 九-2 | MathBench 判分 | ✅ CircularEval/PPL；⚠️ 开放题匹配规则论文未公开 |
| 九-2 | OlympiadBench 判分 | ✅ 升级（数值容差 1e-8 + SymPy 差值；证明题不自动判） |
| 九-2 | Qwen/DeepSeekMath 协议 | 部分 ✅（verifier 引文、采样口径）；⚠️ boxed/SymPy 细节需查两家的 GitHub 评测代码 |
| 九-4 | math_equivalence.py 真实路径 | ✅ 升级（`modeling/math_equivalence.py`，分支 main） |
| （新增） | OpenCompass 判分实现 | ✅ 升级（归一化 exact match，无 sympy） |
| （不变） | 官方判分器实现 | 仍未知，维持主笔记九-1 的最大空白结论 |

## 一手来源表

| 来源 | 关键内容/对本仓库的意义 |
|---|---|
| [arXiv:2411.04872](https://arxiv.org/abs/2411.04872) / [HTML v1](https://arxiv.org/html/2411.04872v1) | FrontierMath checker 双路实现与 guessproof 设计；"答案可程序化验证"是官方判分的正面样板 |
| [Epoch AI FrontierMath](https://epoch.ai/frontiermath) | 官方页；v2 修订 42% 题目错误——基准可靠性风险实例 |
| [arXiv:2410.07985 HTML](https://arxiv.org/html/2410.07985v3) | Omni-MATH：GPT-4o judge（98% 人工一致）+ Omni-Judge（86% 人工一致）+ 74% 规则可测；证明奥赛题规则抽取覆盖率有限 |
| [arXiv:2306.16636](https://arxiv.org/abs/2306.16636) / [HF 卡](https://huggingface.co/datasets/weitianwen/cmath) | CMATH 实为小学数学 1.7k 题；纠正"高考级"误记 |
| [arXiv:2405.12209 HTML](https://arxiv.org/html/2405.12209v1) | MathBench：3709 题、CircularEval/PPL 判分；选择题判分比单次 ACC 更严 |
| [arXiv:2402.14008 HTML](https://arxiv.org/html/2402.14008v2) / [OpenBMB README](https://github.com/OpenBMB/OlympiadBench) | OlympiadBench：1e-8 容差 + SymPy 差值判等；证明题无自动判分；判分器自认 Incorrect Judging |
| [arXiv:2305.20050](https://arxiv.org/abs/2305.20050) / [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.20050) | MATH-500 出处（PRM800K 训练占用 4.5K，余 500 随机保留）；官方自认最终答案判分偶有误判 |
| [arXiv:2409.12122 HTML](https://arxiv.org/html/2409.12122v1) | Qwen2.5-Math：零样本 CoT + Maj@8/RM@8（竞赛 maj@64/rm@256）；规则验证器抽取+比对 |
| [arXiv:2402.03300 HTML](https://arxiv.org/html/2402.03300v1) | DeepSeekMath：PoT 以执行结果为答案、maj@32 注记、SC@64、10-gram 去污染 |
| [OpenCompass math.py](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/math.py) | last-boxed 抽取 + 归一化 exact match（无 sympy）；国产栈判分口径实证 |
| [hendrycks/math modeling/math_equivalence.py](https://raw.githubusercontent.com/hendrycks/math/main/modeling/math_equivalence.py) + [repo API](https://api.github.com/repos/hendrycks/math) | 原版等价判断真身：纯字符串归一化相等；路径在 modeling/ 子目录、分支 main |
| [lm-eval minerva_math README](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/tasks/minerva_math/README.md) | minerva_math500 任务存在；"sympy 等价由 lm-eval 实现而非原 MATH 仓库"的移植关系

---

## 第二轮核对（源码级）

状态：只读网络调研第二轮（2026-08-28）。目标 = 把第一轮遗留的四个 ⚠️ 核到
源码级：Qwen2-Math 评测源码、DeepSeekMath 评测源码、CMATH eval.py、MathBench
开放题匹配。方法：GitHub API 确认仓库与默认分支 → `git/trees` 定位评测文件 →
`raw.githubusercontent.com` 抓取通读。源码存档于 `tmp/research_verify/`
（文件名前缀 `r2_`）。

### 仓库 1：QwenLM/Qwen2-Math 评测源码 → ✅

- **仓库定位**（GitHub API 本会话核对）：`QwenLM/Qwen2-Math` 已 301 永久重定向到
  [`QwenLM/Qwen2.5-Math`](https://api.github.com/repositories/839750798)
  （默认分支 `main`）。Qwen2.5-Math 论文（2409.12122）脚注所指 "QwenLM/Qwen2-Math
  仓库 evaluation 目录" 即该仓库的
  [`evaluation/`](https://github.com/QwenLM/Qwen2.5-Math/tree/main/evaluation)
  目录（`grader.py / parser.py / evaluate.py / math_eval.py / utils.py /
  rm_maj_eval.py / latex2sympy/` 等）。
- **系谱（✅ 文件头自述）**：`evaluation/README.md` 自认 "The codebase is
  adapted from [math-evaluation-harness](https://github.com/ZubinGou/math-evaluation-harness)"；
  [`grader.py`](https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/grader.py)
  文件头注释写明 "This logic is largely copied from the Hendrycks' MATH release
  (math_equivalence), and borrowed from: ProphetNet/CRITIC、openai/prm800k、
  microsoft/ToRA `src/eval/grader.py`、deepseek-ai/DeepSeek-Math
  `evaluation/eval/eval_utils.py`"。**与 EleutherAI lm-evaluation-harness 无
  直接实现关系**——是自建评测 harness（ToRA 系谱）+ hendrycks 归一化血统。
- **抽取正则（✅ 通读 `parser.py` `extract_answer`）**：优先级链 =
  ①多选题清洗（mmlu_stem/sat_math/aqua/gaokao2023）；②Minerva 句式
  `final answer is $...$. I hope`；③**`"boxed" in pred_str` 时取最后一个
  boxed**：`pred_str.split("boxed")[-1]` 后花括号计数栈取内层（兼容
  `\boxed5` 无花括号形态——取到 `$` 为止）；④`he answer is`（即 "The answer
  is" 的宽匹配）/`final answer is` 句式；⑤中文 `答案是`；⑥**兜底：取全文
  最后一个数字**（去逗号后正则 `-?\d*\.?\d+` 取末位，`use_last_number=True`
  默认开）。即"以 boxed 为准"，但无 boxed 也不会空手——文本尾数字会被抓出。
- **归一化（✅ 通读 `parser.py` `strip_string`）**：hendrycks `strip_string`
  的超集——保留原版步骤（去 `\left/\right`、`^\circ`、`\%`，`tfrac/dfrac→frac`，
  `\sqrt3→\sqrt{3}`、`\frac12→\frac{1}{2}`、整数 `a/b→\frac{a}{b}`、左项 ≤2
  字符的 `k=` 前缀剥离）之外新增：`array/bmatrix→pmatrix`、`\neq\leq\geq`
  规范化、约 130 项 MathQA 系单位词表（正则边界删除，含复数形态）、
  `\text{...}`→内容、`x=/y=/z=` 前缀、`\emptyset`→`{}`、
  `(-\infty,\infty)`→`\mathbb{R}`、word2number（"two"→"2"）、`inf`→`\infty`、
  删 "and"、`j`→`i`、`x.000` 尾零。**没有 hendrycks 的 0.5→1/2 特判**（数值
  等价交给 math_equal 的浮点容差）。
- **等价判断（✅ 通读 `grader.py` `math_equal`；`evaluate.py` 以 pebble 进程池
  逐条调用，`timeout=3` 秒，超时/异常一律记 False——fail-closed）**：多级
  级联 = ①小写去空格字符串相等 → ②A–E 选项清洗比对 → ③数值：`parse_digits`
  （去逗号、`%`→/100）后 `isclose(rel_tol=1e-4)`，且 `include_percentage=True`
  时金标生成 `[ref/100, ref, ref*100]` 三个候选（**百分比三向等价**）→
  ④剥 `[](){}` 后小写字符串相等 → ⑤区间/元组逐元素递归、pmatrix 逐元素递归 →
  ⑥方程：双边各恰一个 `=` → `symbolic_equal(lhs-rhs)`；单边 `=` 且左项 ≤2 字符
  → 取右侧比 → ⑦**SymPy 符号等价 `symbolic_equal`**：三个解析器依次尝试
  （sympy `parse_latex` → `parse_expr` → **latex2sympy2 `latex2sympy`**），
  比较路径 = 直接相等 → `a.equals(b)` 或 `simplify(a-b)==0` → 方程
  |lhs−rhs| 相等 → 数值兜底 `float(N(a))` vs `float(N(b))`（rel_tol 1e-4）→
  矩阵逐元素 round(3) 相等；可选 multiprocessing 1 秒超时（超时 False）。
- **双判分实现并存但主链只用一套**：`math_utils.py` 另有一套 sympy 实现
  `compare_ans`（`clean_expr_str` 重归一化 + `parse_latex` + `.equals`，
  `timeout_decorator` 5 秒；`^\circ`→`\times \pi / 180` 度转弧度；预测解析
  失败回退"取最后一个数字"再比）——但本会话对 `evaluation/` 全部 py 文件
  grep 证实**没有任何文件 import `math_utils`**，正式判分路径就是
  `grader.math_equal`。
- **投票口径（✅ 通读 `rm_maj_eval.py`）**：maj@k = `strip_string` 后
  `Counter` 取众数；rm@k = 以 `math_equal_timeout`（5 秒超时）为等价谓词对
  预测聚类取组。与论文 maj@64 / rm@256 口径一致。
- **Prompt 侧 boxed 纪律（✅ 通读 `utils.py` `PROMPT_TEMPLATES`）**：
  Qwen2-Math-Instruct 用 `qwen-boxed`，Qwen2.5-Math-Instruct 用
  `qwen25-math-cot`，系统提示均含 "Please reason step by step, and put your
  final answer within `\boxed{}`."——与缺口 4 论文侧"附录案例答案呈 boxed 形态"
  相互印证。
- **范式归类：解析 + 符号等价族**（数值 rel_tol 1e-4 + SymPy/latex2sympy2 符号
  等价），带 hendrycks 式归一化前置与字符串级联短路；比 lm-eval `minerva_math`
  宽（多 latex2sympy2、百分比三向、区间/矩阵逐元素、方程移项），比 Math-Verify
  少不等式翻转/解集语义处理。
- 来源：
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/grader.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/parser.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/evaluate.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/utils.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/rm_maj_eval.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/math_utils.py 、
  https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/README.md

### 仓库 2：DeepSeekMath 评测源码（deepseek-ai/DeepSeek-Math）→ ✅

- **仓库定位**（GitHub API 本会话核对）：仓库名确认为
  [`deepseek-ai/DeepSeek-Math`](https://api.github.com/repos/deepseek-ai/DeepSeek-Math)
  （`deepseek-ai/DeepSeekMath` 不存在，404），默认分支 `main`。评测代码在
  `evaluation/`：抽取在
  [`data_processing/answer_extraction.py`](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/data_processing/answer_extraction.py)，
  判分在
  [`eval/eval_utils.py`](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_utils.py)
  与
  [`eval/eval_script.py`](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_script.py)。
- **Prompt 侧 boxed 纪律（✅ evaluation/README.md）**：CoT 与 TIR 两种 prompt
  均强制 "Please reason step by step, and put your final answer within
  `\boxed{}`."（中文版："请通过逐步推理来解答问题，并把最终答案放置于
  `\boxed{}` 中。"）。
- **抽取（✅ 通读 `answer_extraction.py`）**：CoT 主链 `extract_answer` 优先级
  链 = ①Minerva 句式 `final answer is $...$. I hope`；②**`extract_boxed_answers`**：
  按 `'boxed{'` 切分 + 花括号计数，返回**全部** boxed 内容列表（闭括号后跟
  `%` 时把 `%` 一并收进）；`exhaust=False` 时取列表**最后一个**；③`he answer is`
  句式；④回退 `extract_program_output`（最后一个 ` ```output ` 代码块，TIR 用）；
  ⑤回退"全文本最后一个数字"（`-?\d*\.?\d+`）。之后首行截取、剥 `:`/`.`/`/`、
  `strip_string`。另有按数据集的专用抽取：GSM8K=最后数字（无则 `[invalid]`）；
  **CMATH 专用 `extract_cmath_few_shot_test`**：`问题：` 前截断 → `答案是` 后
  首行 → 剥全角冒号/句号 → **取其中最后一个数字**（正则 `-?\d+\.?\d*`），
  失败即 `[invalid]`；Gaokao-MathCloze：`答案是` 后首行；miniF2F：整段 Isabelle
  输出。
- **归一化（✅ `answer_extraction.py` `strip_string`）**：hendrycks 血统但自成
  变体——有 `tfrac/dfrac/cfrac→frac`、去 `\left\right`、`^\circ`、`\$`/`$`、
  `x\in`、`\cdot`、`\mathrm`/`\mathbf`、`\mbox{...}`、`inf→\infty`、`j→i`、
  `x.000` 尾零、`.→0.`、`_fix_sqrt`（`\sqrt2` 补花括号，比 hendrycks 多支持负号/
  字母）、**`_fix_tan`**（`\tan2→\tan{2}`，hendrycks 没有）、`_fix_fracs`、
  `_fix_a_slash_b`、结尾 `\\`/`,`/`.` 清除、`{cm}/{mm}` 单位上标删除；**与
  hendrycks 不同：`%` 保留不删（仅 `\%`→`%`）、`k=` 前缀剥离被注释掉、无
  `0.5→1/2` 特判、无 MathQA 大词表**。
- **判分（✅ 通读 `eval_script.py` `is_correct` + `eval_utils.py` `math_equal`）**：
  三级或 = ①`abs(float(pred) − float(ans)) < prec=1e-3`（**绝对容差**，去逗号）；
  ②裸字符串相等；③`math_equal(pred, ans)`。`math_equal`（ToRA/Qwen 同源前身的
  **更简版本**）= 字符串相等 → 数值 `isclose(abs_tol=1e-3)` + 金标
  `[ref/100, ref, ref*100]` 百分比三向 → 区间/矩阵逐元素递归 → 方程移项
  （双边 `=` → `symbolic_equal(lhs−rhs)`；左项 ≤2 字符取右侧）→ **SymPy
  `symbolic_equal`：仅 `parse_latex/parse_expr` 两解析器（无 latex2sympy），
  `simplify(a−b)==0` 或 `isclose(N(a), N(b), abs_tol=1e-3)`**；无 `.equals`、
  无矩阵 round 路径。主链调用**不带 timeout**（`call_with_timeout` 存在但
  `timeout=False` 默认关）。解析失败即 False（fail-closed）。
- **多答案/无序集合语义（对主笔记"集合归一化"主题是直接同向证据）**：
  - 预测与金标均为 list 时做**双列全匹配**（每个预测都必须配到互异金标，
    `is_correct` 递归二部匹配）——MATH 多答案题按无序集合判；
  - `eval_math` 对 MATH 预测**只取最后 `len(ans)` 个 boxed**（注释自述
    "some predictions mistakenly box non-answer strings"）；
  - 双方含 `\cup` 时按 `\cup` 拆分成列表再匹配——解集的并集形态有专门处理；
  - `extract_math_answer`：题干含 "separated by commas" 且答案无括号时按逗号
    拆分，`\text{ and }` 也拆分——多答案题的题干感知拆分。
- **其余口径**：SAT/MMLU-STEM/Gaokao-MathQA 纯选项字母比对（后者取文本中
  **最后出现的** A–D 字母）；OCW 用 Minerva 式 `[invalidanswer]` + AGIEval
  `SymbolicMathMixin.is_tex_equiv`（数值/方程/表达式三分类）；miniF2F 自动
  判分恒 True（形式证明由 Isabelle 流程另行处理）。
- **范式归类：解析 + 符号等价族**（abs 1e-3 数值容差 + SymPy simplify 等差），
  等价实现是 Qwen grader 的直系前身（Qwen grader.py 文件头明确借用本文件），
  比 Qwen 版更简（无 latex2sympy、无 `.equals`、无选项清洗）。
- 来源：
  https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/data_processing/answer_extraction.py 、
  https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_utils.py 、
  https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_script.py 、
  https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/README.md

### 仓库 3：CMATH `eval.py` 内部逻辑（XiaoMi/cmath）→ ✅

- **仓库定位**（GitHub API 本会话核对）：
  [`XiaoMi/cmath`](https://api.github.com/repos/XiaoMi/cmath)（默认分支 `main`），
  判分仅两个文件：根目录
  [`eval.py`](https://raw.githubusercontent.com/XiaoMi/cmath/main/eval.py) +
  [`utils.py`](https://raw.githubusercontent.com/XiaoMi/cmath/main/utils.py)。
- **判分主流程（✅ 通读 `eval.py`）**：`hit / (样本数 − err)` 三计数器——
  `hit`（某候选与金标匹配）、`err`（模型回复判为异常）、`warn`（未能提取出
  数字）。**关键细节：异常回复（超时/报错字符串）从分母中剔除**（
  `valid = sample_size - err`），而"提取失败"只 warn 仍算错。
- **抽取（✅ 通读 `utils.py`）**：**完全不感知 `\boxed{}`**，是"位置正则
  抽数字"方案：按行用四个位置正则收集数字候选（行首/行中/行尾/整行仅一个数，
  两侧以中文字符或中文标点/`=`/`≈`/`℃` 等定界），`\frac{a}{b}`→`a/b`，中文
  分数"五分之三"→`3/5`，千分位逗号/空格删除；**默认截断 `truncation="t"`：
  只保留全回复最末 2 个数字候选**（另有 h/ht/None 选项）。
- **等价判断（✅）**：**不是纯 exact match，是数值容差匹配**——
  `string2num`（`%`→/100，`a/b`→除法，整数/浮点）后 `match_digits`：
  整数↔整数精确相等；其余 **相对差 `|a−b| / (min(|a|,|b|)+1e-6) < 1e-2`**
  （1% 相对容差）。无 SymPy、无字符串归一化（只有数字清洗）、无 LLM judge。
  金标 `golden` 为 1–8 字符短数值（与第一轮 HF 卡核对一致）。
- **异常判定 `has_exception`**：空回复；`请求.*超时|timeout`；含花括号且命中
  `error|异常|失败|content_filter`。命中即返回 `["ERROR"]` 且直接不参与 hit、
  不进分母。
- **范式归类：数值抽取 + 容差匹配**（主笔记三范式之外的第 4 小类：短数值
  基准的"抽数字+容差"路线，同族参照 OlympiadBench 数值 1e-8 容差、Minerva
  数值路径）。
- **对本仓库的意义**：抽取层面它比 hendrycks/minerva 更脆弱依赖标点边界
  （数字必须紧邻中文标点/行界才被抓到），答案写在英文标点或孤立括号里有漏抽
  风险；1% 容差意味着"四舍五入到两位小数"级别的表示差异不影响得分。
- 来源：
  https://raw.githubusercontent.com/XiaoMi/cmath/main/eval.py 、
  https://raw.githubusercontent.com/XiaoMi/cmath/main/utils.py

### 仓库 4：MathBench 开放题匹配规则 → ✅（评测代码在 OpenCompass 侧）

- **仓库定位（本会话 GitHub API 核对）**：MathBench 官方仓库是
  [`open-compass/MathBench`](https://api.github.com/repos/open-compass/MathBench)
  （ACL 2024 Findings；任务原设想的 "OpenBMB/MathBench" 不存在，OpenBMB 组织下
  放的是 OlympiadBench）。**该仓库只含数据集（`datasets/`）与文档，没有任何
  评测代码**（`git/trees` 全量核对）；README 亦无评测入口。评测实现在同组织
  OpenCompass 主库：
  - 数据集与后处理
    [`opencompass/datasets/mathbench.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/mathbench.py)；
  - Circular 评估器
    [`opencompass/openicl/icl_evaluator/icl_circular_evaluator.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_circular_evaluator.py)；
  - AccEvaluator 定义在
    [`opencompass/openicl/icl_evaluator/icl_hf_evaluator.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_hf_evaluator.py)
    （第 101 行，经包 `__init__` 的 `import *` 导出；路径名有迷惑性）；
  - 配置
    [`mathbench_2024_gen_1dc21d.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/configs/datasets/MathBench/mathbench_2024_gen_1dc21d.py)
    与
    [`mathbench_prompt.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/configs/datasets/MathBench/mathbench_prompt.py)。
- **配置层路由（✅ 通读现行与 deprecated 两代配置）**：`single_choice` 子集 →
  `first_option_postprocess`（30+ 条中英文选项抽取模式 + cushion 兜底）+
  `CircularEvaluator`（wocircular 配置改用 PPL）；**非选择题（cloze）子集 →
  `mathbench_postprocess` + `AccEvaluator`**。现行 `mathbench_sets` 的开放题
  子集 = `primary: [cloze_cn, cloze_en]` + `arithmetic: [cloze_en]`（paper
  所称 GSM-X 类应用开放题即对应 `cloze_*` 命名走同一管道）。
- **开放题抽取规则（✅ 通读 `mathbench_postprocess`）**：中文子集按 `答案是`
  切分、英文按 `The answer is` 切分；切分成功 → 触发句之后取**第一个**数字；
  无触发句 → 取全文**最后一个**数字（正则 `-?\d*\.?/?\d+|\d+`，支持小数与
  `3/4` 形式分数）；抽取前仅删千分位分隔符（数字间逗号/空格）；**抓不到数字
  时返回原始文本**；**完全不感知 `\boxed{}`、无 hendrycks 式归一化、无
  sympy、无容差**。
- **开放题判分（✅ 通读 `AccEvaluator`）**：把后处理后的预测串与金标串映射为
  类别 ID（字典键 = `set(map(str, references))`，金标集合外的串自成分类、永不
  匹配）后用 huggingface `evaluate` 的 `accuracy` 计算——**等价于精确字符串
  匹配**。即 MathBench 开放题 = "触发句定位数字 + 精确串匹配"，连 hendrycks
  的 `0.5↔1/2` 特判、`\frac/\sqrt/^\circ` 清洗都没有——**是所有已核对判分器
  中归一化最窄的一个**。
- **CircularEval 实现细节（补充 ✅）**：数据侧 `get_circular_example` 生成
  ABCD/BCDA/CDAB/DABC 四个循环位移（选项轮转、答案字母重映射，reference 编码
  为 `id--字母--模式`）；`CircularEvaluator.score` 产出 `acc_4`（逐次准确率）、
  **`perf_4`（4 轮全对才算对 = more_4_4）**、`more_4_j`（≥j 轮对）、`vote_4`
  （众数投票）、`prior_A/B/C/D/-`（选项先验频率诊断）。新版
  `MathBenchCircularEvaluator`（同文件）增加 boxed 路径：`\boxed{...}` 内容与
  选项**全文精确相等**才映射为选项字母，否则走 `first_option_postprocess`。
- **范式归类：归一化字符串相等族（极窄变体）**——选择题侧归一化 = 选项字母
  抽取；开放题侧归一化 ≈ 仅删千分位 + 触发句定位。
- **对本仓库的意义**：MathBench 开放题口径是"最简规范形比看起来正确更本质"的
  极端反例印证——`0.5` 与 `\frac{1}{2}` 在此口径下互不等价（无任何数值/符号
  等价机制），而逗号千分位反而会被删掉；输出"答案句 + 裸数字"比"boxed 表达式"
  更符合该判分器的抓取假设。
- 来源：
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/mathbench.py 、
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_circular_evaluator.py 、
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_hf_evaluator.py 、
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/configs/datasets/MathBench/mathbench_2024_gen_1dc21d.py 、
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/configs/datasets/MathBench/mathbench_prompt.py 、
  https://raw.githubusercontent.com/open-compass/OpenCompass/main/docs/en/advanced_guides/circular_eval.md

---

## 第二轮归纳：四仓库判分范式与升级结论

| 仓库 | 判分核心 | 范式归类（主笔记三范式） |
|---|---|---|
| Qwen2.5-Math（原 Qwen2-Math） | `math_equal`：数值 rel_tol=1e-4（含百分比三向）+ SymPy/latex2sympy2 符号等价，pebble 3s 超时 fail-closed | 解析 + 符号等价族（hendrycks 归一化前置 + 字符串级联短路） |
| DeepSeek-Math | `is_correct`：浮点差 abs<1e-3 / 裸串相等 / `math_equal`（SymPy simplify 等差，abs_tol=1e-3）；多答案双列全匹配、`\cup` 拆分 | 解析 + 符号等价族（Qwen 版的直系前身，实现更简） |
| CMATH | 位置正则抽数字（默认末 2 候选）+ 相对差 <1e-2；异常回复剔除出分母 | 数值抽取 + 容差匹配（三范式外的第 4 小类） |
| MathBench 开放题 | `mathbench_postprocess`（触发句定位数字，无则全文末数字）+ `AccEvaluator` 精确串匹配 | 归一化字符串相等族（极窄：无 boxed 感知、无符号等价、无容差） |

对主笔记"九、证据最弱处"的更新：

| 主笔记编号 | 缺口 | 第二轮结论 |
|---|---|---|
| 九-2 | Qwen2-Math 抽取正则与等价工具 | ✅ 升级（last-boxed 栈抽取 + `math_equal` SymPy/latex2sympy2；仓库已改名 Qwen2.5-Math） |
| 九-2 | DeepSeekMath CoT 抽取与等价工具 | ✅ 升级（`answer_extraction.py` 全 boxed 列表 + 末位兜底；`eval_utils.math_equal` SymPy；`eval_script.is_correct` abs 1e-3） |
| 九-2 | CMATH eval.py 是否纯 exact match | ✅ 升级（**非** exact match：1e-2 相对容差数值匹配；异常回复剔除出分母） |
| 九-2 | MathBench 开放题匹配规则 | ✅ 升级（触发句数字抽取 + AccEvaluator 精确串匹配；评测代码在 OpenCompass 而非 MathBench 仓库） |
| （新增） | 判分器共识表示清单 | 扩至 9 个实现：原 5 个 + Qwen2.5-Math、DeepSeek-Math、CMATH、MathBench 开放题；"boxed + 最简规范形"在全部 9 个口径下安全 |
| （不变） | 官方判分器实现 | 仍未知，维持主笔记九-1 最大空白结论 |

## 第二轮一手来源表

| 来源 | 核对内容 |
|---|---|
| [QwenLM/Qwen2.5-Math grader.py](https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/grader.py) / [parser.py](https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/parser.py) / [evaluate.py](https://raw.githubusercontent.com/QwenLM/Qwen2.5-Math/main/evaluation/evaluate.py) | `math_equal` 级联等价、last-boxed 栈抽取、pebble 3s 超时 |
| [deepseek-ai/DeepSeek-Math answer_extraction.py](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/data_processing/answer_extraction.py) / [eval_utils.py](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_utils.py) / [eval_script.py](https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Math/main/evaluation/eval/eval_script.py) | 全 boxed 抽取链、`math_equal`（abs 1e-3）、多答案双列匹配、`\cup` 拆分 |
| [XiaoMi/cmath eval.py](https://raw.githubusercontent.com/XiaoMi/cmath/main/eval.py) / [utils.py](https://raw.githubusercontent.com/XiaoMi/cmath/main/utils.py) | 位置正则抽数字 + 1e-2 相对容差；异常剔除出分母 |
| [OpenCompass mathbench.py](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/mathbench.py) / [icl_circular_evaluator.py](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_circular_evaluator.py) / [icl_hf_evaluator.py](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_hf_evaluator.py) | `mathbench_postprocess` + AccEvaluator 精确串匹配；CircularEval 四位移与 perf_4 |
| [open-compass/MathBench](https://api.github.com/repos/open-compass/MathBench) / [api.github.com/repositories/839750798](https://api.github.com/repositories/839750798) / [api.github.com/repos/deepseek-ai/DeepSeek-Math](https://api.github.com/repos/deepseek-ai/DeepSeek-Math) / [api.github.com/repos/XiaoMi/cmath](https://api.github.com/repos/XiaoMi/cmath) | 仓库存在性、默认分支、改名/404 事实（Qwen2-Math→Qwen2.5-Math；DeepSeekMath 404；OpenBMB/MathBench 404） |

第二轮遗留 ⚠️（均为低优先）：
- Qwen `math_utils.py` 的 `compare_ans`（第二套 sympy 实现）在评测目录内无调用方
  （已 grep 全部 py 文件证实），其历史用途（是否曾用于 TIR 路径）未深究；
- DeepSeek-Math OCW 的 `SymbolicMathMixin.is_tex_equiv`（AGIEval 系）未逐行
  核对（仅核对调用分类逻辑，非主流基准口径）；
- MathBench 论文期（2024-05）与现行 OpenCompass main 的配置存在代际差（deprecated
  vs 现行），本轮按"现行 main + deprecated 配置同构"归类，未逐 tag 复考古版。
