# PRE0-JUDGE-001 结果：双判分器格式校准

- 窗口 ID：`PRE0-JUDGE-001`，类型 `STRUCTURAL_ONLY`（零模型调用）
- 运行时间：2026-08-30；attempt = 1（一次通过，dry-run 与正式运行同一语料）
- 预注册：[`preregistration.md`](preregistration.md)
- 判定：**PASS**（门 1–4 全过；门 5 覆盖率与差集已记录、未做任何阈值调整）

## 1. 语料与运行环境（冻结）

- `cases_120.jsonl`：12 类型 × 10 例 = 120 例（每类 4 equivalent + 3
  non_equivalent + 3 unparseable），SHA-256
  `71d8d81d06b63d20d53670fe1d49efd3238ad3d506989c2ff80f006306f3b36f`。
- 构造期修正（均在冻结前完成，符合"写入后不改写"纪律）：
  1. non_equivalent 探针发现 Math-Verify 0.8.0 把 `\%` 转义与 `\text{}` 单位
     在归一化阶段剥除，会造成两类假阳性 → percent 单位类型的 ne 用例改为
     `26%` / `16\text{ cm}` / `0.26`；两个缺陷边界改由结果文档 boundary
     probes 记录（见 §4），不进语料。
  2. 截断样例的尾部提示改为**半截切分**：完整尾随 gold 会被无锚抽取抓到并
     假造 correct；半截后与 gold 必然不等。
- 环境：Python 3.10.20、sympy 1.14.0、math-verify 0.8.0（仅本地 `.venv`，
  不进 requirements.txt）；J3 解析超时禁用（Windows 无 SIGALRM），
  `verify(gold, pred)` 方向冻结 gold 在前。

## 2. 门判定

| 门 | 内容 | J1 contract | J2 hendrycks | J3 math_verify |
| --- | --- | --- | --- | --- |
| 1 | gold self-score（双形态 gold_response） | 120/120 | 120/120 | 120/120 |
| 2 | non_equivalent 假阳性 | 0 | 0 | 0 |
| 3 | unparseable fail-closed 且无异常外泄 | ✓（26 例） | ✓（60 例） | ✓（48 例） |
| 4 | ARH 双形态 canonical 一致 | 120/120 无失败（三 judge 共同前置，位置抽取 vs last-boxed 抽取归一后全等） | | |

- 判分器 `judge_crash` = 0（全 120×3 次 judge 调用无未捕获异常）。

## 3. 覆盖率与差集（门 5，记录不做一致性调优）

总 coverage（120 例）：

| 判分器 | correct | incorrect | unknown | unparseable |
| --- | --- | --- | --- | --- |
| J1 contract（保守三态） | 28 | 11 | 55 | 26 |
| J2 hendrycks（字符串族） | 12 | 48 | 0（设计上无 unknown） | 60 |
| J3 math-verify（符号等价族） | 29 | 43 | 0 | 48 |

equivalent 类上的低覆盖点（correct/total）与主要差集：

- J1 在 interval/tuple/matrix/inequality 上大量 unknown（如 tuple 3/4、choice
  3/4）——本仓保守判分器**无法覆盖**区间、元组、矩阵、不等式，与审计预期一致；
  外部集这些类型必须依赖 native 口径。
- J2 对双形态发射中无 boxed 的 marker/bare 样式全部 unparseable（字符串族不认识
  中文答案句式）；symbolic/set/inequality/unit 全为 0/4。
- J3 对 bare 无锚形式（整数 3/4、tuple marker、radical marker）会抓错片段
  （如 `4\sqrt{15}-14` 抓成 4）——**无锚输入不可信**， boxed/双形态发射是
  正确使用 Math-Verify 的前提。
- 差集规模：J1 vs J3 = 65 例，J2 vs J3 = 24 例，J1 vs J2 = 72 例
  （逐例清单见 `judge_results_attempt1.json`）。差集主体是
  "unknown/incorrect/unparseable 的 fail-closed 语义差异"，非答案翻转。

## 4. boundary probes（非语料案例，仅记录）

| 边界 | gold | pred | J1 | J2 | J3 |
| --- | --- | --- | --- | --- | --- |
| 百分比转义剥除 | `25%` | `0.25\%` | unknown | incorrect | incorrect |
| 单位错配（cm vs m） | `15\text{ cm}` | `15\text{ m}` | unknown | **correct** | **correct** |

结论：**单位错配在本仓任何口径下都不可靠**（J2 remove_right_units 与 J3 归一化
都把单位剥掉只剩数值）。core120_v2 选题必须避免"同数值不同单位"的题面/金标；
若无法避免，该类答案只走 contract 口径并按 unknown 计。

## 5. 对下游的输入

- `final_response` 双形态（`最终答案：X` + `\boxed{X}`）在位置抽取与
  last-boxed 抽取两个假设下收敛同一 canonical（120/120）——ARH 表示纪律
  在三个判分口径下都可判，为 P1 外部层判分提供前提。
- 保守 J1 + native J3 双口径并行可行：J3 不产生假阳性、J1 不产生假阳性，
  两者差集可安全解释为覆盖差异。
- 本窗不改 `SUBMISSION_CONFIG`、不改 runtime、不修改任何 judge 阈值。

## 6. 产物

- `judge_results_attempt1.json`（manifest + 门 + 120×3 逐例 + 差集 + boundary probes）
- `cases_120.jsonl`（冻结语料）+ `build_cases.py`（构造器，含构造期修正记录）
