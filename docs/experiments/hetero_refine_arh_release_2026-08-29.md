# hetero_refine_arh 直接发布记录(发4,2026-08-29 晚)

状态:`DEPLOYED_UNVALIDATED_CANARY`(gitcode main = `9311d8c`)。

## 搭载依据

- ARH 筛窗(今晚,240s,交错配对):`hetero_refine` 25/48 vs
  `hetero_refine_arh` **25/48**,双臂 **error=0/invalid=0**,配对 1:1 净 0,
  成本零增量(5.146=5.146)——四门全过,"不回退+零成本"确认;
- 证据背书:9 个判分实现源码核对,boxed+最简规范形为全口径安全区
  (docs/research/evaluation_adoption_提分行动_2026-08-29.md);
- 用户决策树预授权:ARH 干净且净 ≥0 → 搭载。
- 说明:ARH 的收益靶(官方 invalid 池)本地不可测(本地判分器自产),
  本筛职责为非回退确认;表示保险的官方收益待 Run #7 检验。

## 发布内容

| 项 | 值 |
| --- | --- |
| 基线 / 回滚锚 | `95d5700`(hetero+refine,发3) |
| runtime commit | `9311d8c` |
| 新变量 | SUBMISSION_CONFIG.enable_answer_dual_form=True(仅此) |
| 行为 | numeric 族 final_response = "最终答案:X" + "$\boxed{X}$"(最简规范形) |
| 调用/预算 | 零变化(effective 8 不变) |

## 发布后

1. 官方日志 → Run #7 记账,五数对照 Run #5(12/112/17/88.0%/4h24m),
   重点观察 invalid 是否较 Run #5/R6 显著下降;
2. 回滚条件(预写):correct 回退、invalid 反升、耗时恶化 → revert 至
   `95d5700`;
3. GSA 筛窗结果另档记录,发5 决策在 refine/ARH 判定之后。
