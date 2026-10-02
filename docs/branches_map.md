# 分支与发布面地图（2026-09-21 梳理）

> 目的：记录当前 GitCode 发布面、本地工作分支和历史档案分支。GitHub `origin`
> 与 GitCode 分开维护；未明确授权时不互相删除或同步。

架构版本谱系见 [`architecture_evolution.md`](architecture_evolution.md)；本表只负责
ref/worktree 发布拓扑，不重复记录每个实验架构的细节。

## 发布与镜像

| ref | tip | 角色 |
| --- | --- | --- |
| **gitcode/main** | `ca15d39` | **AtomGit/赛事发布面** |
| **gitcode/codex/harness** | `1bc41ac` | Harness 分支拓扑文档线，非当前 checkout |
| **local codex/harness** | `1bc41ac` | 保留的 Harness 文档分支，非当前 checkout |
| **local main** | `7779ab7` | 本地 main，保留但未与 GitCode main 对齐 |
| **origin/main**（GitHub） | `fc1b671` | GitHub 发布面，未在本轮修改 |

## 当前工作分支

| 分支 | tip | 内容 |
| --- | --- | --- |
| **codex/repo-hygiene-cleanup** | `fca3d2b` | 当前唯一活动 worktree；profile 开关与 worktree 收敛整理 |

## GitCode 历史档案分支

旧 GitCode 分支名已删除，历史由以下 `archive/...` ref 保留：

| 档案分支 | tip |
| --- | --- |
| `archive/codex/btcs-v1` | `30f3aeb` |
| `archive/codex/btcs-v2-main-integration` | `55f80e5` |
| `archive/codex/deterministic-solver-v1` | `16894d1` |
| `archive/codex/fsdf-iterative-ab-001` | `e6ea4e8` |
| `archive/codex/fsdf-v1-code-acceptance-001` | `507ebd3` |
| `archive/codex/official-output-hygiene-canary` | `1c9908b` |
| `archive/codex/salvage-v1` | `f706116` |
| `archive/codex/stateful-tail-v1` | `ca536ce` |

## 本地历史档案分支

本地旧分支均已移动到 `archive/...`；本地 tip 与 GitCode archive tip 可能不同，分别保留
各自原有历史：

`archive/PRE0-8.30`、`archive/codex/agent-systems-experiments-20260901`、
`archive/codex/b1-4k-canary`、`archive/codex/btcs-v1`、
`archive/codex/btcs-v2-main-integration`、`archive/codex/c0-evidence-release-20260827`、
`archive/codex/cod-numeric-candidate-20260827`、`archive/codex/deterministic-solver-v1`、
`archive/codex/engineering-v1`、`archive/codex/external70-active`、
`archive/codex/fsdf-iterative-ab-001`、`archive/codex/fsdf-paired-ab-loop-001`、
`archive/codex/fsdf-v1-code-acceptance-001`、`archive/codex/main-integration-20260829`、
`archive/codex/pot-tir-executor`、`archive/codex/resilience-quality-temperature-ab`、
`archive/codex/salvage-v1`、`archive/codex/stable-baseline-8k-k2`、
`archive/codex/stateful-tail-v1`、`archive/codex/verification-gated-retry`、
`archive/codex/weakness-fix-package-14`、`archive/gsa-canary-20260830`、
`archive/p0-rollback-46c08dd`、`archive/p0-rollback-55f80e5`。

## 发布后例行动作（每次 canary 发布/回滚后）

1. 先在 `codex/repo-hygiene-cleanup` 或新的实验分支完成 scoped commit；
2. 发布到 GitCode 时显式指定目标 ref，不默认同步 `origin`；
3. 本表只记录已核验的 commit tip、archive ref 和 worktree 状态。

## 工作区卫生约定

- `tmp/` 保持 untracked:原始工件先判定、后拷贝归档至 `docs/experiments/`,
  判定未归档的窗不得清理;
- 当前仅保留仓库根目录一个活动 worktree；历史分支和实验工件不参与发布。
- 2026-09-21 已移除 7 个辅助 worktree；tracked 改动保存到 Git stash，
  COT/PoT 未跟踪归档移动至 `tmp/archived_worktree_cot-pot-9.16-20260921/`。
- 原集成目录中的未跟踪缓存已可恢复地归档到 `tmp/archived_worktree_main-integration-20260829/`；
  本地 archive 分支与实验产物均保留。
- 根目录过时的 `P0-提交总结.md` 已归档至 `docs/archive/legacy/`；历史实验报告不删除，
  仅由 `docs/ARCHIVE_INDEX.md` 分类索引。
