# BCOMP-001 有界完成基础设施与答案形成探针预注册草稿

状态：`DRAFT / DRY_RUN_ONLY / ZERO_MODEL_CALLS / NO_CAPABILITY_CONCLUSION`。

## 固定身份

- method：`bounded_completion_foundations_v1`
- run：`BCOMP-001-ZERO-MODEL-001`
- model：`official-client-deferred`
- endpoint：`official-endpoint-deferred`
- source：`sample_data/bcomp_dry_run_fixture.jsonl`，仅含 3 个无 gold 的合成 dry-run item
- seed：`20260912`
- parser：`host_parser_v1`
- scorer：`host_side_gold_v1`；gold 只允许在独立宿主评分侧出现
- route：`constraint_fit_direct_probe`
- bank：`off`
- retries：`0`

运行脚本会把 source、代码和协议 SHA-256 写入 manifest；缺少任一 hash 或边界字段时，
配置校验拒绝启动。当前具体 hash 以脚本生成的 `run_manifest.json` 为准，不手工复制。

## 固定资源与顺序

| 项 | 值 |
| --- | --- |
| 每臂请求 token | `8192` |
| 每题最大逻辑调用 | `1` |
| 每题请求 token 上限 | `16384` |
| 每题窗口 | `1200 s` |
| 调用等待上限 | `900 s` |
| 收尾余量 | `30 s` |
| 窗口上限 | `21600 s` |
| 并发 | `3 workers` |
| arm | `formation`，固定 ordinary free-format scope |
| 顺序 | `fixed`；未来多臂窗口必须另立 balanced 计划 |

## 停止与 VOID 门

- `void_on_incomplete_records=true`：计划项未逐项落盘时作废。
- `void_on_unstable_endpoint=true`：模型错误率超过 `0.10` 或出现预注册的资源不稳定时作废。
- `first_three_formed_zero=true`：真实形成率窗前三个已请求 item 均无 complete candidate 时停止；
  本 dry-run 不触发该门，因为没有请求模型。
- 未请求项计为 `skipped`，不计为模型答错；timeout 进入形成率分母，并保留 timeout-censored latency。

## 解锁条件

本文件只能作为后续新窗口的候选协议。真实端点 probe、形成率门、策略 A/B、能力晋升、
`SUBMISSION_CONFIG` 修改、提交和发布均不由本预注册自动解锁；真实运行前必须以新 run ID
重新确认数据、数值门、资源健康和 disposition。
