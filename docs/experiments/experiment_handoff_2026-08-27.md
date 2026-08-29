# Challenge-Cup 2026 实验交接(2026-08-27,审计修订版)

## 当前工作区(已核实)

- 仓库:`D:\project\challenge_cup_2026\Challenge-Cup-2026`,分支
  `codex/b1-4k-canary`。
- **两个 main 已分叉,引用分数必须注明指哪个**:
  - 提交仓库 main(gitcode/origin)= `b8b78aa`:C0 配置(answer-first + k5,
    `SUBMISSION_CONFIG` 已核实);官方每日窗口拉取的是它。
  - 本地 main = `e4b40c0`:canary profile(4096 单主调用 + B1 门控重试)。
    **不得把本地 main 直接推上远端**,会静默改回 canary。
- 协议快照:未提交工作区改动已按审计裁决落盘
  (2b4ba30,refine 复核 fail-closed + 运行器护栏;352 测试全绿);
  G/GR 变体实现于 472e0dd(354 测试全绿)。

## 重大勘误(相对旧版交接)

1. 旧版"当前部署基线 = answer_first + k5"与本地 main 矛盾:那是提交仓库
   main(b8b78aa,08-26 12:58 推送)的配置;本地 main 是 canary gated。
2. 官方评测历史配置每晚不同:R2=4k/k5、R3=32k/k5、R4=B1+4k 门控、
   R5=8k/k3(commit `9622b0f`,stable-baseline-8k-k2 线)。08-27 00:00
   窗口是 b8b78aa(C0)的官方首秀。
3. **refine 战役证据已恢复**(ADR-0002):原始工件在
   `.worktrees/weakness-fix-package-14/docs/challenger_refine_2026-08-26{,_answers.*}`,
   题集 complex48、双臂 legacy_4k_k5 vs _refine、3 轮 144 对;
   逐题重建 b=12 / c=4,p=0.0768(单侧 0.0384),与转述一致;
   分母口径修正为 **144 对**(旧"+8/288"把重跑行数当题数)。
4. R 战役继续使用,**不复用编号 R4/R5**;续窗以 refine_fresh_r1/r2 命名,
   冻结 complex48、同臂定义与配对口径。

## 已给出的决策(第二轮盘问裁决)

- Q1 工作区改动 → commit 到 codex/b1-4k-canary(已完成)。
- Q2 原始源恢复 → 恢复成功(见上),不走 fresh 重置分支;但
  `skipped_exact_refine_extension.json` 的"96 题源不存在"结论作废。
- Q3 refine_fresh 适用集 → complex48 主 + medium60 辅,两窗固定视界,
  单侧 α=0.05,原门槛判定;仅当探索性累计仍正向才升级正式门。
- Q4 G 小筛门槛(预注册于 g_screen_preregistration_2026-08-27.md):
  卫生(invalid=0 且 error=0)、净失 ≤2 题、平均调用 ≤ C0 的 50% 且 P95 ≤3。
- Q5 今晚顺序 → 快照提交 → 来源搜寻 → TDD 实现 G/GR → G 小筛;
  refine_fresh 两窗排下一会话主线。
- Q6 精确 G = 纯 variant 组合(零引擎改动),fail-closed 保原答案语义,
  已确认并实现(exact_g / exact_g_refine)。
- Q7 筛窗规模 = complex48 全量双臂交错;medium60 辅证留给 refine_fresh 阶段。
- Q8 文档对齐包 → 本文件归档 docs/experiments/,CONTEXT.md 词条 +
  ADR-0001/0002 同批落盘;`ponytail:ponytail` 技能引用删除(不存在)。

## 已核对的代码事实

- 变体定义 `scripts/evaluate_protocol_ab.py`(VARIANTS):现含
  current_family、gated_retry(_8k)、**exact_g、exact_g_refine** 等;
  exact_g = numeric_prompt + use_policy_prompt + gated_retry,effective 上限 2;
  GR effective 上限 5(基座+p3_call_boost 公式与 current_refine 一致)。
- 引擎零改动:门控重试骨架(`user_agent.py` B1 gate,fail-closed)复用;
  refine 上限在运行时由 p3_call_boost 提升(user_agent.py:920)。

## 下一步

1. G 小筛冒烟(dev.jsonl 3 题 × 双臂)验证管线;然后按预注册跑
   complex48 双臂交错窗;出报告后按三门槛判定。
2. G 过筛 → 安排 C0/R/G/GR 四臂同窗;G 失败 → 停 GR,不抢救。
3. refine_fresh_r1/r2 作为独立主线另行排期(不受本筛结果影响)。

## 当前未完成事项

- 尚未启动今晚任何模型调用实验(本文件提交时)。
- tmp/overnight_2026-08-26/ 全部为探索窗(formal_gate=false),
  归档或清理待办;官方日志(eval_log_*)仍在用户 Downloads,未入仓。
