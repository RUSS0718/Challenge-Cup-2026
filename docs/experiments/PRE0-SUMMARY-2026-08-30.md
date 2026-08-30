# Pre-P0 汇总：评测可信度校准（2026-08-30）

状态：**PRE0_EXIT_CONDITIONS_MET_PENDING_USER_GO**（2026-08-30 晚更新）。

演进轨迹：首签 PRE0_COMPLETE → 独立审核否决（PRE0_BLOCKED_PENDING_PROTOCOL_
AMENDMENT）→ 两项协议变更获用户批准（spec §6a）→ AA-003 触发 gate6 旧判据
（ORIGINAL_GATE_FAIL / SUPPORTS_AMENDMENT）→ AA-GATE6 amendment 获批（spec §6c，
冻结文本）→ **AA-004 六门全过（最后校准窗）+ EXT-002 合规 PASS + PARITY 对
46c08dd 重签** → §6b 退出条件 1–5 全部满足，**仅剩条件 6：用户 GO**。

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
| PRE0-AA-002 | 历史校准证据 | 数据 6/6 门通过；gate5 改 mean 属事后改门——数据降为校准证据（§6a），不进入退出门 |
| PRE0-AA-003 | ORIGINAL_GATE_FAIL / SUPPORTS_AMENDMENT | 门 1–5 过（两轮 0 错误）；gate6 旧"持续占优"判据因同臂 +1/+1 触发——实证该判据过严，促成 §6c |
| PRE0-AA-004 | **PASS（6/6，§6c 口径）** | 最后校准窗：两轮 0 错误、胜者翻转、6a 字段 96/96、6b 重算 100% 一致、6c Fisher p=1.0、成本带内（375/480 调用）；formal gate 完整性模式 PASS |
| PRE0-EXT-001 | 描述性证据，不合规关闭 | attempt-1 失败 → 唯一复跑额度被 2a 占用（后遭并发污染）→ 又启动 2b，超额度；2b 保留为链路描述证据 |
| PRE0-EXT-002 | **PASS（门 1–4）** | §6a 批准的合规窗：12/12、0 错误、native 12/12 verdict 零 crash；契约口径升级为 `final_response` 外部抽取（S1 修复生效，12/12 行验证） |

## 2. 调用总数（审核修正）

| 窗口 | 调用 |
| --- | --- |
| AA-001 | 381 |
| AA-002 | 385 |
| EXT attempt-1 | 53 |
| EXT attempt-2a（并发污染，存档） | 60 |
| EXT attempt-2b | 60 |
| **首轮归档合计（审核认定漂移）** | **939** |
| EXT-002（§6a 批准补偿窗） | 60 |
| AA-003（§6a 批准补偿窗，ORIGINAL_GATE_FAIL） | 380 |
| AA-004（§6c 最后校准窗） | 375 |
| **全项目归档合计** | **1754** |
| 误启动未归档重复进程（11:01–11:33，被 kill） | 未计（至少） |

预算口径：原 spec 预算 540；§6a/§6c amendment 将 AA-003（≤480）、EXT-002（≤60）、
AA-004（≤480）列为批准的补偿窗，均未超各自窗口预算；939 的历史漂移保留记录、
不计入新窗预算。

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

## 4. 退出门核查（§6b，2026-08-30 晚更新）

| §6b 条件 | 状态 |
| --- | --- |
| 1. AA 链六门通过（§6c 取代后 = **AA-004**） | ✅ 6/6 门 + formal gate 完整性模式 PASS |
| 2. EXT-002 串行运行、final_response 双口径、12/12 零错误 | ✅ |
| 3. PARITY 对实际 HEAD ↔ release candidate（gitcode 46c08dd 单体）重签 | ✅ 11 场景逐字节一致 + 2 个 reverify 未决场景=§6a 第 3 条已批准已知差异 |
| 4. formal gate 完整性模式消费 manifest/answers/dataset hash/VOID/聚类 | ✅（AA-004 冒烟：integrity PASS） |
| 5. 总汇总记录全部 attempt、真实调用总数、每个失败/污染窗 | ✅ 本文件 §2 |
| 6. 用户审阅后给出进入 P1/P2 的 GO | ⏳ **待用户** |

注：P0 §7.1 官方判读已由用户完成（发4 ROLLBACK_REQUIRED，恢复 `hetero_k5 @
25f99b5` 的指针切换待用户授权执行）——该链路独立于 Pre-P0 退出门。

## 5. 协议变更决策记录（已闭环）

1. **AA 成本门**：用户批准 §6a（P95→mean latency）；AA-003 触发 gate6 旧判据
   后，用户再批准 §6c（AA-GATE6-2026-08-30，删除占优硬判据、gate6 改三段
   校验）；AA-004 为最后校准窗并全门通过。
2. **EXT 处置**：用户批准 §6a 第 2 条（并发污染窗不计复跑额度、新 ID 重跑）；
   EXT-002 合规 PASS，契约口径升级为 final_response 外部抽取。

两项变更的完整冻结文本见 spec §6a/§6c。

## 6. 审核确认已通过的部分（保留事实）

- 459→460 单元测试通过（新增僵尸遥测回归）；`py_compile`、`git diff --check` 通过。
- STATIC 窗机器证据、JUDGE 120 例链路、AA/EXT 全部原始工件与逐窗 manifest
  （已补全）均入库 `docs/experiments/PRE0-*/`。
- 分支 `PRE0-8.30`；所有收敛提交在本分支，未 push、未动 SUBMISSION_CONFIG、
  未动 gitcode 提交仓库（tip 仍 46c08dd）。
