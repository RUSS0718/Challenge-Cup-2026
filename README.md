# Challenge Cup 2026 数学推理智能体

当前发布状态以 [`docs/current_release.json`](docs/current_release.json) 为准。开始评测或
切换分支前，先运行 `python scripts/show_repo_state.py --write --check`；默认输出简短摘要和最近
工件路径，它会核对当前 selector、GitCode main、工作树和发布 runtime hash。需要完整机器快照时
加 `--json`。实验结果的范围和可否重跑，查询
[`docs/experiment_registry.json`](docs/experiment_registry.json)，完整历史处置仍以
[`docs/excluded_approaches.md`](docs/excluded_approaches.md) 为准。

本仓库是挑战杯 2026 人工智能赛道初赛的参赛实现:一个受调用预算约束的数学
推理智能体。当前提交 profile 的默认流水线为题型/答案形态分类 →
Constraint-Fit Harness（Direct/Deep/FSDF fallback）→ 规范化输出，同时保持赛事
规定的单文件入口与公开 client 契约。

> 当前状态（2026-10-04）：正式无参提交 selector 为 ARM v2.1.4 CFR。CFR 是一套新的
> Challenger → Targeted Repair → Fresh Review 方案，默认关闭 hybrid router、答案库、RAG
> 和 Skill；它已完成代码/接口门，并有 2026-10-04 官方 100 题报告 `21/6/73`。该报告不与
> 历史 112 题表格直接比较，也不触发 selector 晋升。GRH v1.1 / 119 正确版本
> 仅作为回滚锚和历史对照保留，invalid rescue 第三轮的方案、结果和回退理由见
> [`docs/archive/invalid_rescue_round3_2026-10-04.md`](docs/archive/invalid_rescue_round3_2026-10-04.md)，
> CFR 发布协议见 [`docs/releases/arm-v2.1.4-cfr-20261004/`](docs/releases/arm-v2.1.4-cfr-20261004/)。

## 当前 Agent 架构

系统是"确定性 Python Harness + 受调用预算约束的模型推理":每题 `solve()`
内独立维护候选、预算与 trace,无跨题状态,不读取 `metadata` 中的答案信息。

```mermaid
flowchart TD
    entry["ReasoningAgent.solve(problem, metadata)"] --> classify["题型/答案形态分类<br/>风险与置信度"]
    classify --> harness["Constraint-Fit Harness"]
    harness --> direct["Direct"]
    harness --> deep["Deep typed lane"]
    harness --> fsdf["FSDF legacy fallback"]
    direct --> finalize["保守选择 / UNKNOWN"]
    deep --> finalize
    fsdf --> finalize
    finalize --> out["final_response + extracted_answer + trace"]
```

| 层 | 在役实现 | 备注 |
| --- | --- | --- |
| 题型/学科分类 | 纯文本规则六类答案形态 + 18 学科词汇路由 | 常开；不读 metadata |
| 生成/路由 | Direct A/B、Deep primary/review、FSDF A/B/C/D/E | 由 HostRouter 按合同分流 |
| 选择 | Evidence Ledger + HostParser/TypedParser | 非法、冲突或不可验证时 `UNKNOWN` |
| 预算 | CFR 每题最多 4 次模型调用 | adaptive/deep 总预算各 16,384 tokens；FSDF 仅作显式历史对照 |
| 表示 | 结构化候选、typed parse、handoff | `UNKNOWN` fail-closed |
| 输出 | `final_response` 非空保证;失败路径返回兜底句 | trace 仅记决策摘要 |

### ARM v2.1.4 CFR（提交 profile 开启）

新方案位于 `reasoning_agent/arm_harness_v214.py`，通过 `ReasoningAgent.solve()` 接入；
Primary 先形成候选，Challenger 以结构化异议检查具体位置和证据，只有可修复异议才进入
一次 Targeted Repair，Fresh Review 必须精确匹配异议并返回 `PASS` 才能替换 incumbent。
任何门失败都保留安全候选或返回 `UNKNOWN`。统一 client dispatch 兼容官方三参数契约，
不会要求评测平台支持本地扩展参数。

