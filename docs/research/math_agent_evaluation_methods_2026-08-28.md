# 数学推理 Agent 评测方法学与"非答题能力"方案研究（2026-08-28）

状态：**只读调研**。本次未运行任何模型评测、未修改运行时代码、未把外部结果当成本仓库
收益。应需求方要求，本笔记**刻意排除**"提升答题/推理能力"的方法（CoT 变体、自洽、
验证器等，见 [2026-08-27 能力研究](math_agent_capability_methods_2026-08-27.md)），只覆盖
评测方法学与不涉及答题能力的方案。

证据标注约定：
- **✅** = 本会话已核对原文/源码（arXiv 题名页经 arXiv API 核对；判分器源码经
  `raw.githubusercontent.com` 抓取并通读，存档于 `tmp/research_verify/`）；
- **⚠️** = 凭既有记忆未在本次核对，引用前需补核；
- 赛事官方飞书文档 https://aicarrier.feishu.cn/wiki/L90FwD9gJiqdg0k33RCcHTdcnrb
  经匿名抓取测试会 302 跳登录页，**无法匿名访问**，其判分细节本笔记不引用。
- 2026-08-28 缺口核对：[A：基准与协议细节](evaluation_gaps_a_基准与协议细节.md)
  两轮共把本笔记全部基准/协议 ⚠️ 升级为 ✅——9 个判分实现源码级覆盖
  （hendrycks 原版、OpenCompass、Qwen2.5-Math、DeepSeek-Math、CMATH、MathBench
  开放题、两个 lm-eval 任务、Math-Verify），正文与"九、证据最弱处"已同步；
  [B：鲁棒性与争议细节](evaluation_gaps_b_鲁棒性与争议细节.md) 已核对完成（其 §5
  出处经检索定位，正文因本机网络不通未逐字核对）。

## 结论先行

1. **官方判分器对提交者黑盒，但业界判分器实现可归为三种主范式 + 一个短数值
   小类**：归一化字符串相等族（hendrycks 原版、OpenCompass、MathBench 开放题，
   均 ✅ 源码通读：无 sympy 或归一化极窄）、解析 + 符号等价族（Minerva 口径、
   Math-Verify、Qwen2.5-Math、DeepSeek-Math，均 ✅ 源码通读）、LLM judge 族
   （Omni-MATH 的 GPT-4o judge / Omni-Judge，需人工元集校准）、"抽数字 + 容差"
   小类（CMATH 相对容差 1e-2，✅ 源码）。**已源码级覆盖 9 个判分实现，
   `\boxed{}` + 最简规范形在全部 9 个口径下均安全。**同一批模型输出在不同
   判分器下得分可差 5 个点以上，Math-Verify 自述极端低估可达 40 点
   （✅，其 README 对比表）。
2. 因此本仓库"输出/抽取卫生"路线不是工程洁癖，而是**判分对齐问题**：官方判分器
   不可见时，唯一稳健策略是让 `final_response` 落在**所有已知判分器共识的
   "高召回区"**——`\boxed{}` 包裹 + 竞赛规范最简形。这与 AGENTS.md 的"普适性优先"
   完全兼容：这是对"任意表示不一致"的类生效，不绑定题号。
3. **不能也不应"放宽等价判断去迎合判分器"**：等价判断在官方侧，本地改不了；
   本地能改的只有输出侧表示。本地判分工具反而可以升级（如引入 Math-Verify 作为
   本地回归判分器），以减少本地判分与官方判分的系统性偏差。
4. **LLM-as-judge 判数学不可靠有专文证据**（✅ MT-Bench 论文记录位置/冗长/
   自增强偏差），本仓库本地判分不应引入 LLM 判分；process/PRM 评测组件
   （PRM800K、MATH-Shepherd、PRMBench）属评测侧知识，**不引入运行时**。
5. 非答题维度里对本仓库最有行动价值的四件套：**invalid/零分治理**（判分器源码
   直接证明缺句式/缺 boxed 即 invalid）、**成本归一化报告**（调用/token/墙钟与
   正确数并列，本仓库已有口径）、**评测方差意识**（112 题单轮差异不显著，
   支持"双轮独立 A/B"预注册）、**扰动鲁棒性自测**（题面/格式扰动，不用隐藏题）。

## 一、主流数学基准与判分口径

