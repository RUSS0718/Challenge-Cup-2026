# P1 在新基线（~11/23）上提高剩余题正确率

日期：2026-07-29  
状态：完成 — 决策：**ADOPT answer-first 默认 Prompt**

## 1. 错误重分类

来源：P0.3 三轮 1024-token 基线（12/11/10）。

| 类别 | 证据 | 可修复性 |
| --- | --- | --- |
| 模型求解/输出收敛不稳定 | 始终错误 idx 0,1,2,10,15,20,22；大多题有候选且 `selected` | 高（Prompt） |
| 有效答案未被抽取 | 仅偶发 `answer_not_extractable` | 低 |
| 答案组/审核选择错误 | 无稳定证据 | 低 |
| 全候选无效 | 1024 下几乎为 0 | 无 |

**最高收益类别**：模型求解错误/输出收敛不稳定 → 最小 Prompt A/B。

## 2. 单变量改动

仅改变 Policy Prompt，其他全固定：

- `max_tokens=1024`、`policy_sample_times=3`、`max_model_calls=6`
- 实验开关全关
- 新 Prompt：优先收敛到答案，禁止复述题意/格式说明

## 3. 结果

| 轮次 | 准确率 | 平均调用 | 平均延迟 | 超时 | 空响应 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 旧基线 P0.3 三轮 | 12 / 11 / 10 | ~4.6 | ~30s | 0 | 0 |
| AF main | **12/23** | 4.52 | 28.5s | 0 | 0 |
| AF rerun1 | **15/23** | 4.35 | 28.7s | 0 | 0 |
| AF rerun2 | **12/23** | 4.30 | 28.1s | 0 | 0 |

- 两轮复评均 **> 11/23**，满足采纳门槛。
- 三轮均值约 **13/23 (56.5%)**，相对旧 ~11/23 约 **+8.7pp**。
- 始终正确：idx 5,7,9,13,17,19；始终错误：idx 0,1,2,10（硬题，仍待后续）。

## 4. 决策

**ADOPT**：将 `POLICY_PROMPT` 替换为 answer-first 文案；`ANSWER_FIRST_POLICY_PROMPT` 作为同义别名保留，CLI `--answer-first-prompt` 仍可用（现与默认等价）。

## 5. 报告文件

- `docs/p1/p1_error_reclassification_2026-07-29.md`
- `docs/p1/p1_answer_first_main_2026-07-29.json`
- `docs/p1/p1_answer_first_rerun1_2026-07-29.json`
- `docs/p1/p1_answer_first_rerun2_2026-07-29.json`