当前状态为 `DEPLOYED_EVALUATED_NO_PROMOTION`：已验证 selector、预算、严格三参数 client、
metadata/gold 隔离和 trace 卫生；100 题官方报告已归档，但没有与历史 112 题表格同范围的
可比结果，不能从本地 smoke 或 119 回滚锚推导能力提升。完整发布协议和离线 verifier 见
`docs/releases/arm-v2.1.4-cfr-20261004/`。

### ARM v2.1.7 structured confirmation（实验 profile，默认关闭）

该候选只允许 Challenger 确认已有 incumbent 值，不允许生成替代答案或放宽 evaluator。新鲜
25 题的 10 轮配对结果为候选/基线均 `24/0/1`，候选触发确认 `17/25`，平均调用和截断率
相同；因此保持默认关闭。预注册和逐题证据见
`docs/experiments/ARM-V2.1.7-STRUCTURED-CONFIRMATION-20261005/`。

### Contextual Answer Reconstruction 历史实验路径

该路径保持 default-off，仅作为历史实验实现保留；当前官方无参构造使用
`SUBMISSION_MODE=arm-v2.1.4-cfr`，FSDF 和 GRH v1.1 / 119 仅作为显式历史对照。

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
        branch["实验/整理分支<br/>scoped commit + 冻结集"]
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
├── user_agent.py                        # Agent 兼容 facade: ReasoningAgent + 配置
├── reasoning_agent/answer_parsing.py      # 纯答案抽取、规范化与确定性检查
├── reasoning_agent/harness_contracts.py   # Harness 合同、候选与 typed parser
├── reasoning_agent/math_harness.py       # MATH-HARNESS-V1 编排、预算与路由
├── reasoning_agent/profiles.py            # 本地 submission、agent-default、ARM 实验 profile
├── llm_client.py                        # 书生 API client(本地评测用)
├── main.py                              # 本地逐题 runner
├── scripts/
│   ├── evaluate_protocol_ab.py          # 实验主力 runner:23 变体/交错配对/void 熔断
│   └── evaluate_dev.py                  # 单配置 evaluator 与消融 CLI
├── sample_data/
│   ├── dev.jsonl                        # 3 题冒烟集
│   ├── medium_capability_freeze_60.jsonl
│   └── complex_capability_freeze_48.jsonl
├── reasoning_agent/error_notebook/eval_112.json # 本地 112 题测试集
├── tests/                               # 本地回归测试(当前全量 1049 项,4 项跳过)
├── docs/
│   ├── excluded_approaches.md           # 淘汰方案单一事实源
│   ├── ARCHIVE_INDEX.md                 # 当前/历史文档分类索引
│   ├── archive/                         # 已移出根目录的旧总结与草稿
│   ├── research/                        # 候选依据:能力/评测方法研究 + 采纳报告
│   ├── experiments/                     # 可读实验总结与历史证据
│   ├── adr/                             # 关键决策记录
│   ├── agents/                          # 工作流与仓库卫生约定
│   ├── architecture_evolution.md        # 版本/架构演进总表
│   └── branches_map.md                  # 分支与发布面地图
└── artifacts/<run_id>/                 # 被忽略的本地运行产物
```

## 提交配置与实验开关板

官方 runner 以 `ReasoningAgent(client=official_client)` 无参构造，解析到当前分支的
`SUBMISSION_CONFIG`：先做题型/学科分类，随后由 Constraint-Fit Router 分流，
direct 进入 Direct Harness，deep/structured/低置信题进入 FSDF legacy fallback。
当前正式 selector 为 `arm-v2.1.4-cfr`；GRH v1.1 / 119 只作为 `43a02da` 回滚锚。CFR 的
官方 100 题报告已归档，但不能从不同题数的历史表格、本地 smoke 或配置切换推导新的能力
或成绩结论。

| 开关 | 在役 | 说明 |
| --- | --- | --- |
| `enable_fork_select_deepen_finish` | ✅ | Constraint-Fit 的 FSDF legacy fallback |
| `enable_temporary_answer_bank` | ⬜ | 默认路径已移除；底层旧 gateway 仅保留显式测试兼容 |
| `enable_contextual_answer_reconstruction` | ⬜ | 历史实验路径 |
| `enable_adaptive_voting`(k5/threshold3) | ✅ | FSDF v1 候选一致性投票 |
| `enable_heterogeneous_reasoners` | ✅ | 新路径候选生成 |
| `enable_step_verification` / `enable_step_revision` | ⬜ | refine 已撤下 |
| `enable_answer_dual_form`(ARH) | ⬜ | 默认关闭 |
| `enable_gsa_aggregation`(GSA) | ⬜ | 回滚锚 `e9df37e` |
| `enable_numeric_chain_of_draft`(CoD) | ⬜ | ARCHIVED |
| `enable_re2_reread`(Re2) | ⬜ | ARCHIVED(官方回滚) |
| `enable_failure_salvage`(P1) | ⬜ | ARCHIVED |
| `enable_verification_gated_retry`(B1) | ⬜ | 被投票路径替代 |

### Official-equivalent submission modes

The formal submission has one selector; the booleans below are only derived
implementation details:

```python
from user_agent import ReasoningAgent, build_submission_config

