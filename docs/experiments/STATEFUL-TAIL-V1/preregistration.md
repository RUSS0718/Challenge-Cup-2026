# stateful_tail_completion_v1 实验预注册

状态：**PREREGISTERED / P1_OFFLINE_VERIFIED / FIDELITY_PENDING_USER_GO**
方法 ID：`stateful_tail_completion_v1`
对照基线：`baseline_hetero`（即 `hetero_k5 @ 25f99b5`，官方 Run #5 12/83/17、4h24m 健康锚）
所属阶段：P1 离线实现与回放（已通过）→ P2 fidelity（待用户授权启动）
权威依据：
- `docs/excluded_approaches.md` §六.0e（BTCS 严格帧终止 + 唯一下一步）
- `docs/experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md` §6e Amendment
- 用户 2026-09-03 指导："不再沿用 BTCS/v4/v5 命名。新方法以 hetero_k5 为基线，只修改最后一个失败槽。"

## 1. 假设与单变量定义

### 1.1 核心假设

官方 Run #8 确认官方模型在 4096 上限下有 86.62% 的长推理截断率；多次独立重算（A/B/C）
不断从原题重新求解，导致长题在相似位置重复截断，消耗了 11k completion token/题
却仍产生 99 个 invalid。

**假设**：当四次独立采样均未生成可提取答案时，第五次调用不再从原题重新开始，而是
携带第 4 份未完成响应的**尾段**（≤8000 字符，不带开头），明确要求"继续完成同一条推理，
不要从头重做"，且允许模型正常推演并以现有的明确答案标记或 `\boxed{}` 收束。这样可以在
不增加总调用上限（仍为 5）、不改变前四次行为、不放宽 parser 的前提下，使部分因长度被切断
的题在第五槽完成推演并形成可判答案。

### 1.2 单变量定义（与 hetero_k5 的严格差异）

| 维度 | 对照臂（`baseline_hetero`） | 候选臂（`stateful_tail_completion_v1`） | 单变量差异 |
| --- | --- | --- | --- |
| 总体调用上限 | 5 | 5 | **无** |
| 单次 max_tokens | 4096 | 4096 | **无** |
| 前 4 次调用 | 1 Direct + 1 Alt + 2 Resamples（温度 0.6，task-aware） | 完全相同 | **无（逐字一致）** |
| 早期共识早停 | 3 个等价候选即停 | 3 个等价候选即停 | **无** |
| 答案抽取 | `extract_answer_first` / `extract_final_answer` 显式标记 | 完全相同 | **无（禁止任何正文 salvage）** |
| 非数值题处理 | 实验 F 三状态行解析 | 完全相同 | **无** |
| **第 5 槽触发** | — | 前 4 次**全部**无清晰答案（candidates 为空）且第 4 份响应非空非报错 | **唯一差异** |
| **第 5 槽行为** | 从原题重新发起 Direct 正向推导 | `STATEFUL_TAIL_CONTINUATION_PROMPT` + 携带第 4 份响应尾段 ≤8000 字符，明确要求继续同一推理 | **唯一差异** |
| 续推仍无标记 | fallback | fallback（fail-closed） | **无** |

### 1.3 严格触发条件（三重与门）

1. `enable_stateful_tail_completion == True`；
2. `budget["used"] == 4` 且 `candidates` 为空（前 4 次调用未产生任何可提取答案）；
3. `budget.get("stateful_tail_source")` 非空（第 4 次调用返回了非空字符串；若第 4 次为
   model_error 或空响应，自动回退到基线的 fresh 第 5 槽重算）。

任何一个条件不满足，第五槽行为、Prompt 与基线逐字一致。

## 2. 停机与保护

- **禁止项**：
  - 不开发 v5 finalizer/recovery；
  - 不从原题重新请求短答案帧；
  - 不放宽 parser 从截断正文或末行捞数字；
  - 不增加第 6 次模型调用；
  - 不修改前 4 次调用的 Prompt、温度或分配；
  - 不携带响应开头或超过 8000 字符；
  - 不使用 OlymMATH hard 逐题调优 Prompt。
- **Fail-closed**：续推响应若仍无显式答案标记，直接走 fallback，不产生猜答案行为。
- **并发与时间**：三并发隔离（单次 solve 内 stateful_tail_source 仅通过 budget 字典传递，
  无类字段共享）；严格遵守 `solve_converge_timeout_seconds`（960s）与
  `solve_hard_timeout_seconds`（1080s）。

## 3. P1 离线验证（已完成）

- 测试文件：`tests/test_stateful_tail_completion.py`（11 项测试通过）；
- 全量基线测试：195 项测试全部通过（0 fail, 0 error）；
- 验证内容：
  1. 默认关闭：`SUBMISSION_CONFIG.enable_stateful_tail_completion == False`；
  2. 未触发时 transcript 与基线逐字一致（早期共识、部分候选存在、L0 题）；
  3. 触发时正确切换 Prompt、拼接尾段、携带候选编号；
  4. 尾段截取：超 8000 字符截取尾部、丢弃头部；
  5. 异常保护：第 4 次 model_error 时优雅回退 fresh 重算；
  6. 续推失败 fail-closed：无标记走 fallback；
  7. 四并发 solve 隔离验证通过。

## 4. P2 Fidelity 门（待启动）

- **题集**：fresh 冻结数据集（不得复用 OlymMATH hard）；
- **样本数**：至少 20 个真实触发 continuation 的长推理请求；
- **通过门**：
  1. raw continuation 形成显式答案率 ≥ **60%**（针对已截断题的保守门）；
  2. 错误接受（虚假答案标记/占位符）= **0**；
  3. JSON 格式与非空 `final_response` = **100%**；
  4. mean calls 相对基线增长 ≤ **1.00**（调用槽总数不变）；
  5. 任一健康门（model error > 10%）或 fidelity 门失败立即停止。

## 5. 正式能力门（P2 后续）

顺序：`fidelity → legacy84 → core120×2 → confirm30`
对照：恒为 `baseline_hetero`（hetero_k5 @ 25f99b5）
规则：双轮同题交错；聚类双侧 exact sign test `p < 0.05` 且 `b > c`；各固定数据集不净负；
invalid+error 不增加；mean calls ≤ 对照 × 1.10；官方预计耗时 ≤ 5.5h。

## 6. 预期管理（用户 2026-09-03 评估）

- 降低部分 invalid 的概率：**55%–65%**
- 正式本地门显著击败 hetero_k5 的概率：**35%–45%**
- 最终官方超过 12/112 的概率：**25%–35%**

本预注册是一份机制合理、成本受控的假设检验，不是确定性承诺。
