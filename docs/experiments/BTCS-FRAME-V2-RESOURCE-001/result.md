# BTCS-FRAME-V2-RESOURCE-001 resource result

状态：`VOID_RESOURCE_HEALTH / NO_CAPABILITY_CONCLUSION`

- workers=1，3 个请求均完成记录
- 成功：1/3
- timeout：2/3
- deadline：0
- orphan：0
- solver `max_tokens`：4096
- client retry：1
- 总耗时：381.661 秒

资源健康门要求 3/3 成功，因此本窗口作废。该结果只说明当前资源窗口不满足 v2
fidelity 前置条件，不说明 parser、共识逻辑或模型能力失败。

资源探针直接使用 `llm_client.py` 和独立 probe 脚本，不加载 BTCS runtime。manifest
中的其余 source SHA 记录运行时的 dirty 快照；后续离线 review 已修改这些文件，因此
本窗口不用于证明当前 staged BTCS runtime 已通过真实请求验证。

## 处置

不启动 fidelity、hard smoke、legacy84、core120、confirm30 或 official canary；不降低
token、不提高并发、不增加 retry，也不启动第三次同类资源复测。等待明确稳定资源窗口后，
如需继续必须依据新预注册重新审计。
