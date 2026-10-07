# Intern S2 原样代理接入（2026-10-07）

根目录 `user_agent.py`、`requirements.txt` 和 `implementations/` 来自本地
`intern-s-math-agent-main` 快照。所有 10 个源文件按字节复制，SHA-256 记录在
`source_sha256.json`；Git 属性禁用这些文件的行尾转换。没有源 Git 元数据，不能声明上游 commit。

## 模型配置

[官方在线模型文档](https://internlm.intern-ai.org.cn/docEn/docs/Models/) 明确列出：
397B 正式版的 API model ID 为 `intern-s2`，上下文 256K；
`intern-s2-preview-397b` 预览版将于 2026-10-31 下线。
[官方模型卡](https://huggingface.co/internlm/Intern-S2-397B/blob/main/README.md)
的 API 示例另写 `intern-s2-397b`，但同时要求以在线 API 文档为准。本接入固定使用
`intern-s2`；不使用浮动别名 `intern-latest`，也不将自托管权重名 `internlm/Intern-S2-397B`
当作托管 API ID。

目标仓库原有 `llm_client.py` 的默认模型和 `.env.example` 已是 `intern-s2`，无需修改。
HTTP endpoint 为 `https://chat.intern-ai.org.cn/api/v1/chat/completions`。
代理本身不指定模型，官方平台注入的 client 才决定平台实际模型；本地配置不能改变平台 client。
凭证通过 `INTERN_API_KEY` 提供，不能提交到 Git。

## 必要接入修改

- `llm_client.chat()` 接受源代理的请求级 `thinking_mode` 参数。显式 `reasoning_mode`
  优先，其次请求级 `thinking_mode`，最后客户端默认值；不修改客户端共享默认值。
- `main.py` 仅保留 `submission` profile，使用新代理默认配置；每题创建独立代理及客户端实例，
  默认并发为 3，避免复用代理中的可变预算与候选状态。
- `requirements.txt` 原样保留；本地 HTTP runner 另用 `requirements-local.txt` 安装 requests。
  历史实现、文档和测试保留，但不再代表当前入口。

## 验证与合入限制

新接入测试及既有客户端测试验证 mock HTTP 请求、模型字段、思考开关、异常兜底和 JSON 输出。
另验证源文件哈希、干净虚拟环境导入和客户端接口。不把 mock 检查视作真实模型能力或官方成绩。
旧入口 selector/CFR 专用测试针对历史实现，不能作为新入口的兼容证据。

源代理每次调用传入 `thinking_mode`，不兼容严格只接受
`chat(messages, temperature, max_tokens)` 的 client：会捕获 TypeError 并返回无法确定。
原样复制要求使本 PR 不修改代理。官方评测 client 是否支持该扩展必须另行确认；
这是源架构的已知兼容限制，用户已授权保持原样合入 main。尚未进行完整真实模型评测。

2026-10-07 验证记录：18 项接入/客户端测试通过；干净虚拟环境按原样
requirements.txt 安装 SymPy 1.13.3 / mpmath 1.3.0 后，导入与支持 thinking_mode 的
脚本客户端 solve 通过。一次独立真实 API 小请求使用 intern-s2 返回 HTTP 200、
response_model=Intern-S2、非空正文和 finish_reason=stop；这是端点/模型 ID
可用性冒烟，未运行完整代理真实模型评测，也不能证明严格三参数平台兼容。
