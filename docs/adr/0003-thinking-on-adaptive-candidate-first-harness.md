# Thinking-on 下采用自适应候选优先 harness

Status: accepted (planning only; not deployed)

官方 client 无法由 `ReasoningAgent` 可靠关闭 thinking，而固定 A→B→C→D→E 协议在
thinking-on 下会把阶段截断、协议失败和 fail-closed 级联成 invalid。因此后续候选
架构采用 `CAR-001`（candidate-first adaptive relay）：先做一次短候选调用；只有
候选缺失、冲突、多候选标记或解析失败时才追加第二候选；仍无法选择时最多做一次
短裁决/恢复，单题最多三次调用。候选以 `CANDIDATE:` 和不超过三行理由形成边界，
不要求完整证明；截断若已包含唯一候选，宿主保留候选并最多做一次短恢复。

候选冲突保留双方，先做有限的规范化、精确等价和安全数值检查，无法判定再交给
短裁决器；不按 B/C 顺序静默丢弃一方。单题 memory 仅是短结构化账本，正式评测题间
丢弃。skill 首版以软建议路线和适用边界进入提示，verifier 只做 shadow 诊断；只有
独立 A/B 显示正确率收益且错误反转受控，才另立硬 skill 或 verifier 选择器实验。

选择该形态是因为历史证据不支持“截断率下降就会正确率上升”：提高预算和多次投票
没有稳定提升，thinking-off 虽几乎消除截断却增加 incorrect，FESF 严格协议又造成
大量 invalid。RPM/TPM 提升只用于 runner 层三 workers 的交错实验和早停吞吐，不改变
单题 20 分钟、整轮 6 小时、单题调用/token 上限。正式评测可以读取评测前冻结的
抽象错题本，但运行期间不得写回或让前题影响后题。

## Considered Options

- 继续固定五阶段并增加预算/截断续写：被否决——历史上预算增长和 handoff 变体未
  稳定提升 correct，且每个必经协议都会扩大 thinking-on 的截断面。
- 每题固定并行多路完整解题：暂不采用——会把新增 RPM/TPM 变成固定成本，且公开
  client 没有线程安全保证；作为后续独立 `parallel-candidate` 实验。
- 强制 skill 逐步执行：暂不采用——上一轮强制路线合规率提高但 correct 下降；先
  用软建议测能力，再用独立门决定是否值得硬执行。

## Consequences

- 大多数题可在一次调用后早停，平均调用和墙钟时间有望下降；难题仍可获得最多两
  次追加机会。
- 候选形成不再等同完整证明。trace 必须区分 `candidate_unproven`、`adjudicated`
  和 `verified`，避免把未完成证明伪装成已验证结论。
- “valid/截断下降”只能作为健康和成本指标；能力门仍以 correct、incorrect、
  invalid 和逐题反转共同判定。
- CAR-001 是实验候选，不改变 `SUBMISSION_CONFIG`，不替换当前 FSDF v1 默认路径。
