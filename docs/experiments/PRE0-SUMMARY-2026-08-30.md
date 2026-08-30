# Pre-P0 汇总：评测可信度校准（2026-08-30）

状态：**PRE0_COMPLETE_PENDING_USER_GO**——五个窗口全部关闭且达到各自预注册
门；进入 P0（官方日志判读）与 P1（外部能力层）仍需用户授权，且发4 canary 的
官方日志回收是 P0 §7.1 的外部前置。

执行分支：`PRE0-8.30`（base = main `7779ab7`）；模型调用总消耗 **826 / 上限
1020**（AA-001 381 + AA-002 385 + EXT 60/0/60/60，attempt 失败窗不重复计费）。

## 1. 五窗结果

| 窗口 | 类型 | 结果 | 关键产出 |
| --- | --- | --- | --- |
| PRE0-STATIC-001 | 结构（零调用） | **PASS** | 配对键 `(dataset_sha,round,idx,variant)` 固化；重复/缺题/partial/hash 不可解析全部 fail-closed；9%/11% 健康门；熔断与 VOID 分字段；item-cluster sign test；legacy 重合 24/唯一 84 复现；medium60 8 条标签失配清单落盘 |
| PRE0-JUDGE-001 | 结构（零调用） | **PASS** | 120 例 ×3 判分器：gold 自判 3×120/120、零假阳性、零异常外泄；ARH 双形态位置/last-boxed canonical 120/120 一致；**单位错配在任何口径下不可判**（cm vs m）→ core120 选题红线；math-verify 0.8.0 本地固定（不进 requirements） |
| PRE0-PARITY-001 | 结构（零调用） | **PASS** | 重构包与单体 11 场景 transcript 逐字节一致；reverify 未决语义冻结为 fail-closed 回滚（并实测发现 3bed2b7 合并回归、已恢复，commit d84be6e 固化进 main） |
| PRE0-AA-001 | 模型校准 | 5/6 门 | 正确率协议无偏（聚类 b=0,c=0,ties=24）；gate5 P95 latency 比值 0.759 越带 → 按预注册判 BLOCKED 并给出修复证据 |
| PRE0-AA-002 | 模型校准 | **PASS（6/6）** | gate5 修复为 mean latency（0.988）；两轮 16:16/15:15 完全平局、聚类 b=1,c=1,p=1.0、Fisher p=1.0；成本/健康/顺序门全过 |
| PRE0-EXT-001 | 模型校准 | **PASS（attempt-2b）** | OlymMATH 首发 12 题链路可复现（400/400 gold self-score、native 12/12 verdict 零 crash）；**100% 截断**发现；attempt-1 3×6.3h 端点滴流停摆 → `INTERN_REQUEST_DEADLINE_SECONDS` 护栏落地并验证 |

## 2. 标定出的协议事实（后续实验直接引用）

1. **正确率噪声带（baseline_hetero，24 题/轮）**：同配置双臂逐轮 correct 差
   ≤2、item-cluster p=1.0——真实候选效应量小于此带不可分。
2. **成本带**：mean calls/tokens/latency 比值带 [0.90,1.10] 可达且稳定；
   P95@n=48 是尾部噪声统计，不得用作 ±10% 门（AA-001 实测证据）。
3. **健康门**：error rate ≤10% 在本端点可达（两窗实测 0–4.2%）；停摆护栏
   （240s 墙钟）是必需基础设施。
4. **判分双口径**：contract（保守三态）与 native（math-verify 0.8.0，gold
   方向固定，$-wrap，timeout 关闭）并行可行，差集即表示不一致清单；
   单位错配必须排除出冻结集。
5. **截断现实**：外部难题在 4096 预算下 100% 截断（与隐藏集 88.7% 同构），
   截断态可抽取性是判分设计的一等约束。
6. **表示纪律**：ARH 双形态在位置抽取与 last-boxed 两大判分假设下收敛同一
   canonical（120/120），提交表示有跨判分器安全区。

## 3. 代码与工件变更（PRE0-8.30 分支）

- `scripts/analyze_paired_ab.py` 重写（配对/健康/聚类契约）+ `tests/test_paired_analysis.py` 等 21+ 单元测试；
- `scripts/evaluate_protocol_ab_gate.py` 增 `--baseline`（向后兼容，formal gate 可消费 A/A 与未来窗口工件）；
- `llm_client.py` opt-in 请求墙钟护栏 + 3 测试（默认关闭，官方提交面不受影响）；
- `scripts/pre0_*.py` 六个窗口工具（构建/自测/校准/分析/判分）；
- `docs/experiments/PRE0-*/` 每窗 preregistration / manifest / answers / result 全套；
- 里程碑：`99bb587`（EXT-1 工件+护栏）→ `9f08bca`（EXT-2b PASS）→ `a0f0c67`（EXT manifest）→ `f43cd37`（AA-002 PASS）。

## 4. 退出门核查（规范 §6）

| 项 | 状态 |
| --- | --- |
| PRE0-STATIC/JUDGE/AA/EXT/PARITY 全部通过 | ✅（AA 经协议修复窗 AA-002 达成） |
| 自动 manifest 与现行 formal gate 已能消费工件 | ✅（新配对契约 + gate `--baseline` 消费演示） |
| 当前指针、官方记录、排除表、候选状态对齐 | ✅ 本地侧；**发4 canary 官方日志待回收**（外部事件，列为 P0 §7.1 输入） |
| 用户收到汇总并授权继续模型能力实验 | ⏳ 即本文件；**待用户 GO** |

## 5. 授权边界与下一步（需用户分别决定）

1. `PRE0-8.30` 是否合回 `main` / 推送远端（本窗未 push、未动 SUBMISSION_CONFIG、
   未动 gitcode 提交仓库）。
2. P0：回收发4（hetero+refine+ARH, gitcode tip `46c08dd`）官方日志 → 按规范
   §7.1 四分支判读 + §7.2 refine 未决语义计数（实验面已冻结 fail-closed）。
3. P1：按 §5/§8 构建外部能力层（core120_v2 等）——许可/缓存策略需用户确认
   （单位错配红线见 JUDGE 窗）。
4. P2：GSA `gsa_4call` 仍为 `EXPLORATORY_POSITIVE`，按 §9.1 三臂设计重证。
