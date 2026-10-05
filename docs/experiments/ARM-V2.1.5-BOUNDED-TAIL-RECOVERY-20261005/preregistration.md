# ARM-V2.1.5-BOUNDED-TAIL-RECOVERY-20261005

状态：`OPEN`

## 假设

官方评测中的主要可观测损失是长输出在 `finish_reason=length` 时没有形成可判定的
`final_response`。当前 v2.1.4 已能在“唯一候选 + 明确 `Final answer`/唯一 boxed 标记”时
保留结构完整的截断尾，但信任门仍把它交给普通 Challenger。一个只确认该候选的短请求，
可能减少 `invalid`，同时避免把不相关的第二次完整解题引入冲突。

## 唯一变量

- 候选：`arm-v2.1.5-bounded-tail`。
- 对照：`arm-v2.1.4-cfr`，配置、提示词、调用上限和 token 预算保持一致。
- 候选只有在主调用满足以下全部条件时才改变第二次请求：单一候选、解析状态为截断、
  `answer_complete_reason=answer_complete_truncated_tail`、来源为 `arm_primary`、结构有效。
- 触发后最多发起一次确认请求，确认请求最多 1,024 tokens；只有确认答案与主候选等价时
  才形成共识。确认缺失、UNKNOWN 或冲突时保留已有安全候选，不替换为确认结果。
- 不满足条件的题目继续使用 v2.1.4 Challenger 路径。

## 数据与调度

使用仓库内、允许发送到已配置端点的三类本地题集，标准答案只留在宿主评分器：

- `official_like_hard20_v1`：15 题，分三组，每组 5 题；
- `eval_112`：5 题；
- `public_regression_112`：5 题。

共 10 轮、50 条记录，按候选/对照交替排列：B01/B02、B03/B04、B05/B06、B07/B08、
B09/B10。共享端点串行使用一个矩阵运行器，题内并发不超过 3；每轮不超过 5 题，gold
不进入 Agent。运行范围固定为 `local_replay`，不代表官方隐藏集成绩。

## 预注册门

1. **VOID 门**：数据集哈希、题目数量、manifest 范围字段缺失，或任一臂出现模型错误率
   大于 10%，则窗口无能力结论。
2. **激活门**：候选必须至少触发一次 `bounded_tail_confirmation`；若 0 次，仅记录为
   工程未激活，不据此判定收益或失败。
3. **卫生门**：候选相对对照的 `incorrect` 不得增加超过 2，平均调用数不得增加超过
   0.5，且单题调用不得超过现有 v2.1.4 上限。
4. **探索收益门**：候选在 50 题上至少减少 2 个 `invalid`，且没有 `correct → incorrect`
   的净损失；这是继续复验的门，不是默认晋升门。
5. **晋升边界**：即使通过探索门，也不得自动修改 `SUBMISSION_CONFIG`、发布 main 或
   宣称官方能力提升；需要第二个独立窗口和接口验收。

## 记录方式

每轮写入 `artifacts/arm-v215-bounded-tail-recovery-20261005/<round>/`，长期提交只保留
预注册、压缩结果和处置；完整 answers、report、manifest 和 raw 响应留在被忽略的
`artifacts/` 目录。实验结束后先更新 `docs/excluded_approaches.md` 与机器注册表，再决定
是否提出下一轮。
