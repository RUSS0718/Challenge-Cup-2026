# hetero_k5 直接发布记录（2026-08-27）

状态：`DEPLOYED_UNVALIDATED_CANARY`（等待 GitCode main 推送与官方评测）。

## 决策与证据边界

- P1 回归已触发 VOID；hetero 启动前 dev3 健康探针 3/3 含 model_error；
- `current vs hetero_k5` complex48 小筛没有运行，因而没有本地能力 PASS/FAIL；
- 用户在已知上述边界后明确要求“直接提交 hetero_k5”；本次发布记录风险接受，不改写预注册结论；
- 官方成绩、invalid、截断率、成本和总耗时全部未知，必须等待新官方日志。

## 发布内容

| 项 | 值 |
| --- | --- |
| 基线 / 回滚锚 | `242c480`（runtime 等同 C0 `b8b78aa`） |
| runtime commit | `18f4f5a` |
| 非 L0 调用上限 | 5 |
| token 上限 | 4096 / call |
| 投票 | adaptive k5，agree threshold=3 |
| reasoner 分配 | 最多 1 Alternative，其余 Direct；提前共识仍生效 |
| L0 | 单次 Direct，不进入 hetero 投票 |
| 其它实验 | P1/P3/RAG/B1/长 token 路由均保持关闭 |

审计发现旧 `cedad82` 只注册了 hetero 配置，但 C0 的初始 generation count=1，后续
adaptive vote 仍走普通 Prompt，无法实现其声称的 Alternative。`18f4f5a` 在 adaptive vote
的单一 Prompt 选择缝隙修复该问题：第一次补采样使用 Alternative，后续使用 Direct。

## 验证

- TDD 红灯复现：旧路径跑满 k5 时只有 1 个 direct 标签、0 个 alternative；
- 修复后跑满 k5：4 Direct + 1 Alternative；提前三次共识：Direct → Alternative → Direct；
- runner `current` / `hetero_k5` 除 `enable_heterogeneous_reasoners` 外配置一致；
- `413/413` unittest 通过；`py_compile` 通过；官方式无参构造、非空 final_response 与 JSON
  序列化 smoke 通过；
- 未增加依赖、调用上限、token 上限、重试或外部服务。

## 发布后

1. 下一次官方原始日志必须归档并补入 `官方评测记录.md`；
2. 与 Run #4 同时比较 correct、invalid、截断率、runner error、attempts 和总耗时；
3. 不用本次发布动作替代本地 A/B；
4. 若官方 correct 回退、总时限风险恶化或 runner error 明显增加，回滚到 `242c480`。

### 发布后本地窗口

20:36 第二健康探针仍为 `UNHEALTHY`：dev3 中 2/3 记录 model_error，平均延迟
315.48s、P95 445.81s。按冻结规则未启动 complex48；见
[`hetero_k5_health_probe_2036_result_2026-08-27.md`](hetero_k5_health_probe_2036_result_2026-08-27.md)。

21:30 第三健康探针仍为 `UNHEALTHY`：dev3 中 1/3 记录 model_error，平均延迟
235.20s、P95 356.70s。仍未启动 complex48；见
[`hetero_k5_health_probe_2130_result_2026-08-27.md`](hetero_k5_health_probe_2130_result_2026-08-27.md)。
