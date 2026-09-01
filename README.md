# Challenge Cup 2026 数学推理智能体

本仓库是挑战杯 2026 人工智能赛道初赛的参赛实现:一个受调用预算约束的数学
推理智能体。当前默认流水线为题型识别 → BTCS Frame v2 求解 → 本地答案共识 →
受限 Arbiter → 规范化输出，同时保持赛事规定的单文件入口与公开
client 契约。

> 当前状态（2026-09-02）：经用户明确授权，默认提交路径已切换为
> `btcs_frame_v2` official trial；回滚锚为 `e9df37e` 的严格 GSA 3+1。
> v2 资源资格窗 1/3 成功并作废，尚无 fidelity 或能力结论。

## 当前 Agent 架构

系统是"确定性 Python Harness + 受调用预算约束的模型推理":每题 `solve()`
内独立维护候选、预算与 trace,无跨题状态,不读取 `metadata` 中的答案信息。

```mermaid
flowchart TD
    entry["ReasoningAgent.solve(problem, metadata)"] --> classify["P0 题型识别(纯文本,六类)"]
    classify --> solvers["BTCS solver A/B，必要时 C"]
    solvers --> consensus{"本地等价共识"}
    consensus -->|"一致"| finalize["final_response 组装"]
    consensus -->|"分歧"| arbiter["Bounded Arbiter<br/>仅 SELECT A/B/C/UNKNOWN"]
    arbiter --> finalize
    finalize --> out["final_response + extracted_answer + trace"]
```

| 层 | 在役实现 | 备注 |
| --- | --- | --- |
| 题型识别 | 纯文本规则六分类,不读 metadata | 常开 |
| 生成 | 数值题单行 `FINAL`；证明题 `FINAL/EVIDENCE/BODY` | 最多3个 solver candidates |
| 选择 | 本地等价共识；分歧时受限 Arbiter | 不允许创造新答案 |
| 预算 | logical≤4、HTTP≤5、retry≤1 | solver 4096 tokens |
| 表示 | numeric 规范化；非数值正文重建 | `UNKNOWN` fail-closed |
| 输出 | `final_response` 非空保证;失败路径返回兜底句 | trace 仅记决策摘要 |

### BTCS Frame v2 默认路径

官方无参构造现在直接使用有限 `FINAL`
答案帧、本地等价共识和只能选择 A/B/C 的受限 Arbiter。每题 logical calls≤4、
HTTP attempts≤5、retry≤1；`UNKNOWN` fail-closed。

## 项目架构与发布流

```mermaid
flowchart LR
    subgraph official["官方平台(每夜 24:00 槽)"]
        judge["clone main → 无参构造<br/>112 隐藏题 → eval_log 五数"]
    end
    subgraph deploy["发布面"]
        gitcode["gitcode/main<br/>(行为 = 在役 canary)"]
        release["发布线克隆<br/>canary/revert 操作面"]
    end
    subgraph loop["实验闭环(每窗一变量)"]
        branch["工作分支 codex/b1-4k-canary<br/>23 变体 + 380 测试"]
        runner["evaluate_protocol_ab.py<br/>240s / workers=3 / 交错配对"]
        sets["冻结集 complex48 / medium60<br/>public112 / dev(探针)"]
        judge2["判定:void 门(错误率>10%整窗作废)<br/>→ 正确率/成本/卫生门 → 逐题配对"]
    end
    branch --> runner --> sets --> judge2
    judge2 -->|"过门 = 官方候选"| release
    release -->|"push(用户签发)"| gitcode --> judge
    judge -->|"Run 日志五数判读"| decision{"keep / rollback"}
    decision -->|"rollback"| anchor["回滚锚(revert 提交)"] --> gitcode
```

## 项目目录结构

```text
├── user_agent.py                        # Agent 核心:ReasoningAgent + 全部实验开关
├── reasoning_agent/btcs.py              # 默认 BTCS Frame v2 协议
├── llm_client.py                        # 书生 API client(本地评测用)
├── main.py                              # 本地逐题 runner
├── scripts/
│   ├── evaluate_protocol_ab.py          # 实验主力 runner:23 变体/交错配对/void 熔断
│   ├── btcs_fidelity_probe.py           # 固定 10 题 fidelity 门
│   ├── btcs_frame_v2_resource_probe.py  # workers=1 资源资格窗
│   ├── replay_btcs.py                   # 离线 transcript replay
│   └── evaluate_dev.py                  # 单配置 evaluator 与消融 CLI
├── sample_data/
│   ├── dev.jsonl                        # 3 题冒烟集
│   ├── public_regression_112.jsonl      # 112 题短题知识覆盖集(回归保护)
│   ├── medium_capability_freeze_60.jsonl
│   └── complex_capability_freeze_48.jsonl
├── tests/                               # 442 项单测(默认路径 + BTCSv2 backport)
├── docs/
│   ├── excluded_approaches.md           # 淘汰方案单一事实源(七条死线)
│   ├── research/                        # 候选依据:能力/评测方法研究 + 采纳报告
│   ├── experiments/                     # 本地与官方评测报告与工件(78+)
│   ├── adr/                             # 关键决策记录
│   ├── agents/                          # 工作流约定
│   └── branches_map.md                  # 分支与发布面地图
├── method_cards.jsonl 等                 # 已归档实验的离线资产(对应开关默认关)
└── tmp/                                 # 未归档原始工件(untracked)
```

