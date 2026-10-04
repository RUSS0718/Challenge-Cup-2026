# 最近十次 Codex 编程任务审查（2026-10-05）

## 结论先行

这十条记录不是十种不同模型，而是最近十个在本仓库工作的 Codex 任务窗口。问题主要来自仓库的信息拓扑：当前发布状态、实验状态、运行工件和分支状态分别散落在代码、README、历史实验文档、工作区副本和长期记忆中，代理需要通过大量搜索和哈希比对才能确认“现在到底在运行什么”。

当前最值得优先修复的不是继续增加架构说明，而是建立一个由代码和发布清单生成的唯一运行时事实源，再让旧文档显式标记为历史材料。

## 样本和方法

样本是当前任务之前，最近十个 `kind=codex`、工作目录位于 `D:\project\challenge_cup_2026` 的任务窗口。读取了线程元数据、用户消息、代理终答和命令事件。线程页最多返回十个 turn；带 `hasMore=true` 的任务只按已返回部分统计，因此耗时是下限或可见部分累计，不代表严格的日历耗时。

搜索信号是命令中出现 `rg`、`Select-String`、`git log/show/grep` 等检索命令的近似计数；文档读取信号是命令中出现 `Get-Content`、`git show` 等读取命令的近似计数。

| 任务窗口 | 可见 turn 耗时 | 命令数 | 搜索信号 | 文档读取信号 | 主要摩擦 |
| --- | ---: | ---: | ---: | ---: | --- |
| 持续优化 invalid rescue 实验 | 338.9 分钟 | 618 | 62 | 318 | 多轮实验、PR、handoff 和历史报告并存 |
| 检查 GRH 评测运行状态 (2) | 304.7 分钟* | 207 | 39 | 97 | 运行副本、定时任务和架构审计交叉 |
| 补齐混合证明数值题判定 | 243.9 分钟 | 533 | 118 | 277 | 大量源码/测试/技能读取，输出多次截断 |
| 根据 PR #2 (3) | 230.6 分钟 | 173 | 47 | 83 | 需要重建 v1.1 与实验脏工作树的差异 |
| 根据 PR #23 v1.1 | 222.6 分钟 | 138 | 30 | 61 | 依赖 PR、逐题记录和多个版本口径 |
| 检查 GRH 评测运行状态 | 138.6 分钟 | 319 | 71 | 198 | 运行目录、分支、配置和进程状态分散 |
| 根据 PR #2 (2) | 99.3 分钟 | 101 | 29 | 78 | v1.2 方案、预检和停止门分散在文档中 |
| 下午四点 MATHHARNESS (2) | 77.5 分钟* | 133 | 35 | 64 | 续跑、磁盘耗尽、路径错误和分支误认 |
| 按文档完成升级修正 | 71.4 分钟 | 124 | 17 | 78 | 需要将旧 v1.1 锚点与新 v1.3 代码隔离 |
| 核对 GRH V1.1 评测回退 | 15.7 分钟 | 98 | 52 | 57 | `GRH v1.1` 与 `arm-v2.1.3-off` 命名不一致 |

可见 turn 时长相加约 **1,743 分钟（29.1 小时）**；这只是任务记录累计，不应当解释成连续占用时间。最明显的检索热点是：invalid rescue、GRH 运行状态、版本发布复现和评测续跑。

## 已确认的定位问题

### 1. 发布状态没有机器可查询的唯一入口

代理曾经需要同时检查 `README.md`、`CONTEXT.md`、`docs/branches_map.md`、GitCode/GitHub ref、脏工作树和运行工件，才能确定 119 基线。一次发布核验还发现：GitHub main 并不包含实验时脏工作树中的十个文件，必须用文件哈希恢复发布树；这说明 commit SHA 单独不足以描述实验状态。

当前已有 CFR 发布协议和 manifest，但它们没有成为所有任务的第一入口，且旧文档仍能被全文搜索命中。见 [`docs/releases/arm-v2.1.4-cfr-20261004/protocol.md`](../releases/arm-v2.1.4-cfr-20261004/protocol.md)、[`docs/branches_map.md`](../branches_map.md)。

