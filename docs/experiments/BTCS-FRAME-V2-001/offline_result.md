# BTCS Frame v2 offline result

状态：`STRUCTURAL_ONLY / PASS / RESOURCE_VOID / NO_CAPABILITY_CONCLUSION`

- 整理后的 BTCSv2 提交候选全量 unittest：502/502
- 此前混合工作树验收记录：507/507；该数字不作为本次提交范围的门结论
- GitCode/main 最小 backport（保留 `ff040df` 默认 GSA 配置）：442/442
- v2 replay：单行 `FINAL`、有限 Markdown wrapper、proof `BODY`、诊断计数、来源指标和
  数值 Arbiter evidence 约束均通过
- `py_compile`：通过
- JSON/trace 卫生：通过
- `git diff --check`：通过

当前离线协议验收通过；随后执行的 `BTCS-FRAME-V2-RESOURCE-001` 因 1/3 成功、2 timeout
作废。没有启动真实 fidelity、hard smoke、legacy84、core120、confirm30 或 official
canary，因此没有能力结论。

真实 fidelity 的固定样本数、packet 最小样本门和安全门见同目录
`preregistration.md`；不得通过累积样本直到通过来改变停止规则。
