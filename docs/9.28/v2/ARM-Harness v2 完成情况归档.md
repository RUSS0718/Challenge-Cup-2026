# ARM-Harness v2 完成情况归档

> 归档日期：2026-09-28
>
> 分支：`feat/arm-harness-v2`
>
> 口径：本文件记录第一点与第五点的完成状态、证据边界和后续实验入口。

## 归档结论

| 项目 | 实现状态 | 证据状态 | 当前处置 |
| --- | --- | --- | --- |
| 第一项：ARM endpoint/Agent 隔离诊断 | 首轮连接失败后已完成一次重跑与报告 | 首轮 `VOID_CONNECTIVITY`；重跑 `PARTIAL_ENDPOINT_RESPONSES` | 仅作诊断，不形成单因果结论 |
| 第五项：结果质量审计模块 | 已完成代码、报告拆分和回归测试 | 可对历史 30 题重算 | 作为后续实验的固定审计基座，不等于质量问题已修复 |

本轮没有修改默认提交 profile 或官方提交路径；仅把硬题 runner 的默认 raw 输出
迁移到 `artifacts/<run_id>/`，也没有把 ARM v2 结果晋升为官方能力结论。

## 第一项：ARM-ISOLATION-001 重跑

### 证据

- [首轮无效实验摘要（54/54 connectivity failure）](../../experiments/ARM-ISOLATION-001-20260928/result.md)
- [可读实验报告](../../experiments/ARM-ISOLATION-001-20260928-RERUN/result.md)
- 重跑 `run_id`：`ARM-ISOLATION-001-20260928-RERUN`。逐次请求明细、机器汇总、manifest 与预检文件保留在本地忽略目录 `docs/experiments/ARM-ISOLATION-001-20260928-RERUN/`，不进入 Git。

### 关键结果

- 首轮 54/54 请求均在客户端连接阶段失败，没有测到模型；不能用于 timeout 或 Agent 架构比较。
- 54/54 条计划记录均写入；18 个实验格中 14 个收到过端点响应，共 37/54 次请求收到响应。
- 17 次请求以客户端 `ReadTimeout` 结束，均约在 180 秒触发；没有 connectivity 错误。
- 轻量预检成功：HTTP 200，耗时约 3.39 秒；这只能证明轻量请求可达，不能代表复杂请求的生成或排队健康。
- `max_tokens=2048` 档 18/18 次收到响应，`4096` 档 17/18 次收到响应，`8192` 档仅 2/18 次收到响应；裸端点的 `8192` 档 6/6 次超时。
- workers=3 没有表现出稳定、独立的超时恶化信号；每个实验格只有 3 次重复，不能排除端点负载影响。
- 本题 54 次运行没有 native correct；收到响应并形成答案的记录仍全部判错或不可用。

### 解释边界

本轮支持的结论是：高 token 上限的复杂请求与本地 180 秒读超时同时出现；裸端点在同一 token 档也超时，因此不能把超时归因于 ARM Agent 架构是必要原因。端点计算、排队、传输停滞和本地读超时仍无法仅凭当前客户端日志区分。

本轮不支持以下结论：

- ARM 架构一定导致超时；
- 延长本地 timeout 就能改善数学正确率；
- workers=3 一定是主要原因；
- 当前端点或 Agent 在更大题集上的泛化能力已得到验证。

### 后续实验入口

后续若要做因果定位，应在新实验编号下记录流式首 token、完成时延、服务端 usage/排队信息，随机化条件顺序并增加题目与重复数。旧窗口不追加调参，也不把部分响应改写成完整健康窗。

## 第五项：结果质量审计模块

### 实现入口

- [审计兼容入口](../../../scripts/external_hard_sets_reporting.py)，以及拆分后的
  [判定](../../../scripts/external_hard_sets_judging.py)、
  [qualification](../../../scripts/external_hard_sets_qualification.py) 和
  [汇总](../../../scripts/external_hard_sets_aggregate.py) 模块
- [运行产物适配器](../../../scripts/external_hard_sets_artifacts.py)
- [硬题 runner](../../../scripts/run_external_hard_sets_smoke.py)
- [审计回归测试](../../../tests/test_external_hard_sets_reporting.py) 与
  [runner 回归测试](../../../tests/test_external_hard_sets_runner_report.py)

runner 已将判定和报告逻辑拆出，并通过统一 artifact 边界把默认 raw 输出写入
`artifacts/<run_id>/`；审计模块可以分别统计答案抽取/格式、native 与 contract
判定、timeout 恢复、Agent 阶段健康度、ARM v2 候选可信度与 early-stop、调用成本，
以及 Skill/Claim DSL qualification。

### 已验证的历史重算口径

基于 `ARM-V1-REPLAY-OFF-20260928/answers.jsonl` 的 30 题记录：

- native：8 correct / 14 incorrect / 8 invalid；
- contract：8 correct / 13 incorrect / 9 invalid；
- native/contract mismatch：1 题；
- `contract_extractable` / `format_ok`：21/30；
- 请求总数 50，其中 timeout 16；timeout 后形成终答 8；其中恢复正确 1；
- timeout 后最终 `UNKNOWN` 为 5；无 timeout 但最终弃答为 3；修正记录后的最终 `model_error` 为 5。

### 当前收益与限制

审计模块现在可以把 timeout、格式失败、候选未形成、Agent 阶段错误、判题器差异和数学错误分开，后续可以按 ARM、题集、领域和语言做对照，并建立正确率、invalid 率、timeout recovery、wrong early-stop、P95 延迟和 token 成本的回归门。

它仍然不是因果诊断器：不能仅凭结果记录证明 endpoint 配置还是 Agent 架构造成 timeout；没有保存原始模型响应时，也不能事后判断截断文本中是否保留了可恢复候选；本地 native/contract 也不等同于官方 judger。

## 仓库卫生与发布边界

本归档只提交可读结论和源码/测试。逐次 `answers.jsonl`、`report.json`、manifest、预检和 raw dump 按仓库卫生规则保留在本地实验目录，不使用 `git add -f` 强行提交。需要复现时使用源码、配置、fixture、`run_id` 和本地证据目录。

当前状态为 `DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / NO_PROMOTION`。下一轮实验必须引用本归档的边界，并先通过 endpoint 健康门，再进行能力或策略 A/B。