### 2. 评测范围没有统一的机器字段

代理反复在 112 题官方评测、221 题本地 proxy、221 题回放和 119 correct 本地诊断之间切换。现有官方评测索引明确只收录官方 112 题结果，但运行目录名和报告格式没有强制区分 `official`、`proxy`、`local_replay`、`smoke`。这使得“119 correct”很容易被误读为官方隐藏集分数。

### 3. 旧文档仍使用“当前”语气

仓库扫描到 13 个 Markdown 文件包含“当前默认”“当前正式”或“当前工作区实验配置”这类状态性表述，其中包括历史文档和 `.workbuddy/memory/MEMORY.md`。两个直接冲突例子：

- `.workbuddy/memory/MEMORY.md` 标注为 2026-08-13，并写着“无时间限制、无调用次数硬上限”；当前 [`AGENTS.md`](../AGENTS.md) 明确规定单题 20 分钟、整轮 6 小时及调用/预算约束。
- [`docs/experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md`](../experiments/math_reasoning_agent_experiment_driven_spec_2026-08-29.md) 的 2026-09-03 段落把 `contextual_answer_reconstruction_v1` 写成 GitCode main 默认路径；当前 README、CONTEXT 和 CFR 发布协议都把 `arm-v2.1.4-cfr` 作为正式 selector。

这不是代理“不会查”，而是检索结果本身没有可靠的时效优先级。

### 4. 长文件和多副本放大了检索成本

`user_agent.py` 当前约 2,200 行；父目录同时存在 `Challenge-Cup-2026`、`Challenge-Cup-2026-v11-release`、`Challenge-Cup-20261001`、`recovered` 和 `tmp`。评测任务还会产生多个相似的 `official_proxy_*`、`GRH-*` 和 resume 目录。代理必须靠全文搜索、路径比对和进程检查来建立上下文。

## 建议的治理顺序

### P0：生成唯一的当前发布状态

新增一个由代码生成的 `docs/current_release.json`（或等价文件），至少包含：

```json
{
  "target_ref": "gitcode/main",
  "commit": "…",
  "submission_mode": "arm-v2.1.4-cfr",
  "status": "DEPLOYED_UNVALIDATED_CANARY",
  "rollback_anchor": "43a02da",
  "official_evaluation": null,
  "runtime_file_sha256": {},
  "generated_at": "…"
}
```

由脚本从 `SUBMISSION_CONFIG`、Git ref 和 CFR manifest 生成；README、CONTEXT 和分支地图只链接它，不再手写 selector。代理进入任务后的第一条命令应是读取这个文件并运行一致性检查。

### P0：强制区分评测范围

把 `evaluation_scope`、`dataset_id`、`dataset_sha256`、`official_evaluation`、`git_commit`、`config_selector`、`dirty_tree` 写入每个 run manifest。runner 在缺少这些字段或范围不匹配时拒绝合并统计。目录名使用固定前缀，例如 `official/`、`proxy/`、`local-replay/`、`smoke/`。

### P1：给历史文档加状态元数据并做过期检查

为 `docs/experiments/`、`docs/9.28/`、`.workbuddy/memory/` 中的文档增加 `status`、`last_verified`、`supersedes` 和 `source_ref`。任何标记为 `ARCHIVED` 的文件不得出现未解释的“当前默认/当前正式”。CI 只检查状态语句和链接，不要求一次性重写历史内容。

`.workbuddy/memory/MEMORY.md` 应改成明显的历史笔记，或迁移到 `docs/archive/legacy/`；它不应继续看起来像运行时规则。

### P1：提供发布、分支和运行的一键盘点命令

新增只读命令，例如 `python scripts/show_repo_state.py`，一次输出：当前 checkout、工作树是否 dirty、GitHub/GitCode refs、`SUBMISSION_MODE`、CFR manifest、活动 worktree、最近 run manifest 和可用回滚锚。它应替代代理分别运行十几个 `git`、`rg`、进程和路径命令。

