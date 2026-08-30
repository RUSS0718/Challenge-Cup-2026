# P1 预注册：外部能力层基线锚（hetero_k5）

- 窗口族 ID：`P1-BASELINE`
- 类型：基线锚建立（无候选、无对照臂；正确率只作锚定不作晋升）
- 预注册冻结时间：2026-08-30 深夜（静态层构建后、模型窗启动前）
- 授权链：GO_P1=YES after rollback verification（用户 2026-08-30 决策 3）；
  回滚已于同日执行并验证（gitcode main `019cc40`，blob=`e804506…`=25f99b5 字节）。
- 数据策略：P1_DATA=LOCAL_CACHE_ONLY（用户决策 2）——原题/gold 只存
  `tmp/p1_data/`，仓库存 manifest/ID/hash/静态门结果。

## 1. 运行对象与配置

- 唯一运行 profile：`hetero_k5`（`operational_baseline_hetero_k5_25f99b5.json`）；
  经 runner 臂 `baseline_hetero` 逐字段复刻，在 PRE0-8.30 线上执行
  （PARITY 对 46c08dd 单体重签背书；refine/ARH 关闭路径与官方回滚字节行为一致）。
- 资源：workers=3；timeout=180s；`INTERN_REQUEST_DEADLINE_SECONDS=240`；
  temperature=0.6；retry=1；熔断 8；共享端点串行。

## 2. 运行矩阵（spec §8）

| 层 | 文件 | 轮数 | solves 预算 |
| --- | --- | --- | --- |
| core120_v2（MATH-500 50 + OlymMATH 40 + AIME24 30） | `tmp/p1_data/run/core120_v2.jsonl` | **2** | 240 |
| confirm30_v2（AIME25 全 30） | `tmp/p1_data/run/confirm30_v2_aim2025.jsonl` | **1** | 30 |
| robust180_v2 结构烟测（2 seeds × 9） | `tmp/p1_data/run/robust_smoke_2seeds.jsonl` | **1** | 18 |
| fresh63_v1 | **SEALED**（不构建、不下载） | — | — |

每 solve ≤5 调用；理论调用上限 288×5=1440。

## 3. 判分与门

- 双口径（§4.3）：contract（`final_response` 外部抽取 + 保守 judge）与 native
  （MATH/OlymMATH=math-verify 0.8.0；AIME=整数 exact；GSM=数值 exact）；
  invalid/error/timeout 全计入固定分母；差集落盘。
- P1 目标（§8）：静态门全过、baseline 工件完整、双轮 item-cluster 统计可复现、
  预计官方成本 ≤5.5h 锚定。**不据逐题错误改 Prompt**。
- 健康门：任一层 model error >10% → 该层 VOID，允许一次复跑；再次失败即
  `ARCHIVED_VOID` 并上报。
- P2 启动条件（用户决策 4）：P1 全门通过后 CONDITIONAL_YES；GSA 三臂
  fidelity probe 先行（§9.2），官方 canary 不在本次授权内（决策 5）。

## 4. 产物

`runs/`（逐层 report+answers+log）、`p1_run_manifest.json`（§4.1 全字段）、
`p1_baseline_result.md`（双口径锚定、方差、成本锚、差集）、静态层 manifest 五份
（已提交 `4fbf9e4`）。
