# R 战役恢复:refine 证据重新锚定为可复核工件

Status: accepted (2026-08-27)

refine 三轮战役(R1–R3)的原始工件在
`.worktrees/weakness-fix-package-14/docs/challenger_refine_2026-08-26.json`
与同名 `_answers.jsonl` 中找到(该 worktree 即产生这批数据的分支)。
逐题重建结果:题集为 `sample_data/complex_capability_freeze_48.jsonl`,
双臂 `legacy_4k_k5` vs `legacy_4k_k5_refine`,3 轮;按
(variant, round, idx) 取最后一次运行去重后共 144 对,分歧对
b=12(refine 胜)/ c=4(基线胜),双侧精确符号检验 p=0.0768,
与历史转述完全一致。

两点口径修正:

1. **分母是 144 对,不是转述的"/288"**。R1/R2 每臂每轮各有 96 行答案,
   是重跑追加而非 96 道独立题;"净增 +8/288" 的写法源自把行数当题数。
2. 战役数据不在正式目录而在实验 worktree 的 docs/ 下;`tmp/overnight_2026-08-26/`
   里的 `skipped_exact_refine_extension.json`(记录"找不到每轮 96 题源")是
   按错误题数(96/轮)搜索所致,结论已被本次恢复推翻。

后续约束:R 累计叙事恢复使用,但任何续窗必须复用同一冻结集(complex48)、
同臂定义与配对口径,并在 manifest 记录 commit hash(协议快照);
不得回接旧编号 R4/R5 造成的歧义,续窗以 refine_fresh 或明确战役批次命名。

## Consequences

- `explore_medium12_r1.json`(当晚另一窗口,current_refine 8/12 vs current 9/12)
  与本战役并存的矛盾仍然存在:两窗口不同题集、不同轮,不合并解读;
  fresh replication 设计需把它纳入对照讨论。
- 官方评测锚点注记:提交仓库 main = b8b78aa(C0:answer_first+k5),
  本地 main = e4b40c0(canary gated profile),两者已分叉;
  引用"main 分数"时必须注明指哪个 main。