| 基准 | 答案形式 | 判分方式 | 核对状态 |
|---|---|---|---|
| GSM8K ([2110.14168](https://arxiv.org/abs/2110.14168)) | 短文本数值 | 答案经 `####` 分隔后精确匹配 | ✅ 题名核对 |
| MATH ([2103.03874](https://arxiv.org/abs/2103.03874)) | LaTeX 表达式 | 最后一个 `\boxed{}` + `math_equivalence` 归一化后字符串相等（见 §2.1） | ✅ 题名核对；判分细节 ✅ 源码 |
| MATH-500（出自 [2305.20050](https://arxiv.org/abs/2305.20050)） | 同 MATH | 同 MATH；论文自认"仅查最终答案，偶致误判" | ✅ 出处与原句（缺口 A） |
| AIME（AIME24/25 口径，Qwen2.5-Math/o1 常用） | 0–999 整数 | 整数精确匹配，抽取实现各异 | ⚠️（口径为通识，未见单篇规范） |
| Omni-MATH ([2410.07985](https://arxiv.org/abs/2410.07985)) | olympiad 级，数值/表达式为主 | **GPT-4o judge 为主**（100 题人工元集 98% 一致）+ 开源 Omni-Judge（与人工 86% 一致）；规则法仅覆盖 74% 答案形态 | ✅ 全文核对（缺口 A） |
| FrontierMath ([2411.04872](https://arxiv.org/abs/2411.04872)) | Epoch AI 研究级，题目不公开 | 每题程序化 checker：整数 exact match / 非整数 SymPy 差值→0；guessproof（猜中率<1%）；10k token 上限 + 收尾强制答案 prompt。**v2（2026-06）修订了 42% 题目的错误** | ✅ 全文 + 官方页（缺口 A） |
| OlympiadBench ([2402.14008](https://arxiv.org/abs/2402.14008)) | 双语 olympiad 数理（开放 79% / 证明 21%） | 开放题：数值 1e-8 容差 + SymPy 差值→0，无 LLM judge；证明题不自动判分；论文自认判分器存在 "Incorrect Judging" | ✅ 全文 + 仓库（缺口 A） |
| CMATH ([2306.16636](https://arxiv.org/abs/2306.16636)) | 中文**小学**数学 1.7k 题（validation 600 + test 1.1k；另 60 题干扰信息子集） | 位置正则抽数字 + 相对容差 1e-2（**非** exact match、不感知 boxed）；**异常回复剔除出分母** | ✅ 身份、构成与 `eval.py` 源码（缺口 A 二轮） |
| MathBench ([2405.12209](https://arxiv.org/abs/2405.12209)) | 3709 题，分层（理论 2209 / 应用 1500） | Chat：CircularEval（打乱选项测 N 次**全对才算对**）；Base：PPL；开放题：触发句定位数字 + 精确串匹配（最窄口径，✅ 源码） | ✅ 全文 + 开放题源码（缺口 A 二轮） |

要点：越接近"竞赛数值/表达式答案"的基准，判分越收敛到 §2 的两类程序化范式
（归一化字符串匹配 / 解析+符号等价）；LLM judge 只在带人工校准元集的大型基准
出现；FrontierMath 是唯一"判分器完全私有"的先例——与本项目场景（官方判分器
黑盒）同构。FrontierMath v2 一次性修订 42% 题目的错误也说明：**重金打造的
基准都有大面积题目缺陷，基准可靠性本身是评测风险的一部分**。

## 二、判分器实现行为（源码级，全部 ✅ 本会话通读）

源码存档：`tmp/research_verify/`（`248c4f_utils.py` = lm-eval `hendrycks_math`
任务实现；`utils.py` = lm-eval `minerva_math` 任务实现；`README.md` = huggingface
Math-Verify）。注意 hendrycks/math 原仓库根目录实测**没有** `math_equivalence.py`
（404），业界通行的是 lm-evaluation-harness 中的移植版（其注释标明移植自
hendrycks）。

### 2.1 hendrycks 口径（lm-eval `hendrycks_math/utils.py`）

- 抽取：参考答案取参考解答中**最后一个** `\boxed{}`/`\fbox{}`；模型输出取首尾
  `$` 之间的内容（`$` 少于 2 个时取整串）。
- 等价：`strip_string` 后**纯字符串相等**，无 sympy；strip 异常时回退原串相等。
- `strip_string` 实际归一化步骤（源码顺序）：去换行；去 `\!`；`\\`→`\`；
  `tfrac/dfrac`→`frac`；去 `\left/\right`；去 `^{\circ}/^\circ`（度）；去 `\$`；
  去尾部 `\text{ ...}` 单位；去 `\%`；` .`→` 0.`、`{.`→`{0.`、行首 `.` 补 `0`；
  `k = x` 且左项 ≤2 字符时剥前缀；`\sqrt3`→`\sqrt{3}`；去全部空格；
  `\frac12`→`\frac{1}{2}`；**`0.5`→`\frac{1}{2}`（硬编码唯一十进制↔分数等价）**；
  `a/b` 仅当两侧均为整数字面量时转 `\frac{a}{b}`。
- 直接推论（失败类清单）：小数与分数不等价（除 0.5）；非整数比 `1.5/2` 不归一；
  无序集合/区间完全不处理；单位只处理尾部 `\text{ }` 形态；`%` 去除但 `percent`
  词形不处理；sympy 不存在所以解析失败不存在——**表示稍异即判错**。

### 2.2 Minerva 口径（lm-eval `minerva_math/utils.py`）

- 抽取：正则强制 `Final Answer: The final answer is(.*?). I hope it is correct.`；
  匹配不到 → **`[invalidanswer]`（直接判错）**。few-shot 示例即用该句式教模型。
- `normalize_final_answer` 注释写明"**逐字符拷贝自 Minerva 论文（Lewkowycz et al.
  2022, [2206.14858](https://arxiv.org/abs/2206.14858)）附录 D**"：单位词表删除
  （square/ways/dollars/mph/inches/ft/hours/km/units/points/feet/minutes/digits/
  cents/degrees/cm/gm/pounds/meters/meals/edges/students/multiples/…）；
  `\text{and}`→`,`；`100,000`→`100000`；`\boxed{}`/`\text{}`/`\textbf{}`/
  `\overline{}` 剥壳；`\fracab`/`\sqrta` 修复；`=` 取右侧；去空格。
- 等价：`parse_latex` 两侧解析 → `simplify(x1-x2)==0`，**5 秒超时**；解析失败、
  减法失败、超时**一律 False（fail-closed 判错）**。
- 现状：该任务 `process_results` **同时**报告 `exact_match`（Minerva 协议）与
  `math_verify`（调用 huggingface Math-Verify）两个指标——判分器代际正在更替，
  新基准论文多双报。

### 2.3 Math-Verify（huggingface/Math-Verify，✅ README 通读）

- README 对比表（MATH 上同一批输出的判分器间差异，README 未注明具体模型）：
  Harness 0.0802 / Qwen 0.1288 / Math-Verify 0.1328——**判分器选择本身移动分数
  5 个点以上**；README 自述现有判分器"极端情况下可低估 40 点"。
- 三步架构：格式无关抽取（按优先级正则，多个匹配取最后出现者）→ SymPy 公共
  表示（`\mathrm/\displaystyle`、单位、`\sqrt/\frac` 畸形、boxed、方程拆分、
  `10%→0.1`、`10 cm→10`、`β→beta`、`0.333` 精确表示）→ 金标比较（数值容差、
  符号差化零、集合对称差、区间端点、矩阵逐元素、不等式翻转等价）。
- **`verify` 有意不对称**（README FAQ）：金标为不等式、预测为区间 → True；
  金标为区间、预测为不等式 → False。目的是防止模型"抄题面不等式"的 reward
  hack；金标为数字、预测为解链 → True，反向 False。**这对本仓库的启示是：
  判分器按"金标形态"定向比较，提交侧无从利用，唯一安全做法是输出最简规范形。**
- 官方建议（README）：让模型把答案放进 `\boxed{}`；抽取用 Latex+Expr 双配置；
  不要把 `StringExtractionConfig` 与其他配置混用（会抓到正文里的 A/B/C/D 字符）。
- **采纳证据（缺口 B）**：Open LLM Leaderboard v2 官方采用 Math-Verify 并全量重评
  （[公告](https://huggingface.co/blog/math_verify_leaderboard)、
  [v2 博客](https://huggingface.co/spaces/open-llm-leaderboard/blog)；出处定位 ✅，
  本机网络不通、正文 ⚠️）——判分器解析缺陷造成榜单级系统性低估是官方承认并
  修复过的事实。

### 2.4 hendrycks 原版、OpenCompass 与模型厂自建评测（✅ 缺口 A 两轮源码通读）

- **hendrycks 原版真身**：`hendrycks/math` 仓库（默认分支 `main`）中路径为
  [`modeling/math_equivalence.py`](https://raw.githubusercontent.com/hendrycks/math/main/modeling/math_equivalence.py)
  （根目录无此文件，故直接抓根路径会 404）。流程与 lm-eval 移植版一致：
  `_strip_string` 归一化后**字符串相等**，异常回退裸串相等；**无 sympy、
  无数值容差**——`1/\sqrt{3}` 与 `\sqrt{3}/3` 这类只有 sympy 能判等的写法
  会判错。
- **OpenCompass**（[`opencompass/datasets/math.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/math.py)）：
  抽取两级——v2 先 last-boxed（`rfind('\boxed')` + 花括号配对，兼容 `\fbox`），
  失败回退 v1（按句切分、优先含 "final answer" 的句子，回退正则放宽为
  `final answer|answer is`）；归一化同 hendrycks 族（去单位词、剥 `\text{}`、
  `tfrac/dfrac→frac`、`0.5→\frac{1}{2}`、整数字面量 `a/b→\frac{a}{b}`）；判分
  `MATHEvaluator.is_equiv` 为**规范化纯字符串相等（无 sympy）**，不等再依次
  降级重试，最终兜底裸串相等；另有 judge 式抽取 `ANSWER: ` 正则模式。
  即 OpenCompass 属 hendrycks 口径的自有变体——**归一化字符串匹配是国产栈的
  默认口径**。
- **Qwen2.5-Math 自建评测**（[evaluation/](https://github.com/QwenLM/Qwen2.5-Math/tree/main/evaluation)，✅ 第二轮源码）：与 lm-eval 无实现关系，系谱为 ToRA/hendrycks（`grader.py` 文件头自述，直系借用 DeepSeek-Math）。抽取优先级链 = Minerva 句式 → 最后 boxed（花括号栈，兼容 `\boxed5`）→ "answer is" → 中文"答案是" → 兜底全文最后一个数字；归一化为 hendrycks 超集（约 130 项单位词表、word2number、`(-\infty,\infty)→\mathbb{R}` 等，**无 0.5→1/2 特判**）；等价 `math_equal` 级联 = 字符串相等 → 数值 `isclose(rel_tol=1e-4)` 且金标三向 `[ref/100, ref, ref×100]`（百分比等价）→ 区间/矩阵逐元素 → 方程移项 → SymPy 三解析器（`parse_latex`/`parse_expr`/latex2sympy2）`simplify(a−b)==0`；pebble 3 秒超时 fail-closed。系统提示强制 boxed；maj@64/rm@256 聚类以 `math_equal` 为等价谓词。
- **DeepSeek-Math 评测**（✅ 第二轮源码）：抽取 = Minerva 句式 → 全 boxed 列表取末个 → "answer is" → 程序输出块（TIR）→ 末位数字；判分 `is_correct` 三级或 = 浮点差 abs<1e-3 / 裸串相等 / `math_equal`（SymPy `simplify(a−b)==0`，abs_tol=1e-3）；**多答案双列全匹配 + `\cup` 拆分**——无序集合语义的直接源码证据；主链不带 timeout，解析失败即 False；PoT 以程序执行结果为答案。
- **CMATH `eval.py`**（[XiaoMi/cmath](https://github.com/XiaoMi/cmath)，✅ 第二轮源码）：**完全不感知 boxed**——位置正则抽数字（数字须紧邻中文标点/行界，默认只留全回复最末 2 个候选）；等价**非 exact match**：整数精确、其余相对差 <1e-2（1%）；**异常回复（超时/报错）剔除出分母**（`hit/(N−err)`），提取失败才算错。
- **MathBench 开放题**（✅ 第二轮源码；官方仓库 [open-compass/MathBench](https://github.com/open-compass/MathBench) 只含数据集，评测在 OpenCompass）：中文按"答案是"、英文按 "The answer is" 切分后取**第一个**数字，无触发句取全文最后一个数字；`AccEvaluator` **精确字符串匹配**——无 boxed 感知、无 sympy、无容差、连 hendrycks 的 `0.5↔1/2` 特判都没有，**是已核对判分器中归一化最窄者**。选择题侧 CircularEval = 选项四循环位移**全对才算对**。

至此已源码级覆盖 **9 个判分实现**（hendrycks 原版、lm-eval hendrycks_math、
lm-eval minerva_math、Math-Verify、OpenCompass MATH、Qwen2.5-Math、
DeepSeek-Math、CMATH、MathBench 开放题）；`\boxed{}` + 最简规范形在全部
9 个口径下均安全。

## 三、失败模式与本仓库抽取卫生的关系

由 §2 源码**直接证明**的判分失败类（非推测）：

1. 缺 `\boxed` 且不符合判分器句式 → invalid（Minerva 源码字面 `[invalidanswer]`）。
2. 十进制 vs 最简分数不等价（hendrycks 除 0.5 外无一处理）。
3. 无序集合/区间在 hendrycks 口径完全不归一（本仓库已有"无序有理数集合归一化"
   卫生与此同向，且 math-verify 对集合对称差的处理证明这类归一化是社区共识方向）。
4. 单位/百分号/度符号是**词表式**处理，覆盖不全；写在文字里（"3 cm"）比写在
   `\text{}` 里更危险。
5. `x = 42` 前缀仅在左项 ≤2 字符时被剥离；长变量名前缀不剥。
6. sympy 路径解析失败 = 判错：**输出非常规记法（自造宏、非标准函数名）是高风险**。
7. hendrycks 原版与 OpenCompass 均无 sympy、无容差：`1/\sqrt{3}` 与 `\sqrt{3}/3`
   这类 sympy 才能判等的写法会判错（✅ 缺口 A 源码）——**最简规范形比"看起来
   正确"更本质**。
8. 判分器误判是**官方承认的普遍现象**，不是本仓库的猜测：Let's Verify 原句
   "correctness is determined solely by checking the final answer, a process which
   occasionally leads to misgraded solutions"；OlympiadBench 自列 "Incorrect
   Judging" 缺陷（√(ab) 类等价式无法判定、容差设置致误判）（✅ 缺口 A 原文引用）。
9. 数值容差谱系（✅ 缺口 A 二轮源码）：Qwen rel_tol=1e-4（金标三向 /100、×1、
   ×100）、DeepSeek abs 1e-3、CMATH 相对 1e-2、OlympiadBench 1e-8、Math-Verify
   可配置——**十进制 vs 分数在宽容差族安全，在字符串相等族（hendrycks /
   OpenCompass / MathBench 开放题）不安全**；最简规范形是唯一全口径覆盖解。
10. 分母纪律反例（✅ CMATH 源码）：CMATH 把异常回复剔除出分母（`hit/(N−err)`）。
    本地报告**不可效仿**：invalid/超时必须计入分母，否则正确率与成本被同时
    美化（对齐 AGENTS.md 报告要求）。另外 CMATH/MathBench 开放题完全不感知
    boxed、依赖"答案句/行界 + 数字"的位置假设——**答案句式 + 裸数字 + boxed
    并存**是同时喂饱两类抓取假设的稳妥形态。

对本仓库的边界（对齐 AGENTS.md）：

- 允许：对"任意满足同一数学条件"的表示做规范输出（最简分数、规范集合序、
  去单位、度符号、boxed 纪律）；这是判分对齐，不是答案特判。
- 不允许：为本地某几题表面字符串对上而放宽/加严抽取；本地判分器的等价判断
  放宽不能替代表示规范（官方判分器不归我们改）。
- 可行动项：本地回归判分引入 Math-Verify（开源库、不涉隐藏答案），与现有
  hendrycks 口径**双判分器并行报告**，观察 112 题上两口径差异——这是纯评测
  侧改动，不触碰答题逻辑。

## 四、Outcome vs Process 评测与 LLM-as-judge（仅评测侧知识）

- Process 评测线：PRM800K/Let's Verify Step by Step（[2305.20050](https://arxiv.org/abs/2305.20050)，✅）、
  MATH-Shepherd（[2312.08935](https://arxiv.org/abs/2312.08935)，✅）、
  PRMBench（[2501.03124](https://arxiv.org/abs/2501.03124)，✅）。评的是**逐步骤
  正确性**，属评测侧基础设施；本赛事判 `final_response` 答案正确性 = outcome 型。
  **不引入运行时，不做任何 PRM 组件**（与 2026-08-27 能力研究的排除一致）。
- LLM-as-judge：MT-Bench 论文（[2306.05685](https://arxiv.org/abs/2306.05685)，✅）
  系统记录位置偏差、冗长偏差、自增强偏差；数学多步判分是公认弱区。**本仓库
  本地判分不引入 LLM judge**；对外报告也不用 LLM 打分充当正确性证据。
  补充（缺口 A）：主流基准并非完全不用 LLM judge——Omni-MATH 以 GPT-4o 为主判，
  用 100 题人工元集校准（98% 一致），开源 Omni-Judge 与人工仅 86% 一致。
  即基准侧的 LLM judge 必须配人工校准且仍有约 14% 残差；本仓库没有人工元集，
  维持不引入。

## 五、不涉及答题能力的评测维度

### 5.1 成本归一化与预算感知

- [Are More LLM Calls All You Need?](https://arxiv.org/abs/2403.02419)（✅ 题名）：
  复合推理系统的调用数扩展律，SC 类收益受预算约束、存在拐点——支持本仓库
  "有效调用上限不超过 C0 的 5"与调用数并列报告的口径。
- 本仓库已有口径（平均/P95 调用、completion tokens、墙钟、invalid 数、正确数
  并列）与该文献方向一致，保持即可。

### 5.2 方差与误差棒

- [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640)（✅ 摘要核对，缺口 B）：
  把评测概念化为"来自不可见超总体的抽样"，给出两模型差异度量与评测实验规划
  公式及降噪建议（正文公式 ⚠️ 未逐条核对）。对 112 题规模，**正确数差 1–3 题
  完全可能来自抽样噪声**。这为 AGENTS.md"默认路径晋升须双轮独立 A/B"提供了
  统计学依据；建议实验报告附正确数的简易置信区间（如 Wilson 区间）。

### 5.3 题面/格式扰动鲁棒性

- GSM-Symbolic（[2410.05229](https://arxiv.org/abs/2410.05229)，✅ 题名）：数值与
  子句扰动下性能下降，说明固定题集分数含题面记忆成分。
- **批评文**：[Statistically Earnest: A Critical Re-evaluation of GSM-Symbolic](https://arxiv.org/abs/2605.28700)
  （✅ 摘要核对，缺口 B，2026-05）：GLMM 重评 20 个开源模型发现**仅约一半模型**
  有统计显著的扰动变化；GSM-Symbolic 变体题面整数分布系统性偏大（K-S=0.12,
  p<0.001），控制后约再解释一半显著性；失败模式是模型特异的（变量绑定脆弱/
  算术限制/双任务干扰）。→ 扰动回归仍可做，但"掉分 = 记忆/脆弱"的推断必须
  控制题面统计量（数值大小分布），显著性按题建模而非只看均分——这强化
  "不得据扰动结果逐题调 Prompt"的红线。
- PromptBench（[2312.07910](https://arxiv.org/abs/2312.07910)，✅ 摘要 + README，
  缺口 B）：四级攻击清单——字符级（DeepWordBug/TextBugger）、词级（TextFooler/
  BertAttack）、句子级（CheckList/StressTest）、语义级（Human-crafted）——可直接
  作为本地扰动回归（同题改写、子句顺序、数值替换）的分类参照；其集成的 DyVal
  以"受控复杂度动态生成"为官方定位的污染缓解手段（见 §5.4）。攻击依赖
  TextAttack，只进本地实验依赖，不进提交环境。
- Let Me Speak Freely?（[2408.02442](https://arxiv.org/abs/2408.02442)，✅ 摘要核对，
  缺口 B）：主张"结构化格式约束显著降低推理能力、约束越严降幅越大"（摘要级；
  正文基准数字 ⚠️ 未读）。社区反驳：[dottxt "Say What You Mean"](https://blog.dottxt.ai/say-what-you-mean.html)
  （✅ 通读；一手但利益相关方——outlines 开发商）用同模型重跑得到相反排序，
  并指出原文 NL/结构化 prompt 非同口径、把 constrained decoding 与 API JSON-mode
  混淆。**双方共同支持的结论可放心引用：解析/抽取方式的选择本身显著改变分数**
  （同一批生成：strict regex 0.35 / AI parser 0.57 / 手写宽松 regex 0.61）。本笔记
  维持"方向性证据"定位：反 JSON 强结构化、自由文本 + boxed 的选择不变；答案
  格式纪律应在 Prompt 中显式声明并给示例。

### 5.4 数据污染与过拟合

- GSM1k（[2405.00332](https://arxiv.org/abs/2405.00332)，✅）：镜像新题上多家模型
  掉分，说明固定公开题集分数含记忆成分。这为 AGENTS.md"112 题仅作回归、拒绝
  答题能力过拟合"提供了外部同构证据；也说明**本地集分数高不预示隐藏题分数**。
- 去污染工程口径实例（✅ 缺口 A）：DeepSeekMath 用"与评测集任一 **10-gram**
  精确匹配的文本段即移除"。本地集若日后扩充，可借用 10-gram 口径自检与公开
  数学题库的重叠。

## 六、竞赛提交侧通用工程做法（非答题能力）

场景锚定（本仓库事实）：平台调 `agent.solve(problem, metadata)`，返回可 JSON
序列化 dict 且必须含非空字符串 `final_response`；接口仅 `client.chat(messages,
temperature, max_tokens)`；单题 20 分钟、整轮 6 小时、并发 3。

1. **fail-closed 输出**：任何异常/超时/解析失败路径都必须返回非空字符串
   `final_response`（官方零分排查清单的字面要求；判分器侧同构证据是 Minerva 的
   `[invalidanswer]`——空/缺失即判错，所以"有比美重要"）。
2. **答案表示纪律**：`\boxed{}` + 最简规范形（§2/§3）。判分器共识优先于表述
   优美；不要输出解释性后缀/长尾文字稀释抽取器的最后匹配。
3. **截断防护**：判分器普遍取"最后出现的答案"，截断会同时造成句式缺失与
   最后匹配漂移——答案优先输出（已有 C0）与 max_tokens 预算是同一问题的两侧。
4. **invalid 与 model_error 区分治理**：invalid（判分器语义）重试同路径无意义，
   应换表示/换路径；model_error（端点语义）才适合原样重试。本仓库 P1 已按此
   分治，判分器源码证明该区分是判分语义层面的（句式缺失 → invalid）。
5. **trace 卫生**：AGENTS.md 已约束（不存敏感信息与完整 prompt）；通例是 trace
   只记决策摘要与失败原因，保证可 JSON 序列化。
6. **预算与并发**：官方并发 3 → 共享端点实验串行（已有规则）；单题墙钟上限
   内必须留出 fail-closed 兜底路径的执行余量。

## 七、明确不做（对齐既有处置）

- 不引入 LLM-as-judge 替代本地规则判分（§4）。
- 不引入 PRM/process 组件（§4，与 2026-08-27 笔记一致）。
- 不做"判分器猎奇"：尝试反推官方判分器、为其定制的答案形态变换（如猜测其
  `verify` 不对称方向）属于投机对齐，一旦判错方向反而伤分；只做**判分器共识
  表示**这种对所有已知实现都安全的形态。
- 不因 Math-Verify 更宽松而用它"抬高"本地分数做报告口径；双判分器只用于
  诊断表示不一致，不以高分者为默认报告。

## 八、一手来源表

| 来源 | 核对状态 | 关键内容 / 对本仓库意义 |
|---|---|---|
| [hendrycks 口径判分（lm-eval hendrycks_math utils.py）](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/hendrycks_math/utils.py) | ✅ 源码通读 | strip_string 全步骤 + 字符串相等；0.5→1/2 唯一特例；无集合/区间归一 |
| [Minerva 口径判分（lm-eval minerva_math utils.py）](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/minerva_math/utils.py) | ✅ 源码通读 | 强制句式抽取，缺失即 `[invalidanswer]`；附录 D 归一化；sympy 等差 + 5s 超时 fail-closed；并行双报 math_verify |
| [Minerva 论文](https://arxiv.org/abs/2206.14858) | ✅ 题名 | 归一化规则的原始出处（附录 D） |
| [HuggingFace Math-Verify](https://github.com/huggingface/Math-Verify) | ✅ README 通读；Leaderboard v2 采纳出处定位（缺口 B） | 判分器间 5+ 点差异；等价类；verify 不对称防 reward-hack；官方建议 boxed |
| [GSM8K](https://arxiv.org/abs/2110.14168) | ✅ 题名 | `####` 精确匹配口径 |
| [MATH](https://arxiv.org/abs/2103.03874) | ✅ 题名 | boxed + math_equivalence 口径 |
| [Let's Verify Step by Step](https://arxiv.org/abs/2305.20050) | ✅ 题名 + 全文（缺口 A） | MATH-500 出处（✅ 原句核对）与 process 评测线起点 |
| [MATH-Shepherd](https://arxiv.org/abs/2312.08935) | ✅ 题名 | 自动 process 标注（仅评测侧知识） |
| [PRMBench](https://arxiv.org/abs/2501.03124) | ✅ 题名 | PRM 评测基准（仅评测侧知识） |
| [MT-Bench / LLM-as-judge](https://arxiv.org/abs/2306.05685) | ✅ 题名 | 位置/冗长/自增强偏差 → 不用于判分 |
| [Are More LLM Calls All You Need?](https://arxiv.org/abs/2403.02419) | ✅ 题名 | 调用数扩展律 → 预算报告口径 |
| [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) | ✅ 摘要（缺口 B） | 评测=实验、两模型差异度量与规划公式 → 双轮 A/B 的统计依据 |
| [GSM-Symbolic](https://arxiv.org/abs/2410.05229) | ✅ 题名 | 题面扰动下降 → 扰动回归思路 |
| [Statistically Earnest（GSM-Symbolic 批评）](https://arxiv.org/abs/2605.28700) | ✅ 摘要（缺口 B） | GLMM 重评仅约半数显著、变体整数分布偏移、失败模式模型特异 |
| [PromptBench（库）](https://arxiv.org/abs/2312.07910) | ✅ 摘要 + README（缺口 B） | 四级攻击清单；DyVal 动态生成缓解污染 |
| [Let Me Speak Freely?](https://arxiv.org/abs/2408.02442) | ✅ 摘要 + dottxt 反驳通读（缺口 B）；正文数字 ⚠️ | 格式约束争议未决；双方共识：解析器选择改变分数（0.35→0.61） |
| [GSM1k](https://arxiv.org/abs/2405.00332) | ✅ 题名 | 记忆/污染证据 → 拒绝过拟合 |
| [Omni-MATH](https://arxiv.org/abs/2410.07985) | ✅ 题名 | olympiad 基准 |
| [FrontierMath](https://arxiv.org/abs/2411.04872) | ✅ 题名 + checker 机制（缺口 A） | 判分器私有先例，与本项目场景同构 |
| [OlympiadBench](https://arxiv.org/abs/2402.14008) | ✅ 题名 | 双语数理 olympiad |
| [CMATH](https://arxiv.org/abs/2306.16636) | ✅ 题名 | 中文小学数学基准 |
| [MathBench](https://arxiv.org/abs/2405.12209) | ✅ 题名 | 分层数学基准 |
| [Qwen2.5-Math](https://arxiv.org/abs/2409.12122) / [DeepSeekMath](https://arxiv.org/abs/2402.03300) | ✅ 评测节 + 评测源码（缺口 A 二轮） | Qwen：抽取链 + `math_equal`（rel_tol 1e-4、百分比三向）；DeepSeekMath：全 boxed 链、abs 1e-3、`\cup` 拆分、10-gram 去污染 |
| [hendrycks/math `modeling/math_equivalence.py`](https://raw.githubusercontent.com/hendrycks/math/main/modeling/math_equivalence.py) | ✅ 源码通读（缺口 A） | 原版等价判断真身：归一化字符串相等、无 sympy 无容差 |
| [OpenCompass `opencompass/datasets/math.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/math.py) | ✅ 源码通读（缺口 A） | 国产栈口径实证：last-boxed + 归一化 exact match |
| [Epoch AI FrontierMath](https://epoch.ai/frontiermath) | ✅（缺口 A） | v2 修订 42% 题目错误——基准可靠性风险实例 |
| [Omni-MATH HTML](https://arxiv.org/html/2410.07985v3) / [OlympiadBench HTML](https://arxiv.org/html/2402.14008v2) / [MathBench HTML](https://arxiv.org/html/2405.12209v1) | ✅ 全文（缺口 A） | LLM judge 人工校准口径 / 1e-8 容差 + SymPy 差值 / CircularEval |
| [QwenLM/Qwen2.5-Math evaluation/](https://github.com/QwenLM/Qwen2.5-Math/tree/main/evaluation) | ✅ 源码通读（缺口 A 二轮） | 抽取链 + `math_equal`（rel_tol 1e-4、百分比三向、SymPy 三解析器、3s 超时 fail-closed） |
| [deepseek-ai/DeepSeek-Math evaluation/](https://github.com/deepseek-ai/DeepSeek-Math/tree/main/evaluation) | ✅ 源码通读（缺口 A 二轮） | 全 boxed 抽取链、abs 1e-3、多答案双列全匹配与 `\cup` 拆分 |
| [XiaoMi/cmath eval.py](https://github.com/XiaoMi/cmath) | ✅ 源码通读（缺口 A 二轮） | 不感知 boxed 的位置正则抽数字 + 1e-2 相对容差；**异常回复剔除出分母** |
| [OpenCompass `datasets/mathbench.py`](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/datasets/mathbench.py) + [circular evaluator](https://raw.githubusercontent.com/open-compass/OpenCompass/main/opencompass/openicl/icl_evaluator/icl_circular_evaluator.py) | ✅ 源码通读（缺口 A 二轮） | 开放题最窄口径：触发句抽数字 + 精确串匹配；CircularEval 四位移全对才算对 |

## 九、证据最弱处

1. **官方判分器实现未知**——本研究最大空白。所有"判分对齐"建议都建立在
   "官方大概率采用上述三种范式之一"的归纳上，飞书文档无法匿名访问，无法确认。
2. （缺口 A 两轮后基本收窄）基准与模型厂评测细节均已源码级升级 ✅（9 个判分
   实现，见[缺口 A](evaluation_gaps_a_基准与协议细节.md) 第二轮节）。遗留均为
   低优先 ⚠️：Qwen `math_utils.compare_ans`（grep 证实无调用方的第二套实现）、
   DeepSeek-Math OCW 的 AGIEval 系 `is_tex_equiv`、MathBench 论文期配置与现行
   main 的代际差。
3. （缺口 B 已核对）Let Me Speak Freely 与 dottxt 反驳各有一手实验、无中立第三方
   复现定论——维持"方向性证据"定位，但双方共识（**解析器选择显著改变分数**，
   0.35→0.61）可放心引用；GSM-Symbolic 批评文（✅ 摘要）表明扰动结论须控制
   题面统计量；Error Bars 论文摘要 ✅、公式细节未逐条核对；Leaderboard v2 采纳
   Math-Verify 出处已定位、正文因本机网络不通未逐字核对。
4. （已解决，缺口 A）hendrycks 原版真身在 `hendrycks/math` 仓库 `main` 分支
   `modeling/math_equivalence.py`；§2.1 引用的 lm-eval 移植版与其一致。
5. （已大幅收窄）"判分器共识表示"清单现覆盖五个实现：hendrycks 原版、
   OpenCompass、lm-eval hendrycks_math、lm-eval minerva_math、Math-Verify，
   外加 OlympiadBench 的容差口径。未覆盖的主要是 MathBench 开放题匹配等
   未公开细节。

## 推荐动作（纯评测侧，不触答题逻辑）

1. 本地回归判分升级为**双判分器并行**（现有 hendrycks 口径 + Math-Verify），
   逐题记录两口径差集——差集即"表示不一致但语义正确"的题，是抽取卫生的
   直接量化。9 个已核口径中，hendrycks 族（无容差）与宽容差族（Qwen/
   DeepSeek/CMATH）正交，双判分器恰好覆盖两极。
2. 实验报告模板加一列正确数 **Wilson 95% 置信区间**（112 题规模下与双轮 A/B
   配合使用）。
3. 把"答案表示纪律"（boxed + 最简规范形 + 无解释性尾缀）整理成可单测的规范
   清单，作为与 2026-08-27 能力研究并列的卫生候选队列。