SUBMISSION_MODE = "arm-v2.1.4-cfr"
SUBMISSION_CONFIG = build_submission_config(SUBMISSION_MODE)
agent = ReasoningAgent(client=official_client)  # config=None -> SUBMISSION_MODE
```

Allowed values include `fsdf`, the v2.1.2/v2.1.3 ARM modes, and the explicit
v2.1.4 modes `arm-v2.1.4-off`, `arm-v2.1.4-adaptive`, and
`arm-v2.1.4-cfr`. The current authorized selector is `arm-v2.1.4-cfr`;
the promotion runner's A arm remains a fixed FSDF baseline and is independent
of the formal selector.

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
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

在 `.env` 中填写 `INTERN_API_KEY`；本地评测模型固定为
`INTERN_MODEL=intern-s2`。`llm_client.py` 会自动加载仓库根目录的
`.env`，其中的值优先于同名 Windows 环境变量。`.env` 已被 Git 忽略，不要提交密钥。
`INTERN_API_BASE` 默认使用官方兼容端点；超时、重试和 thinking 模式按各实验协议设置，
不要为了方便写成会改变冻结实验的全局覆盖值。

运行 3 道快速冒烟题:

```powershell
python main.py --input_file sample_data/dev.jsonl --output_dir artifacts/20260928-135512-dev-smoke
```

运行产物应使用唯一的 `artifacts/<run_id>/` 目录，例如
`artifacts/20260928-135512-dev-smoke/`；不要把逐题 JSON、manifest 或 report
写入源码目录或 `docs/experiments/`。完整约定见
[`docs/agents/repository-hygiene.md`](docs/agents/repository-hygiene.md)。

本地 runner 可用 profile 开关整组切换功能；默认仍是官方提交 profile。
`arm-off`、`arm-on`、`arm-static` 和 `arm-adaptive` 是显式本地实验配置，
不会改变官方提交配置：

```powershell
python main.py --input_file sample_data/dev.jsonl --output_dir artifacts/20260928-135512-submission --profile submission
python main.py --input_file sample_data/dev.jsonl --output_dir artifacts/20260928-135512-agent-default --profile agent-default
python main.py --input_file sample_data/dev.jsonl --output_dir artifacts/20260928-135512-arm-adaptive --profile arm-adaptive
```

ARM-Harness v2.1 的串行 accuracy-first runner 使用固定的
`reasoning_agent/error_notebook/eval_112.json`，并提供
`arm-v2.1-off`、`arm-v2.1-on` 和 `arm-v2.1-off-skill` 三个显式 profile：

```powershell
python scripts/run_arm_v21_eval112_timing.py --profile arm-v2.1-off --run-id ARM-V21-OFF-112-ACCURACY-001
python scripts/run_arm_v21_eval112_timing.py --profile arm-v2.1-on --run-id ARM-V21-ON-112-ACCURACY-001
```

v2.1.2 的 `arm-v2.1.2-off`、`arm-v2.1.2-on`、`arm-v2.1.2-adaptive` 和
`arm-v2.1.2-off-skill`
保持旧 profile 不变，显式启用 evidence-triggered Trust Gate；ON 在 Primary
不完整时改用一次有界 OFF finalizer。runner 也支持固定 30 题数据集：

```powershell
python scripts/run_arm_v21_eval112_timing.py `
  --profile arm-v2.1.2-off `
  --dataset-path sample_data/arm_fixed_items_30.json `
  --expected-records 30 `
  --selection-seed 20260905 `
  --run-id ARM-V212-FULL30-OFF-001
```

