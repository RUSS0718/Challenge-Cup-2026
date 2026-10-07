# Challenge Cup 2026 数学推理智能体

当前根目录入口为原样导入的 `intern-s-math-agent-main` 数学推理代理：
主路推理、受预算控制的续写、本地符号验证和候选选择。源文件字节与哈希保持一致。
本地 HTTP client 固定默认模型 `intern-s2`（Intern S2 397B 正式版）。

导入来源、模型官方文档、验证范围及严格三参数 client 兼容限制见
[接入说明](docs/releases/intern-s-math-agent-s2-20261007/README.md)。
**当前 main 使用此入口；未获得官方评测结果，严格三参数平台 client 尚不兼容。**

本地运行：安装 `requirements-local.txt`，配置 `INTERN_API_KEY` 和
`INTERN_MODEL=intern-s2`，执行：

```shell
python main.py --input_file sample_data/dev.jsonl --output_dir artifacts/intern-s2-local
```

`--profile` 仅接受 `submission`；默认并发为 3，每题使用独立代理和客户端状态。
平台提交只需安装原样的 `requirements.txt`，模型由平台注入 client 决定。

## 当前运行边界

正式入口 `ReasoningAgent(client=official_client)` 只导入 `implementations/` 的新架构。
没有旧 `SUBMISSION_MODE` / CFR / FSDF selector、答案库、RAG、Skills 或旧配置的自动回退。
本地 `main.py` 仅保留 `submission`，其中 `reasoning_agent.artifacts` 只负责保存文件，
已审核为标准库持久化工具，不参与生成、验证或答案选择。

历史实验和旧实现仍保留用于溯源；历史脚本可能依赖旧入口，不能用来运行或验证当前架构。
[旧 README 存档](docs/archive/pre-intern-import-readme-20261007.md) 和既有发布记录仅作历史资料。
审核范围及本地源仓库对照结果见
[隔离审核](docs/releases/intern-s-math-agent-s2-20261007/isolation-audit.md)。

当前接入回归检查（开发环境需安装 pytest；生产依赖清单保持原样）：

```shell
python -m pytest
```

默认 pytest 只收集当前入口、客户端、隔离检查和已审核持久化工具的测试；
旧架构专用测试保留但不默认收集，历史验证须显式指定文件。
