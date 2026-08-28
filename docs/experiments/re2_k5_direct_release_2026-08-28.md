# re2_k5 直接发布记录(2026-08-28 晚)

状态:`DEPLOYED_UNVALIDATED_CANARY`(已推送 gitcode main,等待官方评测)。

## 决策与证据边界

- 战斗之夜(08-28)双窗均 VOID:refine 确认窗 baseline 臂 error 22.9%,
  CoD 筛窗双臂 14.6%/20.8%——两者都未取得搭载资格;
- 用户在剩余提交次数 <7、24:00 截止的约束下明确指令发布新版本;
- 时间紧张档 B(机制级理由 + 健康冒烟):Re2 为纯输入侧改动,
  题干在 user prompt 中二次呈现,调用数/调用结构/token 上限/输出约束零变化;
- 本地 complex48 A/B 未运行(端点长窗不可用),官方成绩五数全部未知。

## 发布内容

| 项 | 值 |
| --- | --- |
| 基线 / 回滚锚 | `25f99b5`(hetero canary,官方 Run #5 = 12/112) |
| runtime commit | `d9203f0` |
| 投票 | adaptive k5,内含 1 路 Alternative(不变) |
| 新变量 | `SUBMISSION_CONFIG.enable_re2_reread=True`(仅此一处) |
| 非 L0 调用上限 | 5(不变) |
| token 上限 | 4096/call(不变) |
| prompt 变化 | 仅 user prompt 追加"请再次仔细阅读题目:"+题干重述 |

## 验证

- 415/415 unittest(413 存量 + 2 新增 Re2 输入侧行为断言);
- py_compile 通过;agent 级断言:开启时题干在 user prompt 出现 2 次,
  关闭时 1 次;
- 未增加依赖、调用数、token 上限、重试或外部服务。

## 发布后

1. 官方日志归档并补入 `官方评测记录.md`(Run #6),与 Run #5 比较
   correct/invalid/runner error/截断率/耗时;
2. 回滚条件(预写):correct 回退、总时限恶化、runner error 上升 →
   回滚锚 `25f99b5`;
3. 本地 Re2 筛窗(baseline_hetero vs re2_k5)已按 240s 新超时排入凌晨队列,
   事后归因用,不作为发布依据。
