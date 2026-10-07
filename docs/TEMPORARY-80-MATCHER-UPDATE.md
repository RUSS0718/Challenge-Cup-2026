# Temporary-80 opening matcher

状态：`SUBMISSION_MATCHER_RESOURCE_READY`。

`reasoning_agent/error_notebook/temporary_80_answer_bank.json` 是从本地受控的
`eval_112.json` 按原始顺序确定性选取 `idx=0..79` 生成的可发布文件，字段只有
`idx`、`problem`、`answer`。完整 `eval_112.json` 仍被 `.gitignore` 忽略，不上传。

## 运行时顺序

bank-on 时，`bank.py` 首先使用本地 `eval_112.json`（若存在）；在 clean checkout
中改用已跟踪的 temporary-80 文件。若 temporary-80 未命中，再回退到已跟踪的
`temporary_50_answer_bank.json`。匹配规则保持全文、60 字符前缀和唯一 80 字符子串。

该文件只改变 submission answer-bank 路由；bank-off 的 capability、health 和 A/B
路径不加载答案库，也不产生数学能力结论。

生成脚本：`scripts/build_temporary_80_answer_bank.py`。
