# V4-HARD20-DUAL-001 实验结果

状态：**EXPLORATORY_NO_WINNER / NO_PROMOTION**

## 1. 实验上下文

- 预注册：本目录 `preregistration.md`
- 题集：`official_like_hard20_v1`，20 题（OlymMATH hard 12 + AIME 2024 8）
- 题集 SHA-256：`3cf90e65ef9239a70d9675b3807a01692d19aef27fa7cd1e5ffcefdc70ef12dd`
- 调度：单轮、同题交错、workers=3、请求超时 300s、硬停止 180 分钟
- 实际耗时：`3276.4s`（约 54.6 分钟）
- 总调用上限：120；实际 solve 数 40（每臂 20；各方法内部最多 4/2 次模型调用）
- 本窗**不含官方基线臂**，因此不能产生相对 `hetero_k5` 的正式能力结论。

## 2. 两候选结果

| 指标 | condition_checked_selection_v1（KCV） | plan_solve_compact_v1（PS-C） |
|---|---:|---:|
| 完成题数 | 20/20 | 20/20 |
| native correct | **2** | 1 |
| native incorrect | 1 | 2 |
| native invalid | 17 | 17 |
| model error | 0 | 0 |
| 平均模型调用 | 3.50 | **1.65** |
| 平均耗时 | 396.9s | **80.6s** |
| OlymMATH correct | 0/12 | 0/12 |
| AIME 2024 correct | **2/8** | 1/8 |

配对差异（KCV − PS-C）：
- 候选 KCV 独胜 `b=2`；PS-C 独胜 `c=1`；净正确数 `+1`；
- 双侧 exact sign test `p=1.0000`（不显著）；
- KCV 平均调用数约为 PS-C 的 2.12 倍（超过 1.10 成本比较门）。

## 3. 门控判定

| 门 | 判定 |
|---|---|
| 完整性（40/40、两臂各20、唯一题20） | PASS |
| 健康（两臂 model error 0%） | PASS |
| 候选胜负（净胜至少2题） | FAIL（净胜1题） |
| 显著性（exact sign test p<0.05） | FAIL（p=1.0000） |
| invalid+error 比较 | PASS（两臂均17 invalid、0 error） |
| 成本（优先候选平均调用≤另一臂×1.10） | PS-C 成本占优；KCV 不通过 |
| 主要子集不明显净负 | 两者 OlymMATH 均 0/12；AIME KCV +1，描述性信号 |

## 4. 处置

- 本窗完整、健康，但**没有满足预注册优先候选条件的 winner**；定级：
  **`EXPLORATORY_NO_WINNER / NO_PROMOTION`**。
- KCV 的 +1 correct 不足以抵消未达净胜 2、显著性失败与 2.12× 调用成本；PS-C 只具成本优势，正确数更低，亦不能晋升。
- 不修改 `SUBMISSION_CONFIG`，不申请 official canary，不进入 core120。
- `condition_checked_selection_v1` 与 `plan_solve_compact_v1` 均不得以本窗结果宣称超过
  官方健康基线 `hetero_k5 @ 25f99b5`。
- 若未来重启，必须提出机制实质变化、新 method ID 与新预注册；不得在本窗结果上追加第二轮
  以追求显著性（原预注册明确第 2 轮不是必需项，且启动前需另行写入 manifest）。
