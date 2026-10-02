# Repository hygiene for experiment artifacts

本项目把“如何得到结果”和“某一次运行得到的结果”分开管理。

## Versioning boundary

进入 Git 的内容：

- 正式源码、测试代码和测试 fixture；
- 可复用的实验定义、配置和预注册协议；
- 有代表性的 baseline，以及压缩后的实验结论和决策记录。

默认留在本地的内容：

- 每次运行生成的 `answers.json`、`answers.jsonl`、`report.json`、
  `run_manifest.json`、`metrics.json`、`network_preflight.json`、日志和临时调试文件；
- 完整模型响应、逐题诊断和其他只对一次运行有意义的 raw dump。

运行产物统一放在：

```text
artifacts/
└── 20260928-135512-arm-adaptive/
    ├── run_manifest.json
    ├── answers.jsonl
    ├── metrics.json
    └── report.json
```

`artifacts/`、`runs/`、`outputs/`、`logs/` 和 `tmp/` 已由 `.gitignore` 忽略。
不要为了让运行结果出现在 Git 状态中而使用 `git add -f`。

## Run identity and manifest

每次运行使用一个唯一 `run_id`，推荐格式为
`YYYYMMDD-HHMMSSffffff-<config>`（也可在人工运行时使用秒级时间戳加其他唯一后缀）。
manifest 至少记录：

```json
{
  "run_id": "20260928-135512-arm-adaptive",
  "git_commit": "abc123",
  "config": "arm-adaptive",
  "dataset": "eval-112",
  "model": "...",
  "started_at": "...",
  "status": "completed"
}
```

`reasoning_agent.artifacts.RunContext` 和 `ArtifactManager` 是运行代码的统一
写入边界。新 harness、评测 runner 或测试辅助脚本应通过它们保存 manifest、
answers、metrics、report 和文本摘要，不再在各自目录中复制一套原子写入逻辑。

## Durable summaries

实验结论进入 `docs/experiments/<experiment-id>/result.md` 或更高层的实验摘要，
内容聚焦配置、数据集、关键指标、门禁结果和结论。不要把几十个 raw JSON 直接
当作实验历史；需要复现时，依靠源码、配置、fixture、`run_id` 和 manifest 的
来源信息重跑。

现有 `docs/experiments/` 中已被 Git 跟踪的 raw 文件是历史证据，本规则不要求在
一次清理中批量删除或改写它们。后续新运行不得继续向该目录写 raw 产物；迁移旧
实验时，保留可读的 summary，另行处理历史文件的索引和归档。

## Review checklist

提交实验相关改动前确认：

1. 源码、测试、fixture、配置和 summary 与 raw 运行文件分开；
2. 新 runner 的默认输出路径在 `artifacts/<run_id>/`，并且不会覆盖另一 run；
3. manifest 能把配置、数据集、模型、时间和代码版本关联起来；
4. summary 没有把单次本地结果夸大为官方能力结论；
5. Git diff 中没有 API key、完整模型响应或无意义的逐题运行副产物。
