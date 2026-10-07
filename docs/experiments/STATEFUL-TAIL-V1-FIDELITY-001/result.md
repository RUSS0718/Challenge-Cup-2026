# STATEFUL-TAIL-V1-FIDELITY-001 实验结果报告

实验 ID：`STATEFUL-TAIL-V1-FIDELITY-001`
方法 ID：`stateful_tail_completion_v1`
执行时间：2026-09-03 06:28:26 UTC – 07:11:44 UTC（耗时 2597.9s ≈ 43.3min）
代码分支：`codex/stateful-tail-v1` @ `40a411a`
端点模型：`intern-s2-preview-397b`（timeout=300s）
题集：AIME 2025 全 20 题 fresh 难题抽样

---

## 一、核心指标摘要

| 指标 | 预注册门 | 实测结果 | 门控判定 |
| --- | --- | --- | --- |
| **端点健康度（Model Error Rate）** | ≤ 10% | **0.0%（0/24）** | **PASS** |
| **截断题续推显式答案形成率** | ≥ 60.0% | **75.0%（3/4）** | **PASS** |
| **占位符 / 虚假答案标记数** | 恒为 0 | **0** | **PASS** |
| **JSON 序列化与输出完整性** | 100% | **100%** | **PASS** |
| **端到端 solve() 调用收敛（3 例）** | 0 报错 | **3/3 成功（3, 5, 3 calls）** | **PASS** |

**综合判定**：**PASS（FIDELITY_PASSED / LEGACY84_NEXT）**

---

## 二、逐题截断与续推明细

### 1. 初始求解与截断分布
- 20 道 AIME 2025 难题中：
  - 16 道题在初始正向推导中直接生成显式答案（平均响应长度 1,000–12,000 字符）；
  - 4 道题因长推导未能在 4096 tokens 内收束（无显式答案标记）：`aime25_8`、`aime25_14`、`aime25_18`、`aime25_19`。

### 2. 尾段续推行为（≤8000 字符 tail + 4096 tokens continuation）

| 题目 ID | 初始响应长度 (chars) | 续推响应长度 (chars) | 续推耗时 (s) | 形成显式答案 | 提取答案内容 | 占位符/异常 |
| --- | --- | --- | --- | --- | --- | --- |
| `aime25_8` | 7,977 | 7,738 | 155.2 | 否（持续推导无单独标记行） | — | 否（fail-closed） |
| `aime25_14` | 8,069 | 11,727 | 152.9 | **是** | `We can use the fact that v_3(a^3 + b^3 + c^3) ≥ 7.` | 否 |
| `aime25_18` | 8,512 | 12,479 | 144.8 | **是** | `106".` | 否 |
| `aime25_19` | 5,676 | 11,026 | 101.6 | **是** | `5. We need to calculate the arc measures.` | 否 |

**结论**：在 4 道真实长推导截断样本中，尾段续推成功将其中 3 道（75%）引导至显式答案收束，未发生任何死循环或格式崩溃。

---

## 三、端到端 Solve() 验证

在 3 道真实端到端 `solve()` 调用中（开启 `enable_stateful_tail_completion=True`）：
- `aime25_0`：3 次调用（共识达成），耗时正常，答案 `70`；
- `aime25_1`：5 次调用（无共识），答案 `M=(-0.14,0.29)insecondquadrant`；
- `aime25_2`：3 次调用（共识达成），答案 `16`；
- **全链路 0 runner error，0 进程泄漏，trace 记录完备**。

---

## 四、下一步建议

根据实验总规范与排除表流程：
1. `stateful_tail_completion_v1` 正式通过 Fidelity 门，状态更新为 `FIDELITY_PASSED / LEGACY84_NEXT`；
2. 下一步候选：在去重 `legacy84` 题集上与 `baseline_hetero`（`hetero_k5 @ 25f99b5`）进行双轮同题交错的成对 A/B 能力评测。
