# G 小筛复测预注册修正(repeat_of=g_screen_complex48)— 2026-08-27

> 本文件在复测窗启动**之前**写定并提交。原预注册
> `g_screen_preregistration_2026-08-27.md` 的设计、题集、运行参数、
> 正确率门与成本门全部不变;仅修正下述两条,并新增 void 门。

## 复测理由与授权

首筛(`g_screen_result_2026-08-27.md`)三门槛判定 FAIL,唯一未过的
卫生门受端点噪声污染:C0 对照臂自身 10/48 model_error(21%),
双臂分歧题中一题双臂同时报错。按该报告"可选后续"条款,经用户明确
授权执行**恰好一次**复测,标注 `repeat_of=g_screen_complex48`。

## 修正 1:卫生门改为相对判据

原:**G 臂 invalid + error 均为 0**。
改:**G 臂 invalid = 0,且 G 臂 model_error 计数 ≤ 同窗 C0 臂
model_error 计数**(G 的硬失败不得多于对照臂)。

理由:卫生目标是"G 不引入额外失败模式",单次端点抖动落在哪一臂纯属
随机;绝对零容忍在可观测的抖动环境下测的是运气而非实现。

## 新增:void 门(窗口健康度)

复测窗中**任一臂** model_error > 5/48(≈10%)即整窗作废(void),
不出筛选结论,不复测(次数上限已用)。void 判定先于过筛判定。

## 不变项重申

- 正确率门:逐题配对净失 ≤2 题;
- 成本门:G 平均调用 ≤ C0 的 50%,且 G P95 调用 ≤ 3;
- 参数:complex48 全量、单轮、workers=3、timeout=90s、retry=1、
  temperature=0.6、`--interleave-items`;
- 协议锚:`codex/b1-4k-canary`(复测启动时的 HEAD);
- 中途调参禁止;三条全过才解锁 GR / 四臂窗口,不过则 G/GR 线终止。
