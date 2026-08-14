# 13.2 实验 E：非数值题型 Prompt 协议收敛（消除冲突源）

## 实验目的

C2+D 与 temperature 实验已证明：thinking 泄漏是 InternLM 对 derivation/proof/
explanation 类任务的固有行为，与采样温度无关。本实验从**产生端**消除已知的
Prompt 冲突源，验证「模型为什么持续产生 thinking」是否能靠协议收敛解决——
而非继续在抽取/重建层猜测 thinking 文本长什么样。

## 改动（只动 Prompt 协议，其余全保持）

- `temperature=0.6`、`max_tokens=3072`、`workers=3`、C2 抽取器 / D 重建器 /
  重试 / P2 / P3 全部不动。
- 三个 system prompt 收敛：
  - 响应必须从「最终答案：」开始，只含两个区块（答案 + 正文）；
  - 正文从「完整推导/证明/解释」改为「**必要且充分的可核验步骤 / 正式证明 /
    核心解释**」；
  - 新增统一禁令：不复述题目、指令或格式，不输出分析计划、Thinking Process、
    自我检查或语言选择说明。
- 非数值题型 user message 删除「请给出完整解答」（诱发长 thinking）与
  「候选编号」（诱发元分析），只保留「题目：{problem}」；数值题型不变。

## 结果（冻结集 48 题，双轮，workers=3）

| 指标 | 0.6 基线（C2+D 协议） | 实验 E |
| --- | ---: | ---: |
| thinking 泄漏率 | 29.2% / 25.0% | **33.3% / 35.4%**（反升） |
| final_response 污染率 | 16.7% / 12.5% | 12.5% / 18.8% |
| length 率 | 33.3% / 27.1% | 33.3% / 35.4% |
| 整体准确率 | 50.0% / 58.3% | 47.9% / 54.2% |
| **宏平均** | **62.2%** | **59.7%**（−2.5pp） |

| 题型 | 基线 | 实验 E |
| --- | ---: | ---: |
| choice | 91.7% | 83.3% |
| fill_blank | 100% | 100% |
| calculation | 91.7% | 100% |
| derivation | 85.0% | **70.0%** |
| proof | 0% | 0% |
| explanation | 5.0% | 5.0% |

## 关键发现：冲突源被消除，但 thinking 换了内容继续存在

实验 E 的改动**局部有效**——「候选编号」元分析从 thinking 中消失：

- 0.6 基线（C2+D）里，模型的 thinking 反复分析「*候选编号：0 (Candidate
  Number: 0), which seems like metadata or a tag…*」；
- 实验 E 删掉「候选编号」后，这类元分析在 round1 残留 0、round2 残留 1。

但 thinking 泄漏**总量不降反升**（29–25% → 33–35%），残留 thinking 换成了
别的形式：分析题目结构（*Since the question asks for two things…*）、复述
指令（*…"推导：" (Derivation:). No other text…*）。说明 thinking 不是某个
具体措辞诱发的，而是 InternLM 对「完整推导/证明/解释」类任务的**固有行为**。

## 结论：实验 E 未达晋升门槛，Prompt 压制语已到天花板

| 门槛 | 结果 |
| --- | --- |
| thinking 泄漏 ≤15% | ❌ 33–35%，反升 |
| final_response 污染 ≤5% | ❌ 12.5–18.8% |
| length ≤30% | ❌ 33–35% |
| derivation 不回退（~80%） | ❌ 70.0% |
| choice/fill/calc 无稳定回退 | ⚠️ choice 91.7→83.3 |

按实验前锁定的分流规则——「若 thinking 仍在 20% 以上，则不再继续堆叠压制语」，
实验 E 判定**失败**，停止继续堆叠压制语。

## 下一步：实验 F（最后一个有限范围的安全重建）

进入用户预定义的有限范围抽取/重建实验 F，且**不再**堆叠正则、**不**为本地
proof/explanation 分数抓取「最后一个数字」：

1. 只删除带明确结构标题（`Thinking Process:`、`Analysis:` 等）的元文本；
2. 只裁剪真实答案块之前的内容；
3. 正文内部没有明确结构边界时不做关键词级删除；
4. 两次调用都没有真实答案块时保留原始响应兜底；
5. 若 E + 安全版 F 都达不到 5% 污染门槛，接受这是当前模型能力边界，停止堆
   正则、不启动 4096、不恢复多候选/P3。

## 原始数据

- `docs/13_2/expE_round1.json` / `expE_round2.json`（实验 E 双轮）
