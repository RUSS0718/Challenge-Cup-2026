# G 小筛预注册(exact_g paired screen)— 2026-08-27

> 本文件在筛窗启动**之前**写定并提交。判定门槛、题集与统计口径自本 commit
> 起冻结;筛选结论不得事后改用其他口径解释。

## 研究问题

精确 G(`answer-first/policy prompt 族 + verification-gated retry`,以门控重试
替换 k5 投票)相对 C0(`answer-first + k5`)能否在正确率不明显回退的前提下
显著节省调用成本。G 是成本前沿探索,**不是晋升候选**;过筛只解锁后续
C0/R/G/GR 四臂窗口,不作为任何默认路径变更依据。

## 设计

| 项 | 冻结值 |
| --- | --- |
| 臂 | `current`(C0)vs `exact_g`(G),双臂 |
| 题集 | `sample_data/complex_capability_freeze_48.jsonl` 全量 48 题 |
| 轮数 | 单窗一轮,`--interleave-items` 同窗交错配对 |
| 运行参数 | workers=3,timeout=90s,retry=1,temperature=0.6(与当晚探索窗一致) |
| 协议锚 | 分支 `codex/b1-4k-canary` @ 472e0dd(含协议快照 2b4ba30) |
| 中途调参 | 禁止;服务熔断则整窗作废(void),不作部分判定 |

## 判定门槛(G 过筛 = 三条全过)

1. **卫生**:G 臂 invalid + error 计数均为 0;
2. **正确率**:逐题配对计分下,G 相对 C0 净损失 ≤ 2 题
   (净损失 >2 即 fail;净增或打平视为通过);
3. **成本**:G 臂平均 model calls ≤ C0 的 50%,且 G 臂 P95 model calls ≤ 3。

## 与既有证据的关系

- 已有 gated r5/r6(medium12/public12)显示 replacement 形态的调用成本
  ~28%–30%(1.00–1.08 vs 3.58–3.83),但那些臂关闭了 answer-first/policy
  prompt 族,不能证明本设计 G 的正确率表现。
- fresh refine replication(refine_fresh_r1/r2)为独立主线,其设计与本筛
  结果互不依赖、互不引用。
