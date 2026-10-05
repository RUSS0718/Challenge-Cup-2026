# ARM-V2.3-PRIMARY-TAIL-CONTINUATION-20261005 — result

状态：`EXPLORATORY_NO_GO / NO_PROMOTION / NO_CAPABILITY_CONCLUSION`

## 聚合结果

T01–T10 完成了预注册的 10 轮、25 条 paired records、50 条 arm records。候选和基线均为
0 model error，均值和 P95 模型调用数都是 2.00 / 2。

| 臂 | correct | incorrect | invalid | 模型调用 | 平均调用 | 截断事件 | continuation 激活 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选 `arm-v2.3-primary-tail` | 4 | 15 | 6 | 50 | 2.00 | 1 | 0 |
| 基线 `cfr-primary-tail-pressure` | 3 | 16 | 6 | 50 | 2.00 | 0 | 0 |

候选没有任何记录满足“Primary 无候选且有部分输出”的触发条件，因此本窗口没有实际测量
continuation 对答案形成的影响。候选的 +1 correct 来自普通 CFR 路径，不能归因给 v2.3。

## 逐题转移

下表按“候选 → 基线”记录：

| 候选 \ 基线 | correct | incorrect | invalid |
| --- | ---: | ---: | ---: |
| correct | 3 | 1 | 0 |
| incorrect | 0 | 15 | 0 |
| invalid | 0 | 0 | 6 |

没有 `候选 incorrect → 基线 correct` 的安全回退；唯一变化是候选在一题上比基线正确，
但这题没有 continuation 激活。invalid 没有下降，截断反而比基线多 1 次。

## 门判定

- **VOID 门：通过。** SymPy 可用；10 个 manifest 完成；候选/基线每组题目、顺序和数据哈希
  相同；gold 没有传入模型。运行 manifest 标记工作树 dirty，故该窗口不具备干净发布资格，
  但不改写已完成的配对记录。
- **协议门：通过但激活门失败。** 候选代码只在限定分支写入 bounded telemetry，完整
  incumbent 仍走 CFR；本窗口触发数为 `0/25`，所以 intended mechanism 未被观测。
- **安全门：通过。** 没有 model error，也没有候选 incorrect → 基线 correct 的回退。
- **探索收益门：不通过。** invalid 为 `6 vs 6`，候选截断没有减少，且 continuation 未激活。
- **成本门：通过。** 两臂平均调用数相同，增量 `0.00`，每题最多两次逻辑调用。

因此 v2.3 保持 `DEFAULT_OFF`，不修改 `SUBMISSION_CONFIG`、正式 selector、GitCode main 或
官方作品。该窗口只能证明代码和预算路径在真实端点下健康，不能证明同轨迹续写的数学收益。

完整逐轮、逐题和协议审计见 [`comparison.json`](comparison.json)；原始 answers、manifest 和
trace 保留在被忽略的 `artifacts/arm-v223-primary-tail-20261005/`。
