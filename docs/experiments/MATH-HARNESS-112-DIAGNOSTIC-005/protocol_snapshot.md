# MATH-HARNESS-112-DIAGNOSTIC-005

状态：用户授权；`diagnostic-only / NO_CAPABILITY_CONCLUSION`。

这是 112 题诊断在完成 scalar RHS、成对/尾部数学定界符和孤立 `$` 规范化后的最终校正窗。
它不覆盖此前窗口，不解除端点预检 NO_GO，也不构成 Issue #17 能力晋升证据。

## 冻结修复

HostParser 对所有 scalar 候选入口统一执行受限的最终 RHS 提取，并清理成对或孤立的
`$`、`$$`、`\[...\]` 数学定界符；新增通用回归测试。该规则不引用题号、题面或答案。

## 运行配置

- 数据集：`sample_data/public_regression_112.jsonl` 全部 112 题，固定文件顺序
- bank-off；标准答案只在宿主侧评分，不进入模型请求
- official-default thinking（`thinking_mode=None`）
- 3 workers；每题最多 5 次逻辑调用、16,384 请求 token、1200 秒
- 单次 HTTP timeout 600 秒；client retry=1；总窗口 hard stop 21,600 秒
- Harness token：A/B/Critic/Repair/Continuation = 4096/4096/2048/4096/2048

## 输出与边界

记录正确/错误/invalid/error、候选状态、调用/token、finish reason、耗时和 compact trace。
结果永久标记为 `diagnostic-only / NO_CAPABILITY_CONCLUSION`；不启动 HEALTH、A/B，不修改
`SUBMISSION_CONFIG`、FSDF 或远程发布面。
