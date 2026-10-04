# ARM-V2.1.5 length-pressure activation probe — preregistration

状态：`PREREGISTERED / ENGINEERING_ONLY`

## 目的

验证 `arm-v2.1.5-bounded-tail` 的唯一触发门能在可控的截断尾输入上被实际调用，
并确认确认请求的上限和 fail-closed 行为。该探针只验证接线、预算和 trace，不能产生
模型能力、正确率或官方评测结论。

## 唯一变量与对照

- 候选：显式 `arm-v2.1.5-bounded-tail`。
- 对照：同一输入、同一 `arm-v2.1.4-cfr` 配置；不改变正式 selector。
- 唯一变量：主调用返回 `finish_reason=length`、唯一结构有效候选、明确 `Final answer`
  标记的 fixture；不得改写题面、gold 或 evaluator。

## 固定 fixture 与门

使用仓库测试中可审计的脚本 client，至少覆盖四种响应：

1. 截断主候选 + 等价确认：必须出现一次 `bounded_tail_confirmation`，确认请求
   `max_tokens <= 1024`，最终来源为共识；
2. 截断主候选 + UNKNOWN：保留安全候选，不形成共识；
3. 截断主候选 + 冲突答案：保留安全候选，不替换 incumbent；
4. 没有明确答案标记的截断：继续普通 Challenger 路径，不触发确认。

通过条件是四类均与上述预期一致、每个 fixture 最多一次确认、没有越过正式调用上限，
且 trace 记录触发原因和最终来源。任何预算越界、无门槛触发或冲突替换都使探针失败。

## 范围边界

探针使用 `diagnostic`/`local_replay` 范围，0 个官方题集结论，0 个发布动作，0 个
`SUBMISSION_CONFIG` 修改。只有探针通过后，才可另立新的真实端点 activation window；
真实窗口必须重新写 method ID、题集 hash、manifest 和 paired baseline。

## 记录

结果应写入本目录的 `result.md`，包含 fixture 数、触发次数、确认 token 上限、失败原因和
是否允许下一窗口。不得把 fixture 通过写成能力收益。
