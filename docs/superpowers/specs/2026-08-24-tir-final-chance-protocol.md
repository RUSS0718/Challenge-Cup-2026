# TIR 最终机会 × 稳定基线 整合协议（2026-08-24）

> 状态：已批准的执行框架。两个工作轨互不阻塞，汇合点在阶段二。
> 基线轨分支：`codex/stable-baseline-8k-k2`；TIR 轨分支：`codex/pot-tir-executor`。

## 0. 背景与角色划分

官方 R3（32k/k5，accuracy 8.04%）证明：思考长度随预算膨胀，单调用 9+ 分钟，
54/112 题撞死在 20 分钟 runner 上限。**任何"更大天花板"策略都被时间维度否决。**

| 轨 | 分支 | 内容 | 状态 |
| --- | --- | --- | --- |
| 基线轨 | `codex/stable-baseline-8k-k2` | SUBMISSION_CONFIG → 8192 上限 + 2 样本共识（k2/agree2/max_calls2） | 本分支已实现，320 测试绿 |
| TIR 轨 | `codex/pot-tir-executor` | pot_executor + 模式 C/A + runner 变体（367 测试绿，**未提交**） | T1 已跑（见 §5），进入最终机会协议 |

**基线轨合并 main 后即为提交配置与一切 TIR 实验的对照臂**——无论 TIR 成败，
8k+k2 都是下一个官方窗口的提交行为。

## 1. 稳定基线的时间账（为何是 8192 + k2）

- 实测生成速度 ~45–60 tok/s；8192 上限 → 单调用 ≤ ~3 min
- k2（agree=2, max_calls=2）：两样本一致即共识；不一致取首候选（确定性）
- 最坏单题 ≈ 2 × 3 min + 重试余量 ≈ 8 min ≪ 20 min；整轮 ≈ 112 × 4 min / 3 并发 ≈ 2.5 h ≪ 6 h
- R3 的 9h23m 与 54 个 error 由 32k×k5 的 45 min 最坏组合导致，本配置从根上消除

## 2. TIR 最终机会协议（用户批准版 + 落地细化）

前提约束：只用公开 `client.chat(messages, temperature, max_tokens)`；
**thinking-on 是常态**（不可依赖 `INTERN_THINKING_MODE=false`）；等稳定基线部署后再实验。

### 阶段一：离线验收（零官方调用，TIR 轨内完成）

1. **安全攻击集转正**：12+ 项对抗探测（import/eval/getattr/静态与运行时巨型幂/
   while/f-string/dict/属性访问/字符串走私/no-print/超时路径）固化为
   `tests/test_pot_executor.py::AttackSurfaceTest`，断言零误接受。
2. **执行器耗时口径修正**：`pot_execute` trace 事件拆分 `model_gen_ms` 与
   `execute_ms`——当前实现把模型生成时间算进了执行耗时，违反口径。修复点：
   `_generate_pot_candidate` 中 `started_at` 只应包住 `execute_program` 调用。
3. **程序自正确率统计**：逐程序对照本地 ground truth，初始程序与修复程序
   分开统计；废弃"执行成功题的最终答案正确率"这一稀释指标。
4. **`pot_max_tokens` 1536 → 8192**：T1 实测 main_length_rate 0.69–0.85——
   thinking-on 下程序请求同样膨胀，1536 导致 `no_program` 频发（T1 探测
   effective_rate 仅 0.667@dev）。同时修复围栏正则（`extract_program` 允许
   ```python 后无换行）。
5. **附带语法补丁**（一次性的 v1.1，非迭代）：白名单增加执行器侧函数包装
   `doit(expr)`（内部实现 `expr.doit()`，模型侧仍是白名单名调用），解决
   `Sum` 不求值问题。

### 阶段二：可行性门（公共 112 + 复杂 48 各一轮，tir_first vs 稳定基线交错单轮）

| 门 | 判据 |
| --- | --- |
| G1 程序有效率 | 适用题（数值题型）程序有效率 ≥ 70% |
| G2 无效率 | Invalid = 0 |
| G3 公共集准确率 | ≥ 75%（T1 参考值 78.6–80.4%，应可达） |
| G4 程序自正确率 | 单独过门：程序答案对 ground truth 的正确率 ≥ 同题 CoT 臂自正确率（非劣），且绝对值 ≥ 60% |

**任一失败 → 永久归档 TIR-first，不再追加 prompt/few-shot/白名单迭代。**

### 阶段三：晋升实验（全部通过后，零代码调整）

- 复杂冻结集 ×4 轮交错：`submission_k5`（此时即 8k+k2 稳定基线）vs `tir_first`
- McNemar p<0.05 **且** 净增 ≥ +8/384 item-rounds
- 通过 → 仅进入晋升评审（人工），不自动上线

## 3. 预算一致性表（两臂统一）

| 参数 | 稳定基线（对照臂=提交配置） | tir_first（处理臂） |
| --- | --- | --- |
| max_tokens / l0 | 8192 | 8192 |
| pot_max_tokens | — | 8192（阶段一第 4 项修改后） |
| max_model_calls | 2 | 2（TIR 主调用 + 至多 1 次修复，或 1 次 TIR + 1 次 CoT 重采样） |
| 投票 | k2/agree2 | 同（TIR 候选入池参与等价分组共识） |
| 温度 | 0.6 | 0.6 |

注意：k2 预算下 TIR 臂的实际形态 = 首调用程序请求，成功则剩 1 次调用给 CoT
交叉验证；失败则修复调用耗尽预算。这是"程序优先、共识兜底"的最紧凑形态。

## 4. 协调事项

1. **pot-tir 工作区有未提交实现**：先按任务分 3 个 commit（executor / wiring /
   runner-gate），再 rebase 到 `codex/stable-baseline-8k-k2`（或合并）——阶段二
   必须在新基线上跑。
2. **B1+4K 实验窗口**（另一工作区）：与基线轨无文件冲突；若需要不同参数的
   变体，用 `VARIANTS` 注册，勿改 `SUBMISSION_CONFIG`。
3. 基线轨合并 main + 推送 gitcode 后，下一个官方窗口即用 8k+k2。

## 5. 回滚

- 基线轨：SUBMISSION_CONFIG 单点改回（历史值 4096/k1 或 32768/k5 均有记录）
- TIR：`enable_tir_first` 默认关，删除即移除
