# PRE0-EXT-001 结果：外部题集与 native judge 烟测

- 窗口 ID：`PRE0-EXT-001`，类型：模型校准窗（不设正确率门）
- 选题：OlymMATH 首发 revision `5f83d12`，12 唯一问题（easy/hard 各 6、四领域各 3、
  ZH/EN 各 6、无同题跨语言），seed 20260830；manifest：
  [`selection_manifest.json`](selection_manifest.json)
- 判定：**PASS（attempt-2b）**——门 1–4 全过；attempt-1 健康失败按预注册 §5
  复跑一次后通过。

## 1. 运行历史

| attempt | 时间 | 结果 | 处置 |
| --- | --- | --- | --- |
| 1 | 08-30 02:41 | 12/12 行；**4 model error**；3 个 solve 因端点滴流停摆各挂 ~22800s（6.3h，占满 3 worker） | 健康失败 → 按预注册允许恰好一次复跑；Amendment A1 落地客户端停摆护栏 |
| 2a | 08-30 03:30→11:31 | 进程跨夜被系统休眠冻结后复活；期间与误重启的进程并发消耗端点 30 分钟（11:01–11:31） | 数据 12/12 零错误但**违反共享端点串行纪律** → `aborted`，仅存档不作为判定依据 |
| **2b** | 08-30 11:31→12:12 | **12/12 完成，model error=0**，无停摆（240s 护栏生效） | **本窗有效 attempt** |

## 2. attempt-2b 有效结果（baseline_hetero 单臂，60 调用预算内实际 60）

- 完整性/健康：12/12 完成、error=0、无熔断 ✓
- native judge（math-verify 0.8.0，gold 方向固定）：12/12 verdict、**0 parser
  crash**、无 fail-open ✓
- 双口径差集（诊断）：contract unknown×11 + correct×1；native correct×2 /
  incorrect×7 / unparseable×3（3 个 invalid 行 fail-closed 记录）。
  截断输出的 contract unknown 集中体现本仓保守口径对外部难题的覆盖边界，
  与 PRE0-JUDGE-001 结论一致。
- **100% 截断**（12/12 题 finish=length，平均 5.0 调用/题全打满 k5）：OlymMATH
  难题在 4096 预算下的预期形态，与隐藏集 88.7% 截断率同构——core120_v2 的
  判分必须按"截断态可抽取性"设计（双口径并行已验证可行）。
- 正确数（2/12 native 口径）仅作链路诊断，**不构成任何能力主张**，不与公开榜
  横比（32k vs 4096 预算差异）。

## 3. 对下游的输入

- 外部题端到端链路（hf-mirror 拉取 → revision 固定 → 静态验收（400/400 gold
  self-score）→ 求解 → native/contract 双口径落盘）**可复现**；
- 本地客户端停摆护栏（`INTERN_REQUEST_DEADLINE_SECONDS`）经真实停摆场景验证
  有效，后续模型窗默认启用；
- attempt-1/2a 的事故与处置已按 §8 Amendment A1 记录，工件全部保留
  （`pre0_ext_answers.jsonl`（a1）、`*_attempt2a_aborted_collided.jsonl`、
  `*_attempt2b.jsonl`、`ext12_dual_judgement_*.json`）。

## 4. 运行配置

- 臂：`baseline_hetero`（answer-first + hetero + adaptive k5/3 + 4096 + policy
  prompt，≤5 调用/solve）；workers=3；timeout=180s；temperature=0.6；
  `INTERN_REQUEST_DEADLINE_SECONDS=240`。
- 运行面：`PRE0-8.30` 分支（commit 99bb587 含护栏）。
- 原始题面仅存本地缓存 `tmp/pre0_ext_001/cache/`；仓库只保留选题 ID、hash 与
  manifest（MIT 许可仍按保守边界处理）。
