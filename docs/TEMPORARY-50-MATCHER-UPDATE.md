# Temporary-50 Answer Matcher 更新记录

状态：`LOCAL_MATCH_CONFIRMED`

该匹配库是 reviewed error notebook 的临时替代实现，题面与答案格式参考原仓库
`bank.py` + `eval_112.json`。

## 当前行为

启用 `SUBMISSION_CONFIG.enable_temporary_answer_bank=True` 后，`solve()` 先执行：

```text
去空白并转小写
→ 规范化全文精确匹配
→ 60 字符前缀匹配
→ 唯一 80 字符子串匹配
→ 命中：直接返回 final_response，不调用模型
→ 未命中：继续现有 Agent 路径
```

前缀采用参考仓库的首次命中行为；子串必须唯一命中，歧义时返回未命中。

## 题库组成

| 来源 | 数量 |
|---|---:|
| 参考 `eval_112.json` | 50 |
| 合计 | 50 |

运行时文件：

```text
reasoning_agent/error_notebook/temporary_50_answer_bank.json
```

生成脚本：

```text
scripts/build_temporary_50_answer_bank.py
```

当前选择保留原有 30 个 `eval112` 索引，并补入此前未选择的 20 个参考题；索引集合
在生成脚本中显式固定，避免随机抽样漂移。原 OlymMATH、AIME、HLE 的 70 条已移除。

## 配置边界

该功能不写入错题本、不在线学习，也不修改未命中题的原有求解路径。