每题严格只执行一次 `solve()`，结果状态为 `complete`、`incomplete` 或 `error`；失败题也会写入
`answers.jsonl` 和 aggregate denominator，并保留 `final_failure_reason`。完整答复由本地 evaluator
评分，标准答案不发送给模型。报告同时记录 second-sample、resolver、safe-candidate 和 final-source
telemetry；Primary/Second 要求显式 `Final answer:` 终答，`answers.jsonl` 还保留完整的有界
`arm_v2_summary` diagnostics；call ledger 仅记录 `reasoning_content` 是否存在及其长度，
不保存完整内容。数据集缺失、答案字段缺失或记录数不符合 `--expected-records` 时 runner
会直接失败。本地结果不自动触发提交晋升。

v2.1.3 保留为历史显式实验模式；当前正式 selector 为 v2.1.4 CFR。CFR 的
`arm-v2.1.4-off`、`arm-v2.1.4-adaptive` 和 `arm-v2.1.4-cfr` 均共享 v2.1.4
实现；CFR 将 Challenger、Targeted Repair 与 Fresh Review 固定为正式 selector，
关闭 hybrid router 并使用 OFF 求解策略：

```powershell
python docs/releases/arm-v2.1.4-cfr-20261004/verify.py
```

`arm-v2.1.6-missing-candidate` 是仅用于本地配对实验的显式 profile：当 Primary
没有形成任何候选时，它才把第二次请求改为独立的短答案形成；已有候选仍使用 CFR
的 Challenger 路径。它不改变正式 selector，也不代表数学能力提升。预注册和运行命令见
[`docs/experiments/ARM-V2.1.6-MISSING-CANDIDATE-RECOVERY-20261005/preregistration.md`](docs/experiments/ARM-V2.1.6-MISSING-CANDIDATE-RECOVERY-20261005/preregistration.md)。

v2.1.3 的历史 selector 为 `arm-v2.1.3-off`，另有显式实验模式
`arm-v2.1.3-on`、
`arm-v2.1.3-adaptive` 和 `arm-v2.1.3-forced-ab`。它们使用正证据 Trust Gate、
structured backend 归因、ON continuation/OFF recovery 和 response-free
false-trusted-primary 统计；forced A/B 不使用 Early Stop 或 Resolver：

```powershell
python scripts/run_arm_v213_forced_ab.py `
  --run-id ARM-V213-FORCED-AB-FULL30-001 `
  --dataset-path sample_data/arm_fixed_items_30.json `
  --expected-records 30 `
  --selection-seed 20260905
```

Forced A/B 只把 A/B verdict、Oracle、rescue/damage 和转移计数写入聚合工件，
不把 gold 放入 runtime prompt，也不扩大官方提交接口。

