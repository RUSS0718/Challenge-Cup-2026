# 分支与发布面地图(2026-08-29 梳理)

> 目的:终结"两个 main"时代的拓扑混乱。此后引用任何分支,以本文件为准。

## 发布与镜像

| ref | tip | 角色 |
| --- | --- | --- |
| **gitcode/main** | `46c08dd` | **唯一官方评测拉取面**；runtime父提交 `9311d8c` = hetero+refine+ARH canary |
| **origin/main**(GitHub) | `46c08dd` | gitcode 的备份镜像,已同步 |
| **local main** | `46c08dd` | 当前部署镜像；本地集成完成前不移动 |

## 工作分支

| 分支 | tip | 内容 |
| --- | --- | --- |
| **codex/b1-4k-canary** | `b2f01ec` | 已推 GitHub 的实验/证据分支；包含 GSA/ARH 工件与最新研究文档 |
| **codex/main-integration-20260829** | 本地集成中 | 从 `46c08dd` 出发收编工作分支；测试通过前不是发布面 |
| codex/c0-evidence-release-20260827 | `0409103` | 历史发布工作树注册；当前本地路径已失效,不得作为发布面 |
| codex/cod-numeric-candidate-20260827 | `25f99b5`+未提交 CoD | CoD 原始实现存档(实现已移植主线);CoD 线 ARCHIVED |

## 历史档案分支(全部保留,勿删)

- `codex/stable-baseline-8k-k2` @ b8b78aa(.worktrees 检出):官方 8k 时代+排除表定稿
- `codex/weakness-fix-package-14` @ b684729(.worktrees 检出):**refine 战役原始工件所在地**(ADR-0002 引用)
- `codex/deterministic-solver-v1` / `codex/pot-tir-executor` / `codex/resilience-quality-temperature-ab` / `codex/salvage-v1` / `codex/verification-gated-retry`:历史实验存档线

## 发布后例行动作(每次 canary 发布/回滚后)

1. local main ff:;
2. GitHub 镜像同步:发布线克隆内 `git push origin gitcode/main:refs/heads/main`;
3. 本表三行 tip 更新,随工作分支提交。

## 工作区卫生约定

- `tmp/` 保持 untracked:原始工件先判定、后拷贝归档至 `docs/experiments/`,
  判定未归档的窗不得清理;
- `.worktrees/` 的两个历史检出是证据家；`main-integration-20260829` 是当前集成工作树；
- %TEMP% 下两个旧 worktree 注册已显示 prunable，但清理属于独立 Git 元数据操作，
  不混入本次目录整理。