### P1：把实验处置表做成可查询注册表

现有 [`docs/excluded_approaches.md`](../excluded_approaches.md) 是重要事实源，但全文较长。保留 Markdown 作为人读版本，同时增加机器可读的 `docs/experiment_registry.json` 和查询命令：

```powershell
python scripts/experiment_status.py --id ARM-V2.1.4-CFR-20261004
python scripts/experiment_status.py --status REJECTED,ARCHIVED
```

每条记录至少包含 `method_id`、`status`、`baseline`、`dataset_scope`、`last_evidence`、`restart_rule` 和报告路径。这样代理无需搜索数百行历史表格来判断一个方案能否重跑。

### P2：降低长文件和输出的进入成本

不建议立即重写整个 `user_agent.py`。先稳定发布状态和入口查询，再在后续修改中逐步把配置、提交 facade、求解编排和兼容层拆成可独立定位的模块；新任务应优先从 `submission_config.py`、CFR harness 和 release verifier 进入。运行命令默认输出摘要和工件路径，详细 raw 输出只写 `artifacts/<run_id>/`。

## 已有的好基础

- [`docs/ARCHIVE_INDEX.md`](../ARCHIVE_INDEX.md)、[`docs/official_evaluations/INDEX.md`](../official_evaluations/INDEX.md) 和 [`docs/branches_map.md`](../branches_map.md) 已经在尝试建立导航与证据边界。
- `docs/releases/arm-v2.1.4-cfr-20261004/manifest.json` 已记录运行文件哈希、回滚锚和未验证状态。
- [`AGENTS.md`](../AGENTS.md) 已明确赛事时限、隐藏评测约束和实验闭环纪律。
- 当前活动 worktree 已收敛为一个，历史 worktree 通过 archive ref 保留。

下一步应把这些已有材料串成机器可查询的入口，而不是再建立一套平行的手工状态文档。

## 2026-10-05 实施状态

上述治理顺序已落地为一组可审计入口：

- `docs/current_release.json` + `scripts/show_repo_state.py` 汇总 checkout、Git ref、正式
  selector、release manifest、runtime hash 和最近 run manifest；`--check` 在 selector 或
  runtime hash 不一致时失败。
- `reasoning_agent.manifest_schema`、`ArtifactManager` 和
  `scripts/validate_run_manifest.py` 统一 `evaluation_scope`、题集标识/哈希、commit、脏树
  和官方标记；旧工件保持 `unknown`，不会被猜成 local replay。
- `docs/experiment_registry.json` + `scripts/experiment_status.py` 提供方案处置的机器查询，
  `docs/excluded_approaches.md` 继续作为人读的完整处置表。
- `scripts/check_doc_freshness.py` 和历史文档的状态 front matter 让过时的“当前默认”表述
  进入可检查路径，而不是靠代理记忆判断。

v2.1.5 的十轮 paired replay 也按上述范围字段落档；结果为
`ENGINEERING_NOT_ACTIVATED / NO_CAPABILITY_CONCLUSION`，详见
[`ARM-V2.1.5 result`](../experiments/ARM-V2.1.5-BOUNDED-TAIL-RECOVERY-20261005/result.md)。
这次结果没有解锁正式 selector；后续只执行已预注册的 activation probe，避免把未触发
机制的负结果误写成能力否定。

## 证据边界

线程耗时和搜索计数来自 Codex 线程事件，是检索成本的信号，不是模型能力基准；部分线程有未加载的更早 turn，且少数任务页带 `hasMore=true`。历史文档中的分数和配置只在其注明的范围内成立，不能据此推断 CFR 的官方隐藏集成绩。当前 CFR 发布协议明确写着官方成绩仍为空，见 [`docs/releases/arm-v2.1.4-cfr-20261004/result.md`](../releases/arm-v2.1.4-cfr-20261004/result.md)。
