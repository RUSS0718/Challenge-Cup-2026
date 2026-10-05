# ARM-V2.4-RISK-GATED-ANSWER-RESERVATION-20261005 — preregistration

状态：`OPEN / DEFAULT_OFF`

## 目的与假设

官方 2026-10-04 报告记录了 73/100 个 `invalid` 和 70/200 次
`finish_reason=length`。v2.2 的全量 answer-first 窗口虽然减少截断，却损失了正确答案；
v2.3 的同轨迹续写窗口没有触发。因此本实验只在宿主路由已经判定为
`structured`/`deep` 或路由置信度不是 `high` 时启用答案保留位。`direct` 且高置信题继续
使用 v2.1.4 的首轮提示和 CFR 第二轮。假设是：把长度风险限制在高风险路由，可以减少截断或
无效输出，同时避免 v2.2 对简单题的质量损失。

## 唯一变量与对照

- 候选：`arm-v2.4-risk-gated`，`arm_harness_version=v2.4`。
- 对照：`cfr-v2.4-risk-pressure`，使用 `arm-v2.1.4-cfr`。
- 两臂首轮均为 2,048 tokens，第二轮均为 4,096 tokens，总预算均为 16,384 tokens；
  两臂均 bank-off、RAG-off、Skill-off，第二轮仍为 CFR Challenger。
- 唯一变量是候选的 route-gated first-call prompt；不修改 parser、judge、正式 selector、
  `SUBMISSION_CONFIG` 或提交作品。

## 数据与配对

U01–U02 使用 OlymMATH 42–46，U03–U04 使用 OlymMATH 50–54，U05–U06 使用新的
AIME `aime-5`–`aime-9`，U07–U08 和 U09–U10 使用两组此前未用的 HLE Math 记录。
共 10 轮、25 条 paired records、50 条 arm records；题目与 X/Y/Z/Q/T 窗口不重叠。
模型请求不得包含 gold，题集 SHA 和配置写入每个 run manifest。

## 预注册门

1. **VOID 门**：任一题目配对、题集哈希、manifest、SymPy 预检或 model error 记录缺失，
   整窗作废。
2. **激活门**：候选至少有 5 条 `risk_gated_answer_commit=activated` 记录；否则只作
   工程探针，不能对该机制作能力结论。
3. **安全门**：不得出现候选 `correct → incorrect`，不得增加 model error；两臂调用与
   token 上限必须相同。
4. **探索收益门**：安全门通过后，候选 correct 不低于对照，且至少减少 2 个 invalid，
   或至少减少 2 个截断事件。
5. **成本门**：候选平均调用增量不超过 0.5，P95 单题调用不超过 2。
6. **晋升边界**：无论结果如何保持 `DEFAULT_OFF`，需要独立新窗口和正式门才可讨论晋升。

## 运行命令

```powershell
.venv\Scripts\python.exe scripts\run_arm_v224_experiment.py `
  --output-dir artifacts/arm-v224-risk-gated-20261005 `
  --workers 1 `
  --timeout 120
```

原始 answers、trace、manifest 和报告留在被忽略的 `artifacts/`；提交树只保留本预注册、
压缩后的比较结果和处置记录。
