# Challenge Cup 2026 数学推理智能体

本仓库是挑战杯 2026 人工智能赛道初赛的参赛实现:一个受调用预算约束的数学
推理智能体。流水线为题型识别 → 答案先行生成 → 异构自适应投票 → 确定性选择 →
验证/修正/复验链 → 规范化输出,同时保持赛事规定的根入口与公开
client 契约。

> 当前状态(2026-08-30 晚):官方 Run #7 判定 **hetero+refine+ARH 整栈 =
> OFFICIAL_NEGATIVE_STACK / ROLLBACK_TRIGGERED**(9/92/11、1 error、7h14m 超时,
> gitcode main 仍停在 `46c08dd`,**指针回滚待用户执行**)。运营基线恢复目标 =
> **hetero_k5 @ 25f99b5**(官方 Run #5 = 12/112,唯一健康锚;profile 见
> docs/experiments/operational_baseline_hetero_k5_25f99b5.json)。refine 全量
> 形态暂停;ARH 保留为零调用后置候选。本地评测协议已按 Pre-P0 校准
> (AA-004 六门全过,噪声带与门见 docs/experiments/PRE0-SUMMARY-2026-08-30.md)。

## 当前 Agent 架构

系统是"确定性 Python Harness + 受调用预算约束的模型推理":每题 `solve()`
内独立维护候选、预算与 trace,无跨题状态,不读取 `metadata` 中的答案信息。

```mermaid
flowchart TD
    entry["ReasoningAgent.solve(problem, metadata)"] --> classify["P0 题型识别(纯文本,六类)"]
    classify --> route{"预算路由"}
    route -->|"L0 简算"| l0["Direct × 1(4096 tokens)"]
    route -->|"默认"| main1["主调用 × 1<br/>answer-first:numeric 族第一行 = 最终答案"]
    l0 --> finalize
    main1 --> vote["adaptive k5 自适应投票(hetero 在役)<br/>最多 5 个独立候选;首次补采样 = AlternativeReasoner<br/>(反证/构造/边界/数值验证),其余 Direct<br/>保守等价分组,3 票共识早退"]
    vote --> select["确定性候选选择<br/>(共识组大小优先)"]
    select --> refine{"P3 refine 链(整栈负结果,随回滚撤下)<br/>verify → revise → 复验"}
    refine -->|"复验明确发现错误"| rollback["回滚原解"]
    refine -->|"通过"| finalize["final_response 组装<br/>numeric:规范化最简形<br/>非数值:正文重建"]
    rollback --> finalize
    finalize --> out["final_response + extracted_answer + trace"]
    vote -. "发5 GSA 备选<br/>3 采样 + 1 生成式聚合(4 调用)" .-> gsa["gsa_4call"]
    finalize --> arh["ARH(随回滚撤下;保留为零调用后置候选)<br/>答案句 + boxed 双形态"]
```

