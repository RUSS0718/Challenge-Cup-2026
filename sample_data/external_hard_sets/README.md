# External Hard Sets（外部难题池，冻结于 2026-09-05）

三套按"官方难题"难度对齐的外部题池，用于提交前回归 smoke 与方法对比。
选题、判分与运行协议见 `MANIFEST.json` 与
`docs/experiments/EXTERNAL-HARD-SETS-SMOKE-001/`。

## 为什么是这三个题源（体系）

与仓库既有口径一致（V4-HARD20 预注册：OlymMATH hard + AIME 为"最接近官方
隐藏评测的难题小窗"），三个池对应三个互补的命题体系：

| 池 | 体系 | 规模 | 语言 | 判分 |
|---|---|---|---|---|
| `set_a_olymmath_hard.jsonl` | 多国奥赛难题（OlymMATH HARD 档） | 88 题 × 中英双语 = 176 行 | ZH+EN（同题双语成对，`problem_group_id` 关联） | Math-Verify / 等价 |
| `set_b_aime.jsonl` | 美国邀请赛（AIME 2024 未用 22 + 2025 全 30） | 52 题 | EN | 整数 exact |
| `set_c_hle_math.jsonl` | 科研前沿（HLE Math 文本题） | 80 题（每领域 20±1） | EN | Math-Verify / 归一化字符串 / 等价 |

四领域均为 Algebra / Combinatorics / Geometry / Number Theory（官方
official_like_hard20_v1 的领域口径）。HLE 中研究级主题（分析/PDE/集合论/
范畴论等）不属于四领域，已剔除；领域标签由关键词规则 + 逐题人工复核给出，
标注过程在模型调用之前完成（盲评）。

## 排除与隔离

- OlymMATH 12 题、AIME 2024 8 题已被 `V4-HARD20-DUAL-001` 使用，全部排除，
  池与该窗口的题零重叠（见 MANIFEST `excluded_items`）。
- HLE 逐题人工复核剔除约 60 题：不可判答案形式（散文/多段/百分比/集合符号/
  函数定义式）、图片依赖题、PDE/分析/集合论/范畴论主题、可疑 gold。
- 题面与答案均为公开数据集内容；`answer` 仅本地评测使用，不进入 `solve()`。

## 使用方式（每轮抽样 50）

```bash
# 三套各分层随机抽 50（seed 记录在 run manifest，可复现）
python scripts/run_external_hard_sets_smoke.py --workers 3 --seed <SEED>
```

- 抽样规则：每套 50 题，按 4 领域分层，每格保底 ≥2，其余按领域规模分配；
  set_a 按题组抽样、每组只取一种语言，整体 ZH/EN≈1:1。
- 同一 seed 两臂可比（配对）；换 seed 则是新一轮，结果不可逐题配对。
- 判分沿用 V4 协议的官方口径：native（Math-Verify / 整数 exact）+
  contract（final_response 严格抽取）双轨，另计 format / serializable /
  trace 卫生检查。
- 成本参考：FSDF（5 调用）实测约 5-8 分钟/题，3 并发 150 题约 4-6 小时。

## 复现

`scripts/build_external_hard_pools.py` 以固定 seed 从原始来源重建池（来源
URL 与 SHA-256 见 MANIFEST）。原始文件不入库；重建需网络。
