# 分支与发布面地图(2026-08-29 梳理)

> 目的:终结"两个 main"时代的拓扑混乱。此后引用任何分支,以本文件为准。

## 发布与镜像

| ref | tip | 角色 |
| --- | --- | --- |
| **gitcode/main** | `c9d0597` | **唯一官方评测拉取面**(行为 = hetero 单变量,即 Run #5 的 12/112 配置) |
| **origin/main**(GitHub) | `c9d0597` | gitcode 的备份镜像,已同步 |
| **local main** | `b8b78aa` | 已 fast-forward 到 GitHub 状态(旧滞留 e4b40c0 陷阱解除);仍落后 gitcode 4 个发布提交,**不得直接推 gitcode** |

## 工作分支

| 分支 | tip | 内容 |
| --- | --- | --- |
| **codex/b1-4k-canary** | `5881b17` | **现役工作分支**(已推 GitHub 备份):全部变体族(exact_g/salvage/hetero_refine/re2_k5/cod_hetero/baseline_hetero)、ADR、CONTEXT、判定报告、排除表、研究文档、AGENTS 章节收编。后续实验与发布包从这里出发 |
| codex/c0-evidence-release-20260827 | `c9d0597` | 发布线(本地克隆在 %TEMP%),gitcode main 的孪生;发布/revert 都在此操作 |
| codex/cod-numeric-candidate-20260827 | `25f99b5`+未提交 CoD | CoD 原始实现存档(实现已移植主线);CoD 线 ARCHIVED |

## 历史档案分支(全部保留,勿删)

- `codex/stable-baseline-8k-k2` @ b8b78aa(.worktrees 检出):官方 8k 时代+排除表定稿
- `codex/weakness-fix-package-14` @ b684729(.worktrees 检出):**refine 战役原始工件所在地**(ADR-0002 引用)
- `codex/deterministic-solver-v1` / `codex/pot-tir-executor` / `codex/resilience-quality-temperature-ab` / `codex/salvage-v1` / `codex/verification-gated-retry`:历史实验存档线

## 工作区卫生约定

- `tmp/` 保持 untracked:原始工件先判定、后拷贝归档至 `docs/experiments/`,
  判定未归档的窗不得清理;
- `.worktrees/` 两个检出是证据家,不 prune;
- %TEMP% 下两个克隆:发布线保留(发布操作面),CoD 克隆可随时重建(实现已入主线),
  系统清理时注意保留前者。