| 层 | 在役实现 | 备注 |
| --- | --- | --- |
| 题型识别 | 纯文本规则六分类,不读 metadata | 常开 |
| 生成 | answer-first:numeric 族第一行即最终答案 | 截断免疫(88% 截断率下答案仍可判) |
| 采样/聚合 | adaptive k5:≤5 候选,3 票共识早退;首次补采样为异构策略 | hetero 在役(官方 Run #5 = 12/112) |
| 修正 | P3 verify→revise→复验；明确复验错误回滚 | 当前提交行为；未决复验语义见总spec |
| 表示 | numeric:答案句+boxed规范形;非数值:正文重建 | ARH 随 Run #7 整栈撤下;invalid 11 为历史最低但未转化为 correct |
| 输出 | `final_response` 非空保证;失败路径返回兜底句 | trace 仅记决策摘要 |

## 项目架构与发布流

```mermaid
flowchart LR
    subgraph official["官方平台(每夜 24:00 槽)"]
        judge["clone main → 无参构造<br/>112 隐藏题 → eval_log 五数"]
    end
    subgraph deploy["发布面"]
        gitcode["gitcode/main<br/>(46c08dd canary;OFFICIAL_NEGATIVE_STACK,回滚待执行)"]
        release["发布线克隆<br/>canary/revert 操作面"]
    end
    subgraph loop["实验闭环(每窗一变量)"]
        branch["本地集成分支<br/>36 变体 + 442 测试"]
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
├── user_agent.py                        # 官方兼容入口与重导出 facade
├── reasoning_agent/
│   ├── policy.py                        # 题型、Prompt、AgentConfig、提交 profile
│   ├── answers.py                       # 抽取、规范化、等价与确定性检查
│   ├── runtime.py                       # ReasoningAgent 求解编排
│   └── tools/                           # 默认关闭的受控数学工具实现
├── llm_client.py                        # 书生 API client(本地评测用)
├── main.py                              # 本地逐题 runner
├── scripts/
│   ├── evaluate_protocol_ab.py          # 实验主力 runner:交错配对/void 熔断
│   └── evaluate_dev.py                  # 单配置 evaluator 与消融 CLI
├── sample_data/
│   ├── dev.jsonl                        # 3 题冒烟集
│   ├── public_regression_112.jsonl      # 112 题短题知识覆盖集(回归保护)
│   ├── medium_capability_freeze_60.jsonl
│   └── complex_capability_freeze_48.jsonl
├── tests/                               # 442+ 单测(行为/单变量/档位断言)
├── docs/
│   ├── excluded_approaches.md           # 淘汰方案单一事实源(七条死线)
│   ├── research/                        # 候选依据:能力/评测方法研究 + 采纳报告
│   ├── experiments/                     # 本地与官方评测报告与工件(78+)
│   ├── adr/                             # 关键决策记录
│   ├── agents/                          # 工作流约定
│   └── branches_map.md                  # 分支与发布面地图
├── experiments/legacy/                  # 已归档、默认关闭的实验实现与资产
└── tmp/                                 # 未归档原始工件(untracked)
```

## 提交配置与实验开关板

官方 runner 以 `ReasoningAgent(client=official_client)` 无参构造,解析到
`SUBMISSION_CONFIG`(runtime `9311d8c`):answer-first 主调用 + **hetero adaptive k5**
(首次补采样为异构策略)+ **P3 refine 链** + **ARH 双形态**,effective 调用上限
8(5+3),4096 token/调用。

| 开关 | 在役 | 说明 |
| --- | --- | --- |
| `enable_adaptive_voting`(k5/threshold3) | ✅ | 共识投票 |
| `enable_heterogeneous_reasoners` | ✅ | 投票内 1 路 Alternative |
| `enable_step_verification` / `enable_step_revision` | ✅ | refine 链 |
| `enable_answer_dual_form`(ARH) | ✅ | 答案句 + boxed 双形态 |
| `enable_gsa_aggregation`(GSA) | ⬜ | 探索性正信号，须按总spec重证 |
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

当前本地集成验收基线 **442/442**。提交前还应确认:`user_agent.py` 可正常
import;`ReasoningAgent(client=official_client)` 可初始化;client 失败时仍返回
可序列化非空 `final_response`;仓库无 API key、个人路径与样例答案特判;实际
提交配置与 A/B 报告中的配置一致。

## 当前路线

- **在役**:hetero+refine+ARH canary(runtime `9311d8c`),回滚锚 `95d5700`；
  官方日志待回收。
- **下一步**:先执行
  `docs/experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md` 的 Pre-P0，
  再决定 GSA 或后续方法窗。
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
3. 每轮结果按五数判读并记入 `docs/experiments/authority/官方评测记录.md`,回滚条件
   在发布记录中预写。

提交、推送和作品页面操作都应单独确认。本地数据集结果只用于研发,不代表
正式成绩。
