# FSDF-ITER-AB-012 强制 Harness 架构与设计谱系

## 一、Agent 编排 + Harness 架构图

```
                          ┌────────────────────────────────────────────────────┐
                          │              ReasoningAgent.solve()                │
                          │   AgentConfig（实验臂 flags）/ SUBMISSION_CONFIG    │
                          └────────────────────────┬───────────────────────────┘
                                                   │ enable_fsdf_* 全开（前沿）
                          ┌────────────────────────▼───────────────────────────┐
                          │        ForkSelectDeepenFinishRelay.solve()          │
                          │        五次逻辑调用上限 · 软/硬截止 900/1080s        │
                          │        client 级思考开关 = False（ARM_THINKING_MODE）│
                          └───┬──────────┬──────────┬──────────┬───────────┬───┘
                             │L0        │A         │B/C       │D          │E
                             ▼          ▼          ▼          ▼           ▼
        ┌──────────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐
        │ L0 算式识别器 │ │A analyze│ │B/C fork │ │D deepen │ │  E finish    │
        │（正则，0调用）│ │5字段分析│ │两路方案 │ │【HARNESS│ │ 终答确认+P2a │
        └──────────────┘ └─────────┘ └─────────┘ │  核心区】│ │ +核查附录    │
                             │          │         │ └────┬────┘ └──────┬───────┘
                             │          │         │      │             │
                             │          │         │      ▼             │
                             │          │         │ ┌─────────────────────────────┐
                             │          │         │ │ 强制 HARNESS（迭代 12 新增） │
                             │          │         │ │                             │
   问题文本+题型 ─────────────┼──────────┼─────────┼─▶ select_skill_route()      │
   （宿主预筛，0 模型调用）   │          │         │ │   ├ 题型亲和 + 关键词打分     │
                             │          │         │ │   └ math_routes.json        │
                             │          │         │ │      （仓库相对路径资源）     │
                             │          │         │ │        │ selected route     │
                             │          │         │ │        ▼                    │
                             │          │         │ │ build_harness_deepen_prompt │
                             │          │         │ │ “路线执行器，不是自由解题者”  │
                             │          │         │ │ 不得跳步/改序/自由发挥        │
                             │          │         │ │ 输出协议：SELECTED_BRANCH /  │
                             │          │         │ │ CANDIDATE_D / OPEN / CHECKS │
                             │          │         │ │ / RISK / DERIVED(第N步:×N)  │
                             │          │         │ └──────────────┬──────────────┘
                             │          │         │                ▼
                             │          │         │ ┌─────────────────────────────┐
                             │          │         │ │ 程序侧验证（不信任模型自述）  │
                             │          │         │ │ count_route_steps()         │
                             │          │         │ │ harness_steps_completed     │
                             │          │         │ │ harness_steps_expected      │
                             │          │         │ │ harness_route_id → trace    │
                             │          │         │ └──────────────┬──────────────┘
                             │          │         │                ▼
                             │          │         │ ┌─────────────────────────────┐
                             │          │         │ │ P1 多行交接装配（4600 上限） │
                             │          │         │ │ 字段五状态 / 冲突标记        │
                             │          │         │ │ 未闭合尾部丢弃 / 整条目裁剪  │
                             │          │         │ └──────────────┬──────────────┘
                             ▼          ▼         ▼                ▼
                             └──────────┴─────────┴───────┬────────────────┘
                                                          ▼
                          ┌───────────────────────────────────────────────────┐
                          │                    E finish                       │
                          │  handoff（含 第N步 记录 + build_harness_finish_    │
                          │  addendum 路线核查要求）+ P2a 确认链               │
                          │  （FINAL→FINAL_D→deep_candidate*→UNKNOWN，*关）    │
                          └────────────────────────┬──────────────────────────┘
                                                   ▼
                                    final_response / trace（含全部遥测）
```
（\* deep_candidate_fallback 为迭代 9 候选，默认关，不在前沿。）

## 二、设计谱系（除 harness 外的每个部件来自哪里）

| 部件 | 来源 | 在本迭代是否改动 |
| --- | --- | --- |
| 五调用中继骨架、L0、A/B/C 提示、截止门、降级边界 | FSDF v1（官方 14/112 版本，commit `de74934` 时代定型） | 未改动 |
| P0 诊断（字段五状态、handoff 遥测、unavailable 标记） | Issue #15 迭代 0（`fsdf_diagnostics_v2`） | 未改动 |
| P1 多行交接（字段边界解析、冲突标记、整条目裁剪、未闭合尾部丢弃） | Issue #15 P1（`fsdf_multiline_handoff_v2`） | 未改动 |
| P2a 终答确认（显式 UNKNOWN 不回退、冲突 fail-closed） | Issue #15 P2a（`fsdf_final_confirmation_v2`） | 未改动 |
| P2b E 收尾提示（FINISH_PROMPT_V2） | Issue #15 P2b（`fsdf_finish_prompt_v2`） | 未改动 |
| D 交接产物优先提示（DEEPEN_PROMPT_V2） | 迭代 11 前的快速诊断窗（`fsdf_handoff_first_d`，e7a35e4） | 被 harness 提示**替换**（仅当 harness 开） |
| D 4096 / E 8192 预算对调 | 迭代 1（`fsdf_de_budget_swap`，唯一分数前移杠杆之一） | 未改动 |
| 删选中思路块、交接装配 4600 | 迭代 4（`fsdf_finish_handoff_share`，最大净增 +3） | 未改动 |
| 思考关闭（client 级开关） | 迭代 10 探针 + 用户指示（`fsdf_thinking_off_v1` 机制已证） | 未改动（经 ARM_THINKING_MODE） |
| **路线选择（宿主预筛）** | **迭代 11（`fsdf_skill_routes_v1`）** | 复用其选择函数，改用其正文 |
| **强制 harness（本轮唯一新增）** | 迭代 12（`fsdf_skill_harness_v1`）：D 系统提示=路线执行脚本、第N步 强制输出、程序侧完成度遥测、E 核查附录 | 新增 |

即：**harness 之外的一切都与前沿 `v2hd_bs_hs`（思考关）逐字节相同**；唯一变量是 D 的
系统提示与两处程序侧验证/遥测。

## 三、为什么强制 harness 在思考关之后才可行

迭代 3 的教训：思考默认模式下 D 4096 预算被思考消耗，加一个强制字段就 15/15 截断。
思考关闭后（探针：同题完整输出仅 178 tokens，8.7%），4096 预算几乎全部可用于内容——
"强制多字段输出"与"预算约束"的矛盾不复存在。这是本候选放在思考关之后的原因。
