# 已排除方案归档（截至 2026-08-24）

> 目的：任何新会话/成员在提议新实验前先查此表，避免重复试错。
> 判定分四级：**REJECTED**（证据否定）/ **ARCHIVED**（不显著，留档）/ **SUPERSEDED**（被后续方案覆盖）/ **OPEN**（未关闭）。
> 官方评测为最终裁决；本地数据仅用于预筛。同窗口交错为必要证据标准（跨窗比较无效，见 §跨窗教训）。

## 一、官方评测否决（配置级）

| 方案 | 官方结果 | 对照（4k+k5=9.82%） | 判定 |
| --- | --- | --- | --- |
| 4k + k1（legacy 单调用） | 4.46% | −5.4pt | REJECTED |
| 32k + k5（应急提预算） | 8.04% | −1.8pt；54/112 runner error、9h23m | REJECTED（单调用时长爆炸撞 20 分钟/题上限） |
| **B1 + 4k**（验证门控重试单调用） | 8.04%（correct 9 / invalid 37） | −1.8pt | REJECTED |

## 二、本地 A/B 否决（机制级，同窗口交错 + McNemar）

| 方案 | 本地证据 | 判定 |
| --- | --- | --- |
| 失败退避（model_error 后等 1s） | Invalid 无降幅，出现首个 Incorrect；理论天花板 ≈ model_error 率 × 条件增益 | REJECTED |
| 终答冲突复算（单输出内双答案触发） | 触发频率过低（retry_count 与基线无差异），无法移动均值 | REJECTED（触发器思路并入验证门控重试留档） |
| 主调用温度 0.4 / 0.8（对照 0.6） | 均值 ±1 内，无增益 | REJECTED |
| **8k + k2**（baseline8k_k2） | 同窗 vs 4k+k5：净 −2，p=0.75 | REJECTED |
| **8k + k3**（k3_8k） | 同窗 vs 4k+k5：净 0，p=1.0 | REJECTED |
| **8k + k1 + temp0**（single_8k_t0） | 同窗 vs 8k+k2：−3（p=0.25） | REJECTED |
| k3 投票（4k，对照 4k 基线） | 净 +5/192，p=0.405 | ARCHIVED（不显著） |
| k5 投票（4k，对照 4k 基线） | 净 +5/192，p=0.267 | ARCHIVED（不显著；曾短暂上线后随 R3 失败回退） |
| k5 投票（32k） | 见官方 R3 | REJECTED |
| single_8k_t0 之外的 8k+k1 变体 | 被 8k+k2 同窗覆盖 | SUPERSEDED |

## 三、历史本地否决（2026-08-22 前，公共集证据）

| 方案 | 证据 | 判定 |
| --- | --- | --- |
| 数值题答案前置协议（单调用） | 8/21 protocol A/B（4096/temp0.6/公共集零截断）：**A 臂 74–77% → 37–44% 崩溃（−37pt），invalid 4→60/54 爆炸 15 倍**；A+B 同崩。与截断无关——prompt 本身与模型长思考模式冲突 | REJECTED（精确数字 2026-08-24 补录，源 docs/experiments/ 经 e4b40c0 归档） |
| 答案先行 + 投票（组合形态） | 同族 prompt（NUMERIC_ANSWER_FIRST_PROMPT）；基于 −37pt 先验预期 S2 同窗验证失败，部署已排除；S2 结果仅归档确认 | REJECTED（先验）/ S2 归档中 |
| 严格 salvage（boxed/末行兜底） | 公共集退化 | REJECTED |
| 6144 条件 token 重试 | 不稳定 | REJECTED |
| 长题 token 路由（证明/推导 6144） | 复杂冻结集 25/48 < 基线 26/48 | REJECTED |
| RAG / 方法卡（40 张离线卡） | 双轮正确率下降、延迟上升 | REJECTED |
| P2 异构推理（Direct+Alternative） | 未过门 | ARCHIVED（基础设施保留） |
| P3 逐步审核与修正 | 未过门，fail-open 边界 | ARCHIVED（基础设施保留） |
| 确定性求解器（直接解题） | 232 题仅 4 题安全命中 | ARCHIVED（opt-in；"回代验证"新形态见未决清单） |
| SymPy 受控证据（算术等价） | 无默认收益证据 | ARCHIVED（opt-in） |
| salvage 离线分析 | 无可靠恢复空间 | REJECTED |

## 四、流程级排除（方法论）

| 做法 | 教训 |
| --- | --- |
| 跨时间窗口比较实验结果 | 窗口漂移制造假增益/假回退（8k 假优势事件）——同窗口交错为必要条件 |
| 用本地公共集校准隐藏集行为 | 公共集截断率 ~0 vs 隐藏集 56–88%，长度分布完全脱钩 |
| 未过预注册门直接改 SUBMISSION_CONFIG | 32k 应急事件教训——一切晋升走门+评审 |
| PowerShell 字符串手术编辑 UTF-8 源码 | GBK 读取损坏中文正则——一律用 Edit 工具或 python 改文件 |
| dedup/归档保留"首次出现" | 曾丢失干净重跑数据——保留最后一次出现 |

## 五、未决清单（未被排除，证据不足待测）

| 方向 | 状态 | 备注 |
| --- | --- | --- |
| **PoT/TIR-first** | ARCHIVED（最终机会协议阶段二 0/36 程序有效率） | 规格见 `docs/superpowers/specs/2026-08-24-tir-final-chance-protocol.md` |
| 答案先行 + 投票（组合形态） | **PASSED**（净 +9/96，p=0.0039，c=0；已批准晋升，k3_8k 窗口后部署） | 8/21 单调用崩溃结论被组合形态推翻——配对证据见 docs/challenger_answer_first_2026-08-24.md |
| 候选答案回代验证（substitution check） | ARCHIVED（约束程序有效率 0/36，fail-closed 零误支持验证通过） | 与 TIR 同源教训：白名单 vs 模型生成程序的根本性失配 |
| 模式多样性投票（1×CoT + 1×PoT） | OPEN | 依赖 TIR 通过协议——TIR 已归档，本项随之冻结 |
| k5 早退阈值 3→2（纯效率调参） | ARCHIVED（净 −1，p=1.0） | 共识强度损失略大于效率收益 |
| 长度校准压力集建设 | **DONE**（24 题已入库并基线化：legacy k5 16.7%） | docs/length_pressure_set_2026-08-24.jsonl；后续实验必带压力维度 |
