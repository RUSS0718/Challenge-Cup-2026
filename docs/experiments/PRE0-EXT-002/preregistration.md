# PRE0-EXT-002 预注册：外部题集烟测（amendment 后合规窗）

- 窗口 ID：`PRE0-EXT-002`
- 类型：模型校准窗，不设正确率门
- 预注册冻结时间：2026-08-30（amendment 批准后、重跑之前）
- 授权：上位 spec §6a Amendment（2026-08-30，用户批准）：并发污染窗不计复跑
  额度；以新 ID 重跑一次；契约口径升级为从 `final_response` 重新外部抽取
  （spec §4.3 contract_score 原义，修复审核 S1）。
- 前序：PRE0-EXT-001（attempt-1 健康失败 3×6.3h 停摆；2a 并发污染存档；
  2b 描述性证据 12/12 零错误、100% 截断）。

## 1. 协议

- 数据：**复用** `PRE0-EXT-001/selection_manifest.json` 冻结选题
  （OlymMATH 首发 `5f83d12`，12 唯一问题：easy/hard 各 6、四领域各 3、
  ZH/EN 各 6；本地缓存 `tmp/pre0_ext_001/cache/ext12_run.jsonl`，
  SHA-256 `451cb2cb…640abcf`），不重新选题。
- 臂：单一 `baseline_hetero`；≤12 solves、≤60 调用；workers=3；timeout=180s；
  temperature=0.6；熔断 8；`INTERN_REQUEST_DEADLINE_SECONDS=240`。
- 串行：AA-003 整窗关闭后执行。
- 工件增强：compact answers 含 `final_response`（本窗起契约口径可用）。

## 2. 判分（S1 修复后口径）

1. `contract_score`：对每题 `final_response` 用 `user_agent.extract_final_answer`
   重新执行**外部抽取**，再以 `evaluate_dev.judge_correct` 判分——回答
   "提交契约下是否稳定可判"（不再直接采信 Agent 内部 `extracted_answer`；
   两者并列记录）。
2. `benchmark_native_score`：math-verify 0.8.0，方向 gold 在前，$-wrap，
   timeout 关闭；输入同样为 `final_response` 外部抽取结果。
3. 两口径差集、invalid、答案类型、调用/时延照旧落盘。

## 3. 门

1. manifest 完整（上游 revision、文件 hash、许可、选题、seed、工件 sha）；
2. 12/12 完成、model error=0（健康失败允许恰好一次整窗复跑；再失败
   `ARCHIVED_VOID`）；
3. native judge 12/12 verdict、0 parser crash、0 fail-open；
4. contract（final_response 外部抽取）/native 双口径差集、invalid、答案类型、
   调用与时延成功落盘；
5. 不设正确率门，不据错题调整 Prompt。

## 4. 产物

`pre0_ext_report.json`、`pre0_ext_answers.jsonl`、`run_manifest.json`、
`ext12_dual_judgement.json`（final_response 口径）、`pre0_ext_result.md`。
