# refine_fresh 确认窗预注册修正案(hetero±refine,单窗)— 2026-08-28

> 运行前冻结。本修正案在 7 发作战表(对话裁决 2026-08-28)框架下生效:
> 发布档位为"时间紧张→B(机制级+健康冒烟)",refine 拥有存量证据
> (144 对 b=12/c=4,单侧 p=0.0384,ADR-0002),故以**单窗确认**代替原
> refine_fresh 双轮设计;原 `refine_fresh_r1/r2` 双轮方案作废,编号沿用
> refine_fresh_confirm。

## 研究问题

在**新在役基线(hetero_k5,官方 Run #5 = 12/112)**上叠加 refine
(P3 verify/revise,re-verify fail-closed)能否不劣化正确率与卫生,
且调用增量可接受——即发 1(下一官方窗)是否搭载 hetero+refine。

## 设计(冻结)

| 项 | 值 |
| --- | --- |
| 臂 | `baseline_hetero` vs `hetero_refine`,双臂 |
| 题集 | complex_capability_freeze_48 全量 |
| 轮数 | 单窗一轮,`--interleave-items` |
| 运行参数 | workers=3,timeout=90,retry=1,temp=0.6 |
| 协议锚 | codex/b1-4k-canary @ 本次运行 HEAD(含 18f4f5a 移植) |
| 前置 | dev3 探针(baseline_hetero 臂)3/3 无 model_error |

## void 门

任一臂 model_error 率 >10% → 整窗作废(P1/G 复测两次教训)。

## 确认门槛(两条全过 → 发 1 搭载 hetero+refine)

1. **正确率**:配对净失 ≤2(净增为强确认;净失 >2 即失败);
2. **成本与卫生**:平均 model calls ≤ baseline×1.35(refine 存量证据
   5.17 vs 3.92 ≈ +32%),P95 ≤ 8(effective 上限);invalid+error ≤ baseline 臂。

失败或 VOID → 发 1 改为 CoD 伴生(hetero+CoD 若其四门过)或 hetero 复测兜底;
refine 线回炉,不再追加窗口追显著。

## 与存量证据的关系

本次单窗仅是**确认**而非发现;正向结论的因果强度仍受单窗限制,
官方窗将承担复测职能。明确不做:不同窗池化、临时改门槛、
把 refine 的 P3 状态计数当正确率证据。
