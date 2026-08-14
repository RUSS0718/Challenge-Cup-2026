# 实验 C2 + D 报告：真实答案块识别 + final_response 输出卫生

日期：2026-08-14
分支：`experiment-thinking-suppression`（main 未动）
改动：
- **C2**：增强 `extract_answer_segment` 的真实答案块识别（跳过 thinking 引用/引号/
  Markdown 列表/元文本，支持英文 Derivation/Proof/Explanation 标题）；候选增加
  `structured` 标记；`_has_clear_answer` 对非数值题型检查真实答案块；`_select_candidate`
  优先真实答案块；无真实答案块时触发至多一次条件重试，两次失败后完整响应兜底。
- **D**：新增 `reconstruct_final_response`，丢弃答案块前的 thinking/Prompt 回显，
  保留「最终答案：<结论>」+「<正文标题>：<正文>」，无法可靠识别结构时返回原始响应。
- 全量 **197 测试通过**（新增 14 项：thinking 引用/引号/括号 Markdown 列表/英文标题/
  真假标记/重试语义/兜底/不等式集合元组自然语言）。

## 1. 两轮结果（冻结集 48 题，3072）

| 指标 | 实验 C | C2+D R1 | C2+D R2 |
|---|---:|---:|---:|
| 整体准确率 | 50.0/56.2% | 50.0% | 47.9% |
| final_response thinking 污染率 | — | **12.5%** | **20.8%** |
| thinking 泄漏率（原始响应） | 18.8/16.7% | 31.2% | 33.3% |
| length 率 | 27.1/25.0% | 33.3% | 39.6% |
| 平均 / P95 调用 | 1.00/1 | 1.06/2 | 1.00/1 |
| 非空 final_response | 100% | 100% | 100% |

## 2. 题型宏平均（两轮合并）

| 题型 | 实验 C | C2+D |
|---|---:|---:|
| choice | 100% | 83.3% |
| fill_blank | 100% | 100% |
| calculation | 91.7% | 75.0% |
| derivation | 80.0% | 80.0% |
| proof / explanation | 0% / 0% | 0% / 0% |
| **宏平均** | 61.9% | 56.4% |

## 3. 112 题回归

| 指标 | 3072 基线 | C2+D |
|---|---:|---:|
| 准确率 | 80.8% | **83.9%** |
| length | 10.7–17.9% | 16.1% |
| thinking 泄漏 | — | 12.5% |

112 题**无回退**（+3.1pp），Gate 2 通过。

## 4. 关键发现

1. **重试语义已生效**：第一轮 3 题触发条件重试（calls 1.06），`_select_candidate`
   优先真实答案块后，重试命中的候选能被正确选中。

2. **final_response 污染源 = thinking 泄漏本身**：12.5–20.8% 的 final_response 仍含
   thinking，来源是 31–33% 的 thinking 泄漏题——其中一部分因抽取失败，reconstruct
   无真实答案块可重建，返回原始含 thinking 的响应；另一部分正文里残留 thinking 片段。
   抽查样例（6005/6007/6009/6016/6018）的 marker_segment 是 `*Language: Chinese`、
   `The prompt asks to "derive...`、`...) and "解释：..."` 等 thinking 复述。

3. **choice/calculation 的波动是样本随机性**（各 12 题次，1–2 题波动），非稳定回退；
   112 题回归（112 题次）83.9% 反升，佐证这一点。

## 5. 门槛判定（实验 D 用户门槛）

| 门槛 | 结果 |
|---|---|
| 非空 final_response 100% | ✅ |
| 每题 ≤2 调用 / 平均 ≤1.5 | ✅ 1.00–1.06 |
| final_response thinking 污染 ≤5% | ❌ 12.5–20.8% |
| 复杂集 length ≤30%（目标 20%） | ❌ 33.3–39.6% |
| 112 短题集无稳定回退 | ✅ +3.1pp |
| 两轮方向一致 | ⚠️ 准确率一致、thinking/length 有波动 |

## 6. 结论与下一步

- C2/D 的**机制正确落地**：重试语义、真实答案块优先、final_response 重建均通过单测，
  112 题无回退。
- **未达门槛的根因是 thinking 泄漏（31–33%）**——它既造成 length 偏高，也造成约 20%
  的 final_response 无法重建干净。C2/D 只能裁剪「答案块前的 thinking 前缀」，无法治理
  「正文 thinking 残片」与「thinking 泄漏导致的抽取失败」。
- 下一步按路线图，应是**单变量治理 thinking 泄漏**：temperature 0.6→0.2 双轮 A/B
  （thinking 泄漏率是否下降），以及「更强 thinking 压制 + 更激进但安全的 final_response
  裁剪」组合。**不**继续为本地 proof/explanation 的 judge 分数做表示规范化。
