# MATH-HARNESS-112-DIAGNOSTIC-003

状态：用户授权；`diagnostic-only / NO_CAPABILITY_CONCLUSION`。

这是 112 题诊断在发现第二个通用数学包装边界（RHS 后残留 `$$`/`\]`）并修复后的独立
校正窗。它不覆盖 `MATH-HARNESS-112-DIAGNOSTIC-001/002`，也不解除端点预检 NO_GO。

## 校正内容

HostParser 现在支持成对 `$$...$$`、`\[...\]` 数学定界符，并清理从等式 RHS 提取后残留的
尾部定界符；既有等式 RHS 规则和回归测试保持。该行为只针对通用数学表示，不引用题号或
固定答案。

## 冻结配置

- 数据集：`sample_data/public_regression_112.jsonl` 全部 112 题，固定文件顺序
- bank-off；标准答案只在宿主侧评分，不进入模型请求
- official-default thinking（`thinking_mode=None`）
- 3 workers；每题最多 5 次逻辑调用、16,384 请求 token、1200 秒；单次 HTTP timeout 600 秒
- 总窗口 hard stop 21,600 秒；client retry=1，不补发失败请求
- Harness token：A/B/Critic/Repair/Continuation = 4096/4096/2048/4096/2048

## 输出与边界

记录正确/错误/invalid/error、候选状态、调用/token、finish reason、耗时和 compact trace。
结果永久标记为 `diagnostic-only / NO_CAPABILITY_CONCLUSION`；不启动 HEALTH、A/B，不修改
`SUBMISSION_CONFIG`、FSDF 或远程发布面。
