# FSDF-ITER-AB-004 配对回归窗口结果（迭代第 4 轮）

方法：同题配对双臂，唯一变量 = `fsdf_finish_handoff_share_v1`（E 输入构成重分配：
删除"选中思路"块、handoff 装配上限 3000→4600，总上限 6500 不变）。基线 `v2hd_bs`
（前沿）vs 候选 `v2hd_bs_hs`。15 题配对，workers=3，hard-stop 75 min。
git_head `92b875a`。30/30 run 完成，0 崩溃 0 顶层错误。

结论：`DIAGNOSTIC_ONLY / NO_CAPABILITY_CONCLUSION / 前沿前移（net +3 零反转）`

## 配对结果（native 判定，15 对）

| 臂 | correct | incorrect | invalid/UNKNOWN | E 终答形成 | E 截断(length) | mean/P95 dur |
| --- | - | - | - | - | - | - |
| v2hd_bs（前沿） | 1 | 2 | 12 | 3/15 | 11/15 | 405.4s / 464.2s |
| v2hd_bs_hs（交接份额） | **4** | 2 | 9 | **6/15** | **9/15** | 389.9s / 459.8s |

- 配对矩阵：**incorrect→correct 1**（OlymMATH-HARD-61-EN）、**invalid→correct 2**
  （OlymMATH-HARD-75-ZH、aime-8）、correct→correct 1、incorrect→incorrect 1、
  invalid→incorrect 1、invalid→invalid 9。
- **correct 净增 +3、零 correct→incorrect 反转**——四轮以来最强单窗结果。
- E 终答形成 3→6；E 截断 11→9（各配置中首次降到 10 以下）。
- 成本：mean 390s vs 405s（候选略短），总 token 与调用上限未放宽。

## 门的判定

- M2 行为门：E 终答形成 ≥6/15 ✓；E 截断 ≤8/15 ✗（9，接近未达）；形成转化 ≥3 ✓
  （2 个 invalid→correct + 1 个 incorrect→correct 的形成来源）。
- M1 装配激活：trace 无直接字符量，代理指标（missing 实例 28 vs 31、clipped 0/0）
  不敏感；装配变化为构造性事实（零模型测试已证），按"构造性激活"记录。
- 前沿前移依据注册规则第一条：**net ≥ +2 且零反转** ✓（+3）。方差警示仍然有效
  （同配置跨窗 ±1-2），+3 高于该噪声带，但确认性复现仍留待后续窗口。

## 供下一轮迭代的事实

1. 删除"选中思路"块后 E 终答形成 3→6：B/C 的 PLAN 叙述确实是 E 重推导的诱因。
2. E 截断 9/15 为历史最低但仍未达 ≤8；E 自延展惯性存在。
3. D 侧字段冲突 22（vs 12）仍为 run 方差；D=4096 的截断压力持续。
4. 累计前沿（v2hd → v2hd_bs → v2hd_bs_hs）每步都有结构性单变量支撑。

## 边界

诊断窗口（n=15 配对）；无能力结论；本次前沿前移仅指迭代循环内基线选择，
**不修改 `SUBMISSION_CONFIG`、不推送 gitcode main**（canary 维持 507ebd3）。
本地 native/contract 为本地近似判定，非官方 judger。
