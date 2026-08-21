# 输出协议 A/B 实验

当前默认路径保持 `F+4096`。实验开关全部默认关闭，不能把实验结果自动写回默认配置。

## 版本

| 版本 | Prompt | 严格 salvage | 无答案时重试 |
|---|---|---|---|
| `baseline86` | `86b66d2` 风格单行答案 | 否 | 4096 |
| `A` | 数值题答案前置 | 否 | 4096 |
| `B` | 基线 Prompt | 是 | 4096 |
| `A+B` | 答案前置 + salvage | 是 | 4096 |
| `A+B+6144` | 答案前置 + salvage | 是 | 6144 |

所有版本最多两次模型调用；重试只在首轮没有可解析答案时发生。报告只保存计数、finish reason、token/延迟统计和安全诊断原因，不保存模型原文。

## 运行

需要明确允许向配置的外部模型 API 发送冻结集题目后执行：

```powershell
D:\Anaconda\envs\CA-py310\python.exe scripts\evaluate_protocol_ab.py `
  --rounds 2 --workers 3 --timeout-seconds 60 --retry-count 1 `
  --output-file docs/protocol_ab_2026-08-20.json
```

中断后报告文件保留已经完成的版本，可从已有文件分析，但不应把缺失轮次当作通过。

## 晋升检查

```powershell
D:\Anaconda\envs\CA-py310\python.exe scripts\evaluate_protocol_ab_gate.py `
  docs/protocol_ab_2026-08-20.json
```

候选必须在三个数据集、两轮中同时满足：准确率不低于同轮 `baseline86`、Invalid 和 Incorrect 均不增加、主调用截断率不增加、`final_response` 非空率 100%、平均调用不超过 1.5、最大调用不超过 2。未通过时保持当前默认路径，不提交 canary。


