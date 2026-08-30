# PRE0-EXT-002 结果：外部题集烟测（AA-GATE6/§6a amendment 后合规窗）

- 窗口 ID：`PRE0-EXT-002`，类型：模型校准窗（不设正确率门）
- 运行：2026-08-30 15:41–16:20（单臂 12 solves，实际调用 60/60，0 停摆触发）
- 授权：上位 spec §6a Amendment（并发污染窗不计复跑额度；新 ID 重跑）+
  审核 S1 修复（契约口径 = 从 `final_response` 重新外部抽取）
- 数据：复用 PRE0-EXT-001 冻结选题（OlymMATH 首发 `5f83d12`，12 唯一问题）
- 判定：**PASS**——门 1–4 全过

## 1. 门判定

| 门 | 内容 | 结果 |
| --- | --- | --- |
| 1 | manifest 完整（revision/hash/许可/选题/seed/工件 sha） | ✓ |
| 2 | 12/12 完成、model error=0 | ✓（两轮 0 停摆，护栏零触发） |
| 3 | native judge 12/12 verdict、0 parser crash、0 fail-open | ✓ |
| 4 | contract/native 双口径差集、invalid、答案类型、调用与时延落盘 | ✓ |

## 2. 双口径结果（S1 修复后口径）

- **contract_score（`final_response` 外部抽取 + `judge_correct`）**：correct 1、
  unparseable 3（invalid 行 fail-closed）、unknown 8；12/12 行
  `contract_source=final_response_external_extraction`。
- **benchmark_native_score（math-verify 0.8.0，gold 方向固定）**：correct 1、
  incorrect 8、unparseable 3；0 crash。
- 差集：8 例 contract unknown ↔ native incorrect（本仓保守口径对截断难题的
  覆盖边界，与 JUDGE 窗结论一致）；无假阳性。
- 100% 截断复现（12/12 finish=length，avg 5.0 调用全打满）——与 EXT-001/2b
  一致，再次确认外部难题在 4096 预算下的形态。

## 3. 与 PRE0-EXT-001 的关系

- 本窗是 §6a 批准的合规窗；PRE0-EXT-001（attempt-1 健康失败、2a 并发污染、
  2b 描述性证据）全部工件保留作历史，不参与退出门证据。
- S1 修复生效：contract 口径不再采信 Agent 内部 `extracted_answer`，
  证明路径为 `final_response` → 外部抽取 → 判分（提交契约可判性的直接证据）。

## 4. 对下游的输入

- 外部题链路（含 `final_response` 契约口径）在修复后的基础设施上完全可复现；
- P1 构建 core120_v2 时沿用本窗的 native 判分配置与选题冻结流程。