四臂 promotion 对比（A=FSDF、B=ARM OFF、C=ARM ON、D=ARM Adaptive）使用同一固定题集、
endpoint 和 judge，并保留每题 response-free diagnostics：

```powershell
python scripts/run_submission_promotion.py `
  --run-prefix ARM-V212-PROMOTION-FULL30-001 `
  --dataset-path sample_data/arm_fixed_items_30.json `
  --expected-records 30 `
  --selection-seed 20260905 `
  --rounds 1
```

gate 默认要求正确数不低于 FSDF、invalid 不增加、runner error 不增加且平均调用不超过 3；
任何 gate 失败都不会改变 `SUBMISSION_CONFIG`。

ARM 配置及其逐次调用 reasoning mode 仅用于代码和本地实验验证；启用 ON 的
profile 会显式发送 `thinking_mode=true`，运行前应按冻结实验协议检查 endpoint 健康。
当前 `SUBMISSION_CONFIG` 启用 ARM v2.1.4 CFR；代码路径不代表数学能力或官方成绩提升，
正式成绩仍需独立官方评测。

该开关只影响本地 `main.py` runner；官方仍通过
`ReasoningAgent(client=official_client)` 使用 `SUBMISSION_CONFIG`，不会被本地
profile 按钮或命令行参数隐式改变。

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

提交前还应确认:`user_agent.py` 可正常
import;`ReasoningAgent(client=official_client)` 可初始化;client 失败时仍返回
可序列化非空 `final_response`;仓库无 API key、个人路径与样例答案特判;实际
提交配置与 A/B 报告中的配置一致。

## 当前路线

- **当前 checkout**：ARM v2.1.4 CFR 位于 Constraint-Fit Harness 的 Direct/Deep seam；
  Challenger、Targeted Repair 和 Fresh Review 受结构化证据门控制，RAG、Skill、答案 bank
  和历史候选均关闭，尚未形成新的官方数学能力结论。
- **历史运营锚**：`hetero_k5 @ 25f99b5`（GitCode `34bc353`），仅作为历史发布/回滚参照。
- **发布状态**：官方无参入口切换到 ARM v2.1.4 CFR。2026-10-04 的 100 题官方报告已经
  归档，但题目范围不同于历史 112 题记录，因此状态仍为 `DEPLOYED_EVALUATED_NO_PROMOTION`；
  远端分支状态以发布后的 ref 审计为准。
- **已归档/排除**(详见 `docs/excluded_approaches.md`):method_rag、Re2、CoD、
  P1 salvage、G 门控、TIR/回代验证、32k 天花板。
- **暂不引入**:LLM-as-judge 本地判分、PRM 组件、LangGraph/AgentScope、
  联网工具与任意代码执行。

详细证据与决策记录见按实验 ID 分类的 `docs/experiments/`、
[架构演进总表](docs/architecture_evolution.md)、
[每日官方评测归档](docs/official_evaluations/)、
[docs/excluded_approaches.md](docs/excluded_approaches.md)、
[docs/adr/](docs/adr/)、[docs/branches_map.md](docs/branches_map.md)。

## 官方提交

赛事特有规则以[飞书赛事文档](https://aicarrier.feishu.cn/wiki/L90FwD9gJiqdg0k33RCcHTdcnrb)
为准。评测拉取作品关联仓库的最新 `main` 分支(每日固定窗口,实测均在凌晨
队列后执行)。

1. 将可复现版本推送到队伍 AtomGit 组织仓库的 `main` 分支(走发布线克隆)。
2. 在作品页面保持关联与提交状态。
3. 每轮结果按五数判读并记入 `docs/official_evaluations/README.md`,回滚条件
   在发布记录中预写。

提交、推送和作品页面操作都应单独确认。本地数据集结果只用于研发,不代表
正式成绩。
