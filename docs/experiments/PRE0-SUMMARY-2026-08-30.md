# Pre-P0 汇总：评测可信度校准（2026-08-30）

状态：**PRE0_BLOCKED_PENDING_PROTOCOL_AMENDMENT**（2026-08-30 审核结论；此前
签发的 PRE0_COMPLETE 撤销）。

审核要点（独立审核，未运行模型调用）：STATIC 完成合规；JUDGE/PARITY 部分完成；
AA-002 属看过结果后改门（未经上位 spec amendment 与用户授权）；EXT 超出复跑
额度并发生共享端点并发；manifest 强制字段缺失；调用总数少报；formal gate 未
真正消费强制工件；deadline 护栏存在僵尸遥测污染缺陷。本文件按审核的最小收敛
动作更新。

## 1. 五窗状态（审核后）

| 窗口 | 审核状态 | 结论 |
| --- | --- | --- |
| PRE0-STATIC-001 | 完成（合规） | 配对键/重复缺题/VOID/聚类统计/84 题去重均有机器证据 |
| PRE0-JUDGE-001 | 部分完成 | 120 例链路可运行；**单位题型被 J2/J3 误判等价（实测），但该类被移出正式门**——正确结论是"单位题型不受支持、必须排除"，不得声称泛化"零假阳性"（已改措辞） |
| PRE0-PARITY-001 | 部分完成 | 工件记录 reverify 未决场景两面答案不同，与上位 spec"签名完全一致"冲突；fail-closed 修复进 main 后**未对当前 HEAD ↔ 实际 release candidate（gitcode 46c08dd 单体）重新生成签名** |
| PRE0-AA-001 | 未通过原规范 | gate5 P95 失败 → BLOCKED（维持）；另发现 gate6 首臂归属用原始 idx 而非 shuffle 位置（已按 seeds 重构重算，结论不变）、analysis 硬编码 seed（已参数化） |
| PRE0-AA-002 | 协议修复候选 | 数据 6/6 门通过（首臂修正后复算仍过），但 gate5 改 mean 是事后改门——**须经上位 spec amendment + 用户授权方可计入退出门** |
| PRE0-EXT-001 | 描述性证据，不合规关闭 | attempt-1 失败 → 唯一复跑额度被 2a 占用（后遭并发污染）→ 又启动 2b，超额度；2b 保留为链路描述证据；**双口径读的是 extracted_answer 而非 final_response 外部抽取**（runner 已修，未来窗生效） |

## 2. 调用总数（审核修正）

| 窗口 | 调用 |
| --- | --- |
| AA-001 | 381 |
| AA-002 | 385 |
| EXT attempt-1 | 53 |
| EXT attempt-2a（并发污染，存档） | 60 |
| EXT attempt-2b | 60 |
| **归档合计** | **939** |
| 误启动未归档重复进程（11:01–11:33，被 kill） | 未计（至少） |

上位 spec 预算为 **540**（一个 AA 窗 + 一个 EXT 窗）。实际运行了 2 个 AA 窗 +
3 个 EXT attempt，**预算与重跑纪律均已漂移**；全部历史保留，但原预算/退出门
不得用于签发。

## 3. 已完成的零调用收敛修复（2026-08-30）

1. `llm_client`：僵尸完成不再写入有序遥测切片（`orphan_completions` 计数；
   审核复现场景已加回归测试）。
2. `tests/test_llm_client.py`：双 `unittest.main()` 修复（直接执行时 deadline
   测试类此前不注册）。
3. `pre0_aa_analyze.py`：首臂归属按 `random.Random(seed)` 重构 shuffle 后位置
   计算（runner 实际口径）；seeds/arm-order/dataset-sha 参数化；两窗 analysis
   已离线重算（gate6 结论均不变，数字已修正）；不再依赖开发机绝对路径。
4. `evaluate_protocol_ab_gate.py`：新增 `--manifest/--answers/--dataset-sha256`
   完整性模式——校验 manifest 工件 sha、重复配对键、expected_n 完整性、
   error-rate 健康门，并输出逐轮 + 聚类 exact McNemar（AA-002 工件冒烟通过，
   全部从工件复现）。
5. runner：compact answers 新增 `final_response` 与 `schedule_position`
   （隐私安全的契约字段 + 调度复现字段；未来窗生效）。
6. 三窗 manifest 补齐 §4.1 强制字段：真实 commit（AA-002 修正 `ff..` 占位 →
   `9f08bca`）、dirty 清单、运行时代码 hash、python/sympy/requests/math-verify
   版本、judge/prompt 文件 hash、数据集与工件最终 sha256、分 attempt 真实调用数。

## 4. 退出门核查（审核后）

| 项 | 状态 |
| --- | --- |
| STATIC/JUDGE/AA/EXT/PARITY 全部通过 | ❌（JUDGE/PARITY 部分完成；EXT 不合规关闭；AA-002 待 amendment） |
| manifest/formal gate 消费工件 | ✅ 修复后成立（完整性模式冒烟通过）；此前汇总的 ✅ 属过早声明，已撤回 |
| 指针/官方记录/排除表/候选状态对齐 | ✅ 本地侧；发4 官方日志待回收（P0 §7.1 输入） |
| 用户授权 | ⏳ 两项协议变更待确认（见 §5） |

## 5. 待用户确认的两项协议变更（确认后才允许任何重跑）

1. **AA 成本门统计量**：上位 spec 固定 P95 latency 比值 ∈[0.90,1.10]；AA-001
   实测同配置双臂 P95@n=48=0.759（尾部噪声主导）。是否批准上位 spec amendment
   将该门改为 mean latency 比值 ∈[0.90,1.10]（P95 降为记录项），并以新窗口
   重跑受影响的 AA？
2. **EXT 污染窗处置**：attempt-1 失败后唯一复跑额度已被 2a 占用（后并发污染）。
   是否批准"并发污染窗不计入复跑额度、允许以新 ID（PRE0-EXT-002）按原协议
   重跑一次"，并以 `final_response` 外部抽取作为契约口径（审核 S1 的修复）？

获得确认后：只重跑受影响的 AA（新窗 + amendment 引用）与 PARITY（零调用，
当前 HEAD ↔ gitcode 46c08dd 单体）；EXT-2b 保持描述性证据，是否重跑按上面
第 2 项决定。在此之前 **PRE0 = BLOCKED**，不进入 P0/P1 能力实验。

## 6. 审核确认已通过的部分（保留事实）

- 459→460 单元测试通过（新增僵尸遥测回归）；`py_compile`、`git diff --check` 通过。
- STATIC 窗机器证据、JUDGE 120 例链路、AA/EXT 全部原始工件与逐窗 manifest
  （已补全）均入库 `docs/experiments/PRE0-*/`。
- 分支 `PRE0-8.30`；所有收敛提交在本分支，未 push、未动 SUBMISSION_CONFIG、
  未动 gitcode 提交仓库（tip 仍 46c08dd）。
