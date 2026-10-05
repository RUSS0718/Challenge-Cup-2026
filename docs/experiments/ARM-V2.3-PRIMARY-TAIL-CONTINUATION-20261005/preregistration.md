# ARM-V2.3-PRIMARY-TAIL-CONTINUATION-20261005 — preregistration

状态：`OPEN / DEFAULT_OFF`

## 目的与假设

2026-10-04 官方报告显示大量请求以 `finish_reason=length` 结束；v2.1.8 的 compact
finalizer 和 v2.2 answer-commit-first 又分别出现了正确答案损失。v2.3 测试一个更窄的
假设：当 Primary 没有形成可解析候选、但进程内仍有一段有限原始输出时，把同一 Primary
输出的尾部交给一次受限 continuation，让模型沿原轨迹完成结论。若 Primary 已有完整
incumbent，则保持 v2.1.4 CFR Challenger，不重新生成或替换它。

该假设只改变“无候选且有部分文本”的第二次请求计划；它不改变 parser、selector、正式
`SUBMISSION_CONFIG`、官方 selector、答案库、RAG、Skill 或模型 client 契约。原始尾部只
用于同一进程内构造 continuation prompt，不写入 trace、manifest 或提交工件。

## 唯一变量与对照

- 候选：`arm-v2.3-primary-tail`，`arm_harness_version=v2.3`。
- 对照：`cfr-primary-tail-pressure`，使用 `arm-v2.1.4-cfr`。
- 两臂均 bank-off、RAG-off、Skill-off，Primary 请求 `2,048` tokens，第二次请求上限
  `4,096` tokens，总预算 `16,384` tokens；候选 continuation 实际最多请求 `2,048`
  tokens，未触发时仍使用原 CFR Challenger。
- 候选与对照共享题目、顺序、模型端点、并发和本地 judge；模型请求不包含 gold。

## 数据与配对

T01–T02 使用 5 个新 OlymMATH 记录，T03–T04 使用另外 5 个新 OlymMATH 记录，T05–T06
使用 5 个新 AIME 记录，T07–T08 和 T09–T10 各使用 5 个新 HLE Math 记录。题目与
X/Y/Z/Q 压力窗口不重叠，共 10 轮、25 条 paired records、50 条 arm records。

数据文件哈希在运行 manifest 中记录；运行前必须通过 SymPy 评分依赖、题集键完整性、配对
清单和 gold 隔离检查。

## 预注册门

1. **VOID 门**：任一题集哈希、配对清单、manifest、SymPy 预检或模型错误记录缺失，整窗
   作废；不得挑选剩余指标。
2. **协议门**：候选所有触发记录必须标记 `primary_tail_continuation`，触发时只使用
   有限尾部和一次受限 continuation；完整 incumbent 不得触发 continuation；两臂预算相同。
3. **安全门**：候选不得出现任何 `correct → incorrect`；不得增加 model error；不得
   超过每题两次逻辑调用或总 token 预算。
4. **探索收益门**：安全门通过后，候选至少减少 2 个 invalid，或在不减少 correct 的
   前提下减少 2 个 Primary 截断/无候选事件；否则保持 `NO_GO`。
5. **成本门**：候选平均模型调用相对基线增加不超过 `0.5`，P95 单题调用不超过 `2`。
6. **晋升边界**：无论结果如何，不修改 `SUBMISSION_CONFIG`、正式 selector、GitCode
   main 或官方作品；最多允许进入新的独立复验。

## 运行命令

```powershell
python scripts/run_robustness_matrix.py `
  --rounds T01,T02,T03,T04,T05,T06,T07,T08,T09,T10 `
  --output-dir artifacts/arm-v223-primary-tail-20261005 `
  --matrix-id ARM-V2.3-PRIMARY-TAIL-CONTINUATION-20261005
```

共享模型端点实验必须串行；每轮结束后先保存 report、aggregate 和 manifest，再进行任何
复核。原始 answers、trace 和 response metadata 留在被忽略的 `artifacts/`，提交只收录
压缩后的 result、comparison 和处置记录。