## 提交配置与实验开关板

官方 runner 以 `ReasoningAgent(client=official_client)` 无参构造，解析到
`SUBMISSION_CONFIG`：BTCS Frame v2，logical calls≤4、HTTP attempts≤5、
retry≤1、4096 token/solver；不与 GSA、adaptive voting、refine、salvage、RAG
或 SymPy 叠加。

| 开关 | 在役 | 说明 |
| --- | --- | --- |
| `protocol_mode="btcs_frame_v2"` | ✅ | 当前 official trial |
| `enable_adaptive_voting`(k5/threshold3) | ⬜ | GSA 默认路径关闭 |
| `enable_heterogeneous_reasoners` | ⬜ | GSA 显式安排三候选顺序 |
| `enable_step_verification` / `enable_step_revision` | ⬜ | refine 已撤下 |
| `enable_answer_dual_form`(ARH) | ⬜ | 默认关闭 |
| `enable_gsa_aggregation`(GSA) | ⬜ | 回滚锚 `e9df37e` |
| `enable_numeric_chain_of_draft`(CoD) | ⬜ | ARCHIVED |
| `enable_re2_reread`(Re2) | ⬜ | ARCHIVED(官方回滚) |
| `enable_failure_salvage`(P1) | ⬜ | ARCHIVED |
| `enable_verification_gated_retry`(B1) | ⬜ | 被投票路径替代 |
| `enable_method_rag` | ⬜ | 永久排除(双轮双负) |

## 赛事接口

仓库根目录的 `user_agent.py` 导出:

```python
from user_agent import ReasoningAgent

agent = ReasoningAgent(client=official_client)
result = agent.solve(problem, metadata)
```

返回值是可 JSON 序列化的字典,并始终包含非空字符串 `final_response`。
智能体只依赖公开模型调用契约 `client.chat(messages, temperature, max_tokens)`;
不访问 client 私有字段,不读取样例 `answer`,不依赖本地绝对路径,trace 不保存
完整 Prompt、冗长模型原文或敏感信息。

## 快速开始

建议使用 Python 3.10+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

本地调用需要配置书生 API:

```powershell
$env:INTERN_API_KEY = "your-api-key"
# 可选:$env:INTERN_MODEL = "intern-s2-preview-397b"
```

运行 3 道快速冒烟题:

```powershell
python main.py --input_file sample_data/dev.jsonl --output_dir sample_outputs
```

## 本地评测与实验纪律

- **主力 runner**:`scripts/evaluate_protocol_ab.py`(多臂交错配对、240s 超时、
  连续失败熔断、逐题诊断)。筛选窗一律**预注册**:门槛与 void 门
  (任一臂错误率 >10% 整窗作废)在运行前冻结。
- 判定顺序:void 门 → 正确率门 → 成本门 → 卫生门 → 逐题配对差分。
- 本地 AnswerJudge 为保守三态(精确一致/结构化有理数一致/UNKNOWN),不等同
  官方 judger;报告口径含平均/P95 调用、completion tokens、墙钟、invalid 与
  正确数并列。

## 测试与提交前检查

```powershell
python -m unittest discover -s tests -q
python -m py_compile user_agent.py llm_client.py sympy_adapter.py main.py scripts/evaluate_dev.py
```

当前 GitCode/main backport 验收基线 **442/442**。提交前还应确认:`user_agent.py` 可正常
import;`ReasoningAgent(client=official_client)` 可初始化;client 失败时仍返回
可序列化非空 `final_response`;仓库无 API key、个人路径与样例答案特判;实际
提交配置与 A/B 报告中的配置一致。

## 当前路线

- **在役**：BTCS Frame v2 official trial；尚无 fidelity 或能力结论。
- **回滚锚**：`e9df37e` 严格 GSA 3+1。
- **下一步**：读取同一隐藏集 official log 后按 correct/error/耗时门裁决 keep/rollback。
- **已淘汰**(详见 `docs/excluded_approaches.md`):method_rag、Re2、CoD、
  P1 salvage、G 门控、TIR/回代验证、32k 天花板。
- **暂不引入**:LLM-as-judge 本地判分、PRM 组件、LangGraph/AgentScope、
  联网工具与任意代码执行。

详细证据与决策记录见:`docs/experiments/`(六轮官方与全部本地报告)、
[docs/excluded_approaches.md](docs/excluded_approaches.md)、
[docs/adr/](docs/adr/)、[docs/branches_map.md](docs/branches_map.md)。

## 官方提交

赛事特有规则以[飞书赛事文档](https://aicarrier.feishu.cn/wiki/L90FwD9gJiqdg0k33RCcHTdcnrb)
为准。评测拉取作品关联仓库的最新 `main` 分支(每日固定窗口,实测均在凌晨
队列后执行)。

1. 将可复现版本推送到队伍 AtomGit 组织仓库的 `main` 分支(走发布线克隆)。
2. 在作品页面保持关联与提交状态。
3. 每轮结果按五数判读并记入 `docs/experiments/官方评测记录.md`,回滚条件
   在发布记录中预写。

提交、推送和作品页面操作都应单独确认。本地数据集结果只用于研发,不代表
正式成绩。
