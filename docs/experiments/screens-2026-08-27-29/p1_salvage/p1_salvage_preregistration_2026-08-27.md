# P1 失败路径抢救回归预注册(current vs current_salvage)— 2026-08-27

> 启动前冻结。实现:`enable_failure_salvage`(commit 789ba3c,
> TDD 7 测试);变体 `current_salvage` = C0 单变量 + 抢救开关
> (单变量性由测试锁定)。

## 研究问题

失败路径答案抢救(全部候选被拒/best 结构不可靠时,从被拒响应按
boxed > 标记 > 裸数字优先级抢救可判答案)能否在正确率不回退的前提下
显著降低 invalid。这是 official R6(invalid=20,全部计 0 分)的直接对策。

## 设计(冻结)

| 项 | 值 |
| --- | --- |
| 臂 | `current`(C0)vs `current_salvage`,双臂 |
| 题集 | 双集:public112 + complex48 |
| 轮数 | 每集 2 轮(rounds=2),`--interleave-items` 同窗交错 |
| 运行参数 | workers=3,timeout=90,retry=1,temp=0.6 |
| 协议锚 | codex/b1-4k-canary @ 本次运行时 HEAD |

**服务健康 void 门**:任一臂 model_error 率 >10%(沿用 G 复测教训:
错误与臂无关,超过阈值说明是环境噪声,整窗作废)。

## 判定门槛(P1 晋升本地门 = 两条全过)

1. **invalid 缩减**:salvage 臂合计 invalid(2 集 × 2 轮)< C0 臂合计,
   且缩减主要来自计算/填空/选择题(非数值题型不参与抢救);
2. **正确率不回退**:配对差(4 窗合并,b=salvage 胜/c=C0 胜)
   c − b ≤ 2;双侧二项检验 p ≥ 0.05 视为无差异、p < 0.05 且 b>c 才视为改善。

## 明确不做

- 不改成功路径行为(实现上零触碰);
- 不把本门槛表述为官方分数预期;过门后是否推送官方窗口另行决策。
