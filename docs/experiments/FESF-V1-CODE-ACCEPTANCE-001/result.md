# FESF v1 code acceptance

状态：`PASS_LUNA_MAX_REVIEW / ZERO_MODEL / MODEL_EXPERIMENT_DEFERRED / NO_RELEASE`

已验收内容：

- 正式 `SUBMISSION_CONFIG` 回到 FSDF v1：六个 FSDF canary 与 FESF 均关闭，FSDF 主路径保留；
- FESF 固定 A→B→C→D→E 五调用协议，L0 保持单次 4096；B/C 物理串行；
- A 只接收 Skill 元数据，宿主只向 C 注入被选中的一份正文；非法或不适用选择回落 `NONE`；
- `exact-evaluation` 独立目录、frontmatter、正/负 cases 和受限 `EXACT_EVAL` DSL；
- D 只按 claim/evidence ID 合成主线、辅助、反证、未决；无证据的 `REFUTED` 降级为 `UNRESOLVED`；
- 每次 `solve` 新建 `SolveMemory`，不写盘、不跨题；E 只看到有界结构化状态；
- runner 显式提供 `fsdf_v1_tkoff` / `fesf_v1_tkoff_exact_eval`，并钉死候选开关与 thinking off；
- trace 不保存完整 prompt/response，返回值可 JSON 序列化。

独立 Luna 复核首轮发现并已修复的协议问题：A 的非适用路由现在规范化为 `NONE` 且不
触发工具；D 支持/反驳必须绑定同一 `claim_id` 的确定性 evidence；支持、辅助、反驳、未决
类别互斥，非法 evidence 不进入记忆或 E；D 缺失、重复、非法字段或任意损坏均 fail-closed；
FESF relay 在软截止后停止后续模型调用。随后 Luna max 复核又发现并推动修复了：证据
必须是 standalone canonical equation、未定义/缺失定义域/负幂与累计幂膨胀必须拒绝、
重复/撤回/占位/截断 FINAL 必须拒绝。最终 Luna max 只读复核为 PASS。focused suite 为
187 tests OK，全量测试为 648 tests OK（4 skipped）。

本工件只记录工程验收，不代表 Skill 可用性资格门或困难题正确率通过；真实模型 Q/W1/W2
按用户指示暂缓，默认路径未切换，未推送发布。
