# MATH-HARNESS-112-DIAGNOSTIC-002

状态：用户授权；`diagnostic-only / NO_CAPABILITY_CONCLUSION`。

这是 `MATH-HARNESS-112-DIAGNOSTIC-001` 发现并修复通用标量等式候选边界后的独立校正窗。
它重新冻结配置和工件，不覆盖 `-001`，也不解除 `MATH-HARNESS-ENDPOINT-PREFLIGHT-001/002`
的 NO_GO。

## 校正内容

对标量题的无 marker 末行，例如 `2^7 = 128`，HostParser 现在取最后一个等号右侧的
结果作为候选；不改变 proof/derivation/explanation 路径，不引入题号或固定题面特判。
新增回归测试覆盖该通用行为。

## 冻结运行配置

- 数据集：`sample_data/public_regression_112.jsonl` 全部 112 题，固定文件顺序
- bank-off；标准答案只在宿主侧评分，不进入模型请求
- official-default thinking（`thinking_mode=None`）
- 3 workers；每题最多 5 次逻辑调用、16,384 请求 token、1200 秒；单次 HTTP timeout 600 秒
- 总窗口 hard stop 21,600 秒；client retry=1，不补发失败请求
- Harness token：A/B/Critic/Repair/Continuation = 4096/4096/2048/4096/2048

## 输出与边界

记录正确/错误/invalid/error、候选状态、调用/token、finish reason、耗时和 compact trace。
结果仍永久标记为 `diagnostic-only / NO_CAPABILITY_CONCLUSION`；不启动 HEALTH、A/B，不修改
`SUBMISSION_CONFIG`、FSDF 或远程发布面。
