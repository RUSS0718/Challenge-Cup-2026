# 2026-10-06 架构选择记录

本次提交选择 `arm-v2.1.4-cfr` 作为 GitCode `main` 的正式 selector。

选择依据：

- 当前 `gitcode/main` 已包含 ARM v2.1.4 CFR 的发布协议、运行时哈希和离线校验。
- CFR 保留 `Challenger → Targeted Repair → Fresh Review` 的有限修复链，默认关闭 RAG、答案库和 hybrid router，失败时保留安全候选或返回 `UNKNOWN`。
- 9 月 15 日的 Answer-first 旧分支虽然在本地 112 题观察中达到 `formed=112/112`、`invalid=0`，但统计为 `51 correct / 13 incorrect / 48 unknown`，此前已判定 `NO_GO`；本次不将其覆盖到主线。
- 官方隐藏集尚未对 CFR 返回新成绩，因此本记录不声称数学能力提升，也不修改回滚锚点 `43a02da`。

验证范围：

- `docs/releases/arm-v2.1.4-cfr-20261004/verify.py`
- 发布 manifest 中记录的运行时文件 SHA-256
- 严格三参数 client、selector、配置门和 trace/gold 隔离

后续若官方评测证明 CFR 造成可确认的 `correct→invalid` 损失，按发布协议回滚到 `43a02da`。
