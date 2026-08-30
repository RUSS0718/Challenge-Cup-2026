# PRE0-JUDGE-001 预注册：双判分器格式校准

- 窗口 ID：`PRE0-JUDGE-001`
- 类型：`STRUCTURAL_ONLY`，**零模型调用**
- 预注册冻结时间：2026-08-30（语料构建与运行之前）
- 上位规范：`math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6、§4.3
- 依据：`math_agent_evaluation_final_report_2026-08-29.md`（13 判分器系谱与共识表示）、
  `local_evaluation_benchmark_audit_2026-08-29.md` §2.4（双口径定位）

## 1. 假设与动机

外部题集（MATH-500/OlymMATH/HMMT）的答案类型（根式、集合、区间、不等式、元组、
矩阵、单位）远超本仓保守 judge 的覆盖；提交契约又要求 `final_response` 在**未知**
官方判分器下稳定可判。本窗口用 120 个固定合成案例量化三个判分器在 12 类答案上的
行为差异，并验证 ARH 双形态在两类抽取假设下收敛到同一 canonical。

## 2. 语料（冻结）

`cases_120.jsonl`：12 类 × 每类 10 例 = 120 例。类别配比每类固定
`4 equivalent + 3 non_equivalent + 3 unparseable`。12 类：整数、分数/小数、根式、
符号表达式、无序集合、区间、不等式、元组/向量、矩阵、选择项、单位/百分比、
截断/占位符。字段：`case_id, answer_type, category, gold, pred_response, note`。

- `gold`：该题的规范标准答案字符串。
- `pred_response`：一个完整 `final_response` 形态字符串；equivalent 类为
  gold 的替身表示（如 `0.5` vs `\frac{1}{2}`），non_equivalent 类为明确错误的
  近邻答案（如差一个符号/差 1），unparseable 类为截断推理文本、占位符
  （`[答案]`、`TODO`）、空串或噪声。
- 语料写入后计算整体 SHA-256 并记入 manifest；此后不得改写（发现错例只能作废
  该 case_id 并在结果中标注，不得就地修改后复用旧 hash）。

## 3. 三个判分器（全部只读实现，不进 requirements.txt）

| ID | 实现 | 口径 |
| --- | --- | --- |
| J1 `contract` | `user_agent.extract_final_answer`（位置抽取，boxed 兜底）→ `normalize_answer` → `scripts/evaluate_dev.judge_correct` | 提交契约保守三态 |
| J2 `hendrycks` | boxed 抽取 → hendrycks `strip_string` 归一化 → 字符串相等（lm-eval hendrycks_math 移植，文件头注明来源） | 字符串相等族 |
| J3 `math_verify` | 固定版本 Math-Verify：`parse(pred)` 失败→fail-closed；`verify(gold, pred)` 方向固定 gold 在前 | 解析+符号等价族 |

J3 版本在运行前 `pip install` 到 `.venv`（仅本地评测环境），版本号与安装 hash
记入 `run_manifest.json`；**不写入 requirements.txt**。

每例判定输出 ∈ {`correct`, `incorrect`, `unknown`, `unparseable`}；
J1 的 `unknown` 与 J3 的 `unparseable` 都是合法 fail-closed 输出。

## 4. 通过门（预注册，判定顺序即列序）

1. **gold self-score 120/120（每个判分器独立）**：对 120 个 gold 构造双形态
   gold_response（`最终答案：{gold}\n$\boxed{{{gold}}}$`，ARH 冻结发射格式），
   `J(gold_response, gold) == correct` 必须 120/120。
2. **明确错误假阳性 0（每个判分器独立）**：任一 `non_equivalent` 例被判为
   `correct` 即失败。
3. **不可解析 fail-closed**：`unparseable` 例无未捕获异常外泄、无 traceback、
   且输出 ∈ {`incorrect`,`unknown`,`unparseable`}（判 `correct` 即失败）。
4. **ARH 双形态一致性**：对全部 120 个 gold 的双形态 gold_response，
   位置抽取 canonical == last-boxed（`_extract_boxed_answers[-1]`→normalize）
   canonical；任一不一致即失败（记录 case_id）。
5. **记录项（不设门）**：各判分器在 `equivalent` 类上的 correct/unknown 率
   （coverage）、三类答案上 J1/J2/J3 两两差集清单、逐类型 coverage 表。
   **不得为提高判分器间一致率调整任何阈值或归一化规则。**

## 5. VOID 与停止条件

- 门 1–4 任一失败 → 本窗 `VOID`：结果文档记录失败清单；只有当失败根源是
  **校准脚本/语料构造 bug**（非 judge 阈值问题）时，允许修复后整窗重跑一次并
  记为 attempt=2；若仍失败 → Pre-P0 停止，评测协议进入 `BLOCKED` 待处置。
- 门 5 的差集只入报告；任何"顺手修 judge"行为都违反本预注册。

## 6. 产物

`run_manifest.json`（python/sympy/math-verify 版本、语料 hash、运行时间戳）、
`pre0_judge_result.md`、逐例机器可读结果 `judge_results.json`。

## 7. 明确不做

- 不修改 `user_agent.py`、`evaluate_dev.py` 的任何判分/抽取实现。
- 不把 Math-Verify 写入提交依赖；不据此调整 `final_response` 模板（那是
  ARH 的职责，且 ARH 格式本窗视为冻结输入）。
- 零模型调用；官方判分器仍为黑盒，本窗结论只覆盖三个已实现口径。
