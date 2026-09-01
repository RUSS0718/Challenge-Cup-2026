# BTCS-FRAME-V2-RESOURCE-001 resource qualification

状态：`VOID_RESOURCE_HEALTH / NO_CAPABILITY_CONCLUSION`

实际结果见同目录 `run_manifest.json`、`health_probe_result.json`、`answers.jsonl`、
`progress.jsonl`、`report.json` 和 `result.md`。

## 目的与前置

本窗口只验证 `btcs_frame_v2` 在当前 endpoint/model 上的 4096-token 请求健康度；不验证
答案正确率，也不启动 fidelity 或 hard smoke。v2 离线 contract gate 必须先通过。

## 冻结参数

- run id：`BTCS-FRAME-V2-RESOURCE-001`
- method id：`btcs_frame_v2`
- branch：`codex/btcs-v1`
- HEAD：`2bca89a864098aa8253c7e793d73224b9d88d6ec`
- input：`sample_data/dev.jsonl`，exactly 3 requests
- workers：1，严格串行
- endpoint：`https://chat.intern-ai.org.cn/api/v1/chat/completions`
- model：`intern-s2-preview-397b`
- temperature：0.6
- solver `max_tokens`：4096
- client retry：1
- 底层 timeout：300 秒
- request deadline：360 秒

执行脚本：

```text
python scripts/btcs_frame_v2_resource_probe.py --input sample_data/dev.jsonl --timeout 300 --deadline 360
```

## 健康门

3/3 请求必须完成，且 `error=0`、`deadline_exceeded_count=0`、`orphan_completions=0`。
任一失败即 `VOID_RESOURCE_HEALTH`；不降低 token、不提高并发、不增加 retry，不复用
`BTCS-RESOURCE-002` 或旧 EPC/GSA 窗口。

通过后只解锁 `BTCS-FRAME-V2-FIDELITY-001`，不自动启动；所有结果保存为 compact
diagnostics，不保存题面、Prompt、模型正文或凭证。
