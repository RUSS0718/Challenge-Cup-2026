# hetero_k5 小筛 runtime 修正案（2026-08-27）

> 写定于新小筛启动前。原设计、题集、运行参数、VOID 与三项过筛门保持
> `hetero_k5_screen_preregistration_2026-08-27.md` 字面不变；只更正实现锚。

## 更正原因

旧锚 `cedad82` 虽注册 `hetero_k5` 开关，但 C0 初始 generation count=1，后续 adaptive
vote 没有调用 AlternativeReasoner，无法实现文档声称的 hetero 分配。直接用旧实现运行会得到
名称为 hetero、实际没有 Alternative 的无效对照。

## 新协议锚

- runtime / GitCode main：`25f99b5`；
- runtime 实现 commit：`18f4f5a`；
- `current`：C0 answer-first + adaptive k5 + 4096，heterogeneous=False；
- `hetero_k5`：唯一配置差异为 heterogeneous=True；
- 非 L0 早停时顺序为 Direct → Alternative → Direct；跑满 k5 时最多
  4 Direct + 1 Alternative；L0 仍为单次 Direct；
- 413/413 unittest、py_compile 与官方式无参 smoke 已通过。

## 不变门槛

1. 任一臂 model_error 率 >10%：整窗 VOID；
2. 正确率配对净失 ≤2；
3. candidate 平均 calls ≤ C0×1.10，P95 ≤ C0 P95；
4. candidate invalid+error ≤ C0；
5. 小筛通过只解锁正式门，不等于晋升；本次已发布 canary 的事实不得反写为 PASS。
