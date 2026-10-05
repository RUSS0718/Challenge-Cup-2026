# Invalid Rescue 实验归档与默认路径回退

日期：2026-10-04
项目：Challenge-Cup-2026
回退目标：GRH v1.1 发布代码（`43a02da`）及其已核验的 119 题运行工作树
官方基线工件：`artifacts/official_proxy_20261002/runs/current_branch_grh_proxy221_intern_s2_r1/`

## 回退结论

默认运行代码已回到 GRH v1.1 的已核验版本。该版本的发布核验清单记录了 119 个正确、32 个错误、70 个无效；其运行 manifest 记录 `git_head=91b66b3167458fd5c117f7068f32227f7a33f7d2`，并记录工作树有 10 个经过哈希核对的运行时文件。`docs/releases/grh-v1.1-20261002/verify.py` 在当前工作树通过，说明发布清单中的 10 个源码哈希、`arm-v2.1.3-off` 默认配置和 3 路并发公开 client 合同仍一致。

这里把 `91b66b3` 称为“119 题版本”是运行证据口径；实际可复现代码锚点是 `43a02da` 发布树加 manifest 中列出的工作树文件。不能把当前 EACL 分支的 HEAD 当作该基线。

## 221 题基线与 invalid 组成

保存的官方代理基线为 221 题：`correct=119`、`incorrect=32`、`invalid=70`。invalid 主因审计分布为：

| 主因 | 数量 | 解释 |
|---|---:|---|
| R1 | 8 | 没有闭合候选，属于 solver/推理失败 |
| R2 | 19 | 多个候选冲突，没有可证明的裁决 |
| R3 | 21 | 已有候选但最终决策/收束失败，常伴随截断 |
| R4 | 0 | 结构或解析拒绝不是这份基线的主因 |
| R5 | 18 | 有非空答案，但冻结 evaluator 返回 `unknown` |
| R6 | 4 | 截断、超时或运行健康问题 |

R5 的 `unknown` 不能直接改写为正确；R1/R3/R6 也不能靠序列化器补出没有形成的答案。

## 尝试过的方案与处置

### 1. EACL v1.3 控制平面

把推理、候选账本、确定性验证、保守裁决和最终序列化拆开，并用 `UNKNOWN/ABSTAIN` 处理冲突或不可证明候选。221 题对照审计得到 `invalid→correct=13`、`invalid→incorrect=8`、`correct→invalid=14`，净正确数变化为 0；因此它改善了可审计性，但没有建立默认提分证据。

### 2. Round 2：三角根集合、冲突裁决、矩阵/分数表面

尝试了完整根集合与逐根验证、唯一 deterministic `PASS` 才裁决、多解/矩阵/向量形状保护和分数规范化。按冻结 evaluator 的安全口径，计数的 `Invalid Rescue=0`；候选回放中的单个正例没有同时满足 evaluator 可判定和安全裁决条件。真实 smoke 没有错误增加，也没有形成可计分 rescue，故只作为实验代码归档。

### 3. Round 3：proof numeric gate

对“证明/推导并求数值”增加 mixed-proof 识别、闭合候选、未截断和 deterministic `PASS` 门。严格 frozen-before → production-after 回放为：

- 全量：`119/31/71 → 105/29/87`，`Invalid Rescue=4`、`Invalid Damage=0`、`Correct Damage=18`、净正确数 `-14`；
- 排除 `PROOF` host gating 的 scope：`100/30/66 → 104/29/63`，净变化 `+4`，但这不能抵消全量生产路径的 18 个正确损失。

R2 单一归因回放覆盖 19 题：只有 1 个 deterministic unique pass，且冻结 evaluator 对它仍为 `unknown`；另外 2 题 evaluator 对某候选判正确但没有唯一可证明裁决。因此没有启用强行 resolver。

结论：proof gate 不进入默认路径。

### 4. Round 3：surface serializer

尝试了有限的 evaluator-friendly 表面转换：显式矩阵/向量形状、单一顶层商转 `\\frac`、安全的括号分组，以及去掉 assignment 壳。隔离非 `PROOF` scope 的回放观察到 4 个 `invalid→correct`、0 个 damage、净 `+4`；其中 3 个属于 serializer，另一个 `No` 属于独立的 binary extraction。全量结果被 proof gate 的正确损失污染，不能作为默认晋升证据。

当前处置：serializer 和矩阵 shape 规则删除出生产代码；本归档保留可读结论，原始运行工件仍按
`artifacts/<run_id>/` 的忽略目录约定保存，不进入默认发布树。

### 5. Round 3：binary decision extraction

对题面明确要求 yes/no 的通用表面做 paired ablation，启用与禁用臂各 9 题：

| 指标 | 启用 | 禁用 |
|---|---:|---:|
| `invalid→correct` | 1 | 0 |
| `invalid→incorrect` | 0 | 0 |
| `correct→invalid` | 0 | 0 |
| `correct→incorrect` | 0 | 0 |
| `Invalid Rescue` | 1 | 0 |

唯一正例是 `qwen_college_math:exercise.9.3.2` 的 `No` 收束。该结果支持继续研究，但只有 9 题 paired 子集，且没有完整 221 题独立复评；随本次回退一并移除实验实现，不修改默认路径。

### 6. R5 evaluator-surface 审计与 smoke

审计了函数、置信区间端点、symbolic quotient 和多解答案的表面差异。发现的少量 `invalid→correct` 中有 provenance 差异，不能当作安全收益；冻结 evaluator 保持不变，`unknown` 继续 fail-closed。真实 smoke 主要用于观察 SELECT/ABSTAIN、截断和延迟，不产生能力晋升结论。

## 代码清理范围

已从当前工作树生产路径移除本轮 EACL/invalid-rescue 专用模块、入口和测试，包括 `eacl_*`、`answer_contract.py`、`candidate_canonicalizer.py`、`answer_serialization.py`、`exact_equivalence.py`、`matrix_equivalence.py` 及对应实验测试。保留运行工件和实验文档，便于追溯假设、逐题转移和 evaluator 口径；不保留只服务于已否决默认路径的代码闭包。

没有把 gold、answer bank 或题号规则加入运行时。回退后的默认 profile 仍是发布核验中的 `arm-v2.1.3-off`。
本次项目瘦身同时删除了已被永久排除的 method-card RAG、reference-example RAG 和学科 Skill
运行时、1.5 GB 参考模型/向量库、离线检索脚本及其专用测试；`AgentConfig` 不再暴露这些实验开关。

## 验证

- `python docs/releases/grh-v1.1-20261002/verify.py`：通过；10 个运行时文件哈希、默认配置和 3 路并发公开 client 合同一致。
- 实验 raw 结果仍在 `artifacts/`；本文件是提交树中的综合可读归档，避免把临时 JSON 和运行缓存混入发布树。
- 后续若要重新尝试任何 rescue 机制，必须新建独立 method id、预注册单一变量，并在同一 frozen-221 上先完成 paired replay，再考虑真实 API smoke；不能直接把本归档中的局部正例晋升为默认配置。

- `.venv\\Scripts\\python.exe -m pytest -q tests`：1049 passed、4 skipped、183 subtests。
