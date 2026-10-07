# hetero_k5 能力臂筛选预注册(current vs hetero_k5)— 2026-08-27

> 启动前冻结。实现:`Variant.heterogeneous` → `enable_heterogeneous_reasoners`
> (commit 本次运行时 HEAD);变体单变量性由 `test_hetero_k5_is_single_variable_over_current`
> 锁定(C0 全配置不变,k5 投票预算内运行时拆分为 1 路 alternative + 4 路 direct,
> effective 调用上限不变)。

## 背景

异构 reasoner 是仓库中**从未做过有效同窗 A/B** 的唯一现成能力杠杆
(ARCHIVED-not-REJECTED;曾有"无证据默认开启"的历史,P0 止血后锁 False)。
方法卡 RAG 已因双轮双负永久排除,不在本计划内。

## 设计(冻结)

| 项 | 值 |
| --- | --- |
| 臂 | `current`(C0)vs `hetero_k5`,双臂 |
| 题集 | complex_capability_freeze_48 全量 |
| 轮数 | rounds=1 先筛;两轮正式门仅在过筛后另行预注册 |
| 运行参数 | workers=3,timeout=90,retry=1,temp=0.6,交错配对 |
| 排期 | 在 P1 回归窗结束后串行执行,不得并行(共享端点) |

## void 门

任一臂 model_error 率 >10% → 整窗作废(今日端点拥塞已知教训)。

## 判定门槛(hetero 过筛 = 三条全过)

1. **正确率**:配对净失 ≤2 题(净失 >2 即 fail;p 值仅记录不作门);
2. **成本**:平均 model calls ≤ C0 × 1.10(k5 内部重分配,总量不应增长),
   P95 ≤ C0 的 P95;
3. **卫生**:invalid + error 合计不高于 C0 臂。

小筛结论不得表述为晋升;过筛后才安排 complex48×2 轮 + medium60 辅证的
双轮独立正式门(AGENTS.md 晋升要求)。
