# re2_k5 canary 回滚记录(2026-08-29)

状态:`ROLLED_BACK`(gitcode main = `6037c73`,revert `d9203f0`)。

## 裁决依据(官方 Run #6,发布时预写的三条件全部触发)

| 指标 | Run #5(`25f99b5`) | Run #6(`7479d47`) | 条件 |
| --- | --- | --- | --- |
| correct | 12 | 11 | ✅ 回退 |
| 耗时 | 4h24m | **7h24m(超 6h 红线)** | ✅ 恶化 |
| runner error | 0 | **10** | ✅ 上升 |
| invalid | 17 | 27 | (+10 ≙ 10 个 error 题的 fallback) |
| prompt_tokens | 167,724 | 237,238(+41%) | 机制根因 |

## 机制

题干重述 → user prompt 输入翻倍(+41% prompt tokens)→ 单题墙钟膨胀
(4h24m→7h24m)→ 10 题在官方 runner 超时/报错 → fallback 答案涌入
invalid(+10)→ correct −1。本地两窗(08-28/29)已预警:Re2 臂延迟
+34%/+9%、model_error 率 14.6~20.8% 连续越 void 门——本地筛窗纪律
成功预测了官方恶化。

## 遗产

- `enable_re2_reread` 开关与测试保留在仓库(默认关),不删代码;
- 回滚后 413/413 测试通过,行为等价 `25f99b5`(官方 Run #5 = 12/112);
- 发 3 候选:refine(战斗之夜 W2 干净确认,配对净 +1、成本 1.26×、
  三门全过),叠加 hetero 基线,待用户签发。
