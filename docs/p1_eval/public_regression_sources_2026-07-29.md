# 112 道公开分布回归题：来源目录

日期：2026-07-29  
用途：为 P1 的 112 道短题知识覆盖回归题提供可审计的概念来源与章节定位。

能力边界（2026-07-30 审计）：该集合覆盖 18 个数学方向，但当前全部 112 题均
被 `classify_problem_type` 识别为 `calculation`。它适合检查知识点覆盖、
答案解析和基础输出链路，不代表证明/推导/解释、长题面、跨方向混合题或隐藏
评测风格。题源公开性与方向覆盖也不等价于复杂能力覆盖。

## 使用边界

- 本目录只采用来源机构自己发布的一手资料：MIT OpenCourseWare（MIT OCW）课程页、讲义目录，以及 NIST/SEMATECH 工程统计手册。
- 回归题不得复制课程作业、考试或其答案。每道题应由项目依据下列定义、定理或标准计算公式自行选取参数并重新表述；数据项中的 `source_id` 与 `source_ref` 只用于说明知识点来源。
- 每道题还应保留独立的答案验算说明。来源可追溯不等于答案已验证；数学验算与数据结构校验是两个独立的验收项。
- MIT OCW 的站点材料一般按 CC BY-NC-SA 4.0 发布，但个别第三方内容可能另有标注；具体使用仍以页面声明为准。MIT OCW 的许可说明允许在署名、非商业和相同方式共享条件下分享、改编材料。[MIT OCW Privacy and Terms of Use](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)
- NIST 说明：除明确标为受版权保护的材料外，NIST 网站信息属于公共信息，可分发或复制，并建议保留适当署名。[NIST Copyrights & Disclaimers](https://www.nist.gov/copyrights-disclaimers)

## 公开的 18 方向分布

| 方向 | 数量 | 建议 `source_id` |
|---|---:|---|
| 离散数学 | 24 | `mit_ocw_6_042j` |
| 数值分析 | 13 | `mit_ocw_18_330` |
| 测度积分 | 11 | `mit_ocw_18_125` |
| 微分几何 | 9 | `mit_ocw_18_950` |
| 概率论 | 8 | `nist_stats_handbook` |
| 抽象代数 | 8 | `mit_ocw_18_703` |
| 随机过程 | 7 | `mit_ocw_6_262` |
| 复分析 | 7 | `mit_ocw_18_04` |
| 常微分方程 | 5 | `mit_ocw_18_03sc` |
| 统计推断 | 4 | `nist_stats_handbook` |
| 泛函分析 | 4 | `mit_ocw_18_102` |
| 线性回归 | 3 | `nist_stats_handbook` |
| 偏微分方程 | 3 | `mit_ocw_18_303` |
| 非基础及进阶课程 | 2 | `mit_ocw_18_905` |
| 高等代数 | 1 | `mit_ocw_18_06` |
| 运筹学 | 1 | `mit_ocw_15_053` |
| 数学分析 | 1 | `mit_ocw_18_100a` |
| 拓扑学 | 1 | `mit_ocw_18_901` |
| **合计** | **112** |  |

## 来源目录

### `mit_ocw_6_042j`

- 标题/机构：*Mathematics for Computer Science*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/)；[按章阅读目录](https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-fall-2010/resources/readings/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：离散数学。
- 可定位章节：命题与证明、归纳法、数论、图论、有向图、关系与偏序、递推、计数、生成函数；阅读目录列出 Chapter 1–13 的主题。
- 题目改编边界：仅依据逻辑等价、握手定理、树、同余、容斥和组合计数等定义/定理原创参数化，不复制课程习题。

### `mit_ocw_18_330`

- 标题/机构：*Introduction to Numerical Analysis*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-330-introduction-to-numerical-analysis-spring-2012/)；[课程大纲](https://ocw.mit.edu/courses/18-330-introduction-to-numerical-analysis-spring-2012/pages/syllabus/)；[讲义目录](https://ocw.mit.edu/courses/18-330-introduction-to-numerical-analysis-spring-2012/resources/lecture-notes/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：数值分析。
- 可定位章节：级数展开、数值积分与差分、插值与样条、ODE 初值方法、求根与 Newton 法、最小二乘。
- 题目改编边界：自行设置函数、节点、步长和初值，按标准算法做有限步计算或误差阶判断。

### `mit_ocw_18_125`

- 标题/机构：*Measure and Integration*, MIT OpenCourseWare。
- 公开 URL：[讲义目录](https://ocw.mit.edu/courses/18-125-measure-and-integration-fall-2003/pages/lecture-notes/)；[课程资源](https://ocw.mit.edu/courses/18-125-measure-and-integration-fall-2003/download/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：测度积分。
- 可定位章节：Lecture 1 的测度空间、σ-代数和 Borel 集；Lecture 2–4 的可测函数、简单函数、Lebesgue 积分、单调收敛与 Fatou 引理；Lecture 17–20 的 Lp 与 Fubini 定理。
- 题目改编边界：用新选集合与简单函数考查定义、测度、积分和收敛定理的适用结论。

### `mit_ocw_18_950`

- 标题/机构：*Differential Geometry*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-950-differential-geometry-fall-2008/)；[讲义资源](https://ocw.mit.edu/courses/18-950-differential-geometry-fall-2008/download/)；[课程大纲](https://ocw.mit.edu/courses/18-950-differential-geometry-fall-2008/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：微分几何。
- 可定位章节：Chapter 1 局部与整体平面曲线几何；后续曲面/超曲面局部与整体几何；长度与距离。课程以曲率为中心。
- 题目改编边界：自行给出曲线或规则曲面参数，计算弧长、曲率、基本形式或 Gaussian 曲率等标准量。

### `nist_stats_handbook`

- 标题/机构：*NIST/SEMATECH e-Handbook of Statistical Methods*, National Institute of Standards and Technology。
- 公开 URL：[详细目录](https://www.itl.nist.gov/div898/handbook/dtoc.htm)；[概率分布概览](https://www.itl.nist.gov/div898/handbook/eda/section3/eda36.htm)；[二项分布](https://itl.nist.gov/div898/handbook/eda/section3/eda366i.htm)；[置信区间](https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm)；[检验与置信区间的对应](https://www.itl.nist.gov/div898/handbook/prc/section1/prc15.htm)；[线性最小二乘回归](https://www.itl.nist.gov/div898/handbook/pmd/section1/pmd141.htm)。
- 使用说明：NIST 未特别标注版权的网页信息按其声明属于公共信息；保留 NIST 署名。
- 覆盖方向：概率论、统计推断、线性回归。
- 可定位章节：1.3.6 概率分布及常见分布；7.1.3–7.1.5 假设检验和置信区间；4.1.4.1 线性最小二乘模型。
- 题目改编边界：自行构造有限样本和分布参数，使用标准公式计算概率、统计量、区间、检验结论与 OLS 系数。

### `mit_ocw_18_703`

- 标题/机构：*Modern Algebra*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-703-modern-algebra-spring-2013/)；[讲义目录](https://www.ocw.mit.edu/courses/18-703-modern-algebra-spring-2013/pages/lecture-notes/)；[课程大纲](https://ocw.mit.edu/courses/18-703-modern-algebra-spring-2013/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：抽象代数。
- 可定位章节：Lecture 1–13 群、子群、陪集、循环群、置换群、同态、商群、Sylow 定理；Lecture 14–23 环、理想、域、整环、多项式环与群作用。
- 题目改编边界：采用新群、置换、多项式或理想，依据定义和标准定理原创计算题/判断题。

### `mit_ocw_6_262`

- 标题/机构：*Discrete Stochastic Processes*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/6-262-discrete-stochastic-processes-spring-2011/)；[资源目录](https://ocw.mit.edu/courses/6-262-discrete-stochastic-processes-spring-2011/download/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：随机过程。
- 可定位章节：Lecture 2 Bernoulli 过程；Lecture 4–6 Poisson 过程；Lecture 7–9 有限状态 Markov 链、特征结构与奖励；Lecture 10 更新过程。
- 题目改编边界：自行设置转移矩阵、到达率和时刻，计算有限步概率、平稳分布或等待时间。

### `mit_ocw_18_04`

- 标题/机构：*Complex Variables with Applications*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-04-complex-variables-with-applications-spring-2018/)；[讲义资源](https://ocw.mit.edu/courses/18-04-complex-variables-with-applications-spring-2018/download/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：复分析。
- 可定位章节：Topic 1 复代数；Topic 2 解析函数；Topic 3–4 线积分与 Cauchy 积分公式；Topic 5 调和函数；Topic 10 保形映射；Topic 11 辐角原理；课程资源还包含级数与留数主题。
- 题目改编边界：自行选择函数、围道和区域，计算导数、积分、留数、级数收敛半径或零点数。

### `mit_ocw_18_03sc`

- 标题/机构：*Differential Equations*, MIT OpenCourseWare Scholar。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-03sc-differential-equations-fall-2011/)；[课程大纲](https://ocw.mit.edu/courses/18-03sc-differential-equations-fall-2011/pages/syllabus/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：常微分方程。
- 可定位章节：Unit I 一阶方程、Euler 法、线性方程与积分因子、自治方程；Unit II 常系数二阶线性方程、特征方程、阻尼与受迫响应；后续 Fourier/Laplace 与一阶系统。
- 题目改编边界：新设初值与系数，求显式解、稳定性或一个标准方法步骤。

### `mit_ocw_18_102`

- 标题/机构：*Introduction to Functional Analysis*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-102-introduction-to-functional-analysis-spring-2021/)；[讲义与阅读目录](https://ocw.mit.edu/courses/18-102-introduction-to-functional-analysis-spring-2021/pages/lecture-notes-and-readings/)；[课程大纲](https://ocw.mit.edu/courses/18-102-introduction-to-functional-analysis-spring-2021/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：泛函分析。
- 可定位章节：Lecture 1 Banach 空间；Lecture 2 有界线性算子与对偶；后续 Hahn–Banach、Lp 空间、Hilbert 空间、紧/自伴算子与谱定理。
- 题目改编边界：用有限维或经典序列空间中的新向量/算子实例考查范数、算子范数、投影与完备性。

### `mit_ocw_18_303`

- 标题/机构：*Linear Partial Differential Equations*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-303-linear-partial-differential-equations-fall-2006/)；[课程大纲](https://ocw.mit.edu/courses/18-303-linear-partial-differential-equations-fall-2006/pages/syllabus/)；[资源目录](https://ocw.mit.edu/courses/18-303-linear-partial-differential-equations-fall-2006/resources/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：偏微分方程。
- 可定位章节：一维热方程与分离变量、Fourier 级数和 Sturm–Liouville；一维波动方程与特征线；Laplace/Poisson 方程、Fourier 变换和 Green 函数。
- 题目改编边界：自行设置简单边初值条件，验证或写出一个可直接代回检查的经典解。

### `mit_ocw_18_905`

- 标题/机构：*Algebraic Topology I*, MIT OpenCourseWare。
- 公开 URL：[课程资源](https://ocw.mit.edu/courses/18-905-algebraic-topology-i-fall-2016/resources/)；[讲义目录](https://ocw.mit.edu/courses/18-905-algebraic-topology-i-fall-2016/resources/lecture-notes/)；[课程大纲](https://ocw.mit.edu/courses/18-905-algebraic-topology-i-fall-2016/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：非基础及进阶课程。
- 可定位章节：Lecture 1–2 奇异单形、链与同调；Lecture 3–4 范畴、函子、自然变换；Lecture 14–18 CW 复形与 Euler 示性数；Lecture 20–24 张量、Tor、Hom 与泛系数定理。
- 题目改编边界：只选可由基础定义直接核验的小型链复形、Euler 示性数或函子性质，不复制问题集。

### `mit_ocw_18_06`

- 标题/机构：*Linear Algebra*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/)；[课程大纲](https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：高等代数。
- 可定位章节：消元与 LU、四个基本子空间、最小二乘、Gram–Schmidt、行列式、特征值/特征向量、对称与正定矩阵、线性变换与 SVD。
- 题目改编边界：自行构造低阶矩阵，计算特征结构、最小多项式或相似性相关量。

### `mit_ocw_15_053`

- 标题/机构：*Optimization Methods in Management Science*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/15-053-optimization-methods-in-management-science-spring-2013/)；[课程大纲](https://www.ocw.mit.edu/courses/15-053-optimization-methods-in-management-science-spring-2013/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：运筹学。
- 可定位章节：线性规划、整数规划、网络流与启发式、决策树；课程大纲给出相应模块。
- 题目改编边界：自行设置二维线性规划或小网络参数，用枚举顶点/流量守恒直接核验答案。

### `mit_ocw_18_100a`

- 标题/机构：*Real Analysis*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://www.ocw.mit.edu/courses/18-100a-real-analysis-fall-2020/)；[讲义与阅读目录](https://www.ocw.mit.edu/courses/18-100a-real-analysis-fall-2020/pages/lecture-notes-and-readings/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：数学分析。
- 可定位章节：Lecture 23 点态/一致收敛；Lecture 24 Weierstrass M-test 与极限交换；Lecture 25 幂级数和 Weierstrass 逼近定理。
- 题目改编边界：使用新函数列判断点态/一致收敛，并给出可由上确界直接核验的答案。

### `mit_ocw_18_901`

- 标题/机构：*Introduction to Topology*, MIT OpenCourseWare。
- 公开 URL：[课程页](https://ocw.mit.edu/courses/18-901-introduction-to-topology-fall-2004/)；[课程大纲](https://ocw.mit.edu/courses/18-901-introduction-to-topology-fall-2004/pages/syllabus/)。
- 许可：MIT OCW CC BY-NC-SA 4.0，个别另行标注内容除外。
- 覆盖方向：拓扑学。
- 可定位章节：拓扑空间与连续函数、连通性、紧致性、分离公理，以及基本群等后续主题。
- 题目改编边界：选择有限拓扑或实线上的简单子集，依据开集、闭包、内部、连续和紧致的定义直接判断。

## 数据项最小溯源约定

为使每道题可以回查，建议每个 JSONL 数据项至少包含：

- `source_id`：必须对应本目录中的稳定标识；
- `source_url`：指向对应课程/手册页面；
- `source_ref`：具体到讲次、章节或手册编号；
- `adaptation`：固定说明为“基于定义/定理的原创参数化改编”，不得暗示复制原题；
- `verification`：简短记录答案的独立推导式、代回结果或枚举依据。

本来源目录只确认公开性、机构归属、许可页面和主题覆盖。最终 112 行数据仍需通过：总量与 18 方向计数、字段完整性、题干去重、答案数学复核，以及评测器不向 `solve` 泄露 `subject`/`answer` 的接口隔离测试。

## 冻结数据集实际使用的来源

上面的分布表是研究阶段的建议映射；冻结文件
`sample_data/public_regression_112.jsonl` 以每行的 `source` 字段作为稳定
`source_id`。下表是实际键值，必须以此表与逐题 `source_url` 为准：

| `source` | 公开资料 | 覆盖方向 | 许可或使用依据 |
|---|---|---|---|
| `mit_ocw_6_042j` | MIT OCW *Mathematics for Computer Science* | 离散数学、生成函数 | MIT OCW CC BY-NC-SA 4.0 |
| `mit_ocw_18_330` | MIT OCW *Introduction to Numerical Analysis* | 数值分析 | MIT OCW CC BY-NC-SA 4.0 |
| `mit_ocw_18_125` | MIT OCW *Measure and Integration* | 测度积分 | MIT OCW CC BY-NC-SA 4.0 |
| `mit_ocw_18_950` | MIT OCW *Differential Geometry* | 微分几何 | MIT OCW CC BY-NC-SA 4.0 |
| `random_services` | Kyle Siegrist, *Random* | 概率论、随机过程、统计推断、线性回归 | 站点 Rights and Permissions 声明为 Creative Commons，可改编并要求署名与回链 |
| `judson_aata` | Thomas W. Judson, *Abstract Algebra: Theory and Applications* | 抽象代数 | 作者维护的自由教材；逐题仅引用定义/章节，不复制习题 |
| `mit_ocw_18_04` | MIT OCW *Complex Variables with Applications* | 复分析 | MIT OCW CC BY-NC-SA 4.0 |
| `lebl_diffyqs` | Jiří Lebl, *Notes on Diffy Qs* | 常微分方程、偏微分方程 | 作者页声明为可再分发、可修改的 OER；本集不复制书中习题 |
| `mit_ocw_18_102` | MIT OCW *Introduction to Functional Analysis* | 泛函分析 | MIT OCW CC BY-NC-SA 4.0 |
| `stacks_project` | The Stacks Project, Tensor Products | 非基础及进阶课程 | GNU Free Documentation License；本集只引用定义 |
| `mit_18_700` | MIT OCW *Linear Algebra* 18.700 | 高等代数 | MIT OCW CC BY-NC-SA 4.0 |
| `mit_ocw_15_053` | MIT OCW *Optimization Methods in Management Science* | 运筹学 | MIT OCW CC BY-NC-SA 4.0 |
| `lebl_basic_analysis` | Jiří Lebl, *Basic Analysis* | 数学分析 | CC BY-NC-SA 4.0 / CC BY-SA 4.0 双许可 |
| `stacks_project_topology` | The Stacks Project, Topology | 拓扑学 | GNU Free Documentation License；本集只引用定义 |

这 112 道题均由本项目重新选择对象、参数和问法；`source_ref` 只定位知识点，
`verification` 是独立验算，不表示题面来自该资料的原习题。
