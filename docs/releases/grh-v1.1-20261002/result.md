# GRH v1.1 正式发布核验（2026-10-02）

目标：发布到 GitCode main，默认 arm-v2.1.3-off；保持 CURRENT_BRANCH_GRH_221_INTERN_S2_20261002_R1 实验的实际源码与配置。

## 来源与一致性

- GitHub main 核对为 b730409ef6834265ebc0c19b4e1f7fce7d66a28c；实验 HEAD 为 91b66b3167458fd5c117f7068f32227f7a33f7d2。实验标记 working_tree_dirty=true，因此直接复制 GitHub main 不足以复现。
- 从历史备份 89324454be056e5ca0db704f783d6ced899b6075 恢复 harness_contracts.py 的终答连接词解析修改、fork_select_deepen_finish.py、math_routes.json，并保留实验记录的 directed_frontier_transfer.md。
- experiment_manifest.json 保留原实验清单。全部 10 个记录文件逐字节 SHA-256 一致；.gitattributes 固定对应换行方式，使新的 Git checkout 保持这些字节。
- 未记录的基础代码沿用 GitHub main；不声称实验清单覆盖了整个脏工作树。所恢复文件均有实验哈希证据，未引入 v1.2 修复。
- 默认 Harness/Deep/ARM 开启，positive_evidence、solver reasoning OFF；Hybrid、bank、RAG、Skills 关闭；ARM 3 calls / 16384 tokens，与实验默认配置一致。客户端模型由平台提供，本地实验使用 intern-s2。
- 合并 GitCode 原 main 4ff7a40f9b2200bdf8e3855133110aeae624bc28，保留历史，以普通快进推送发布；不改写 GitHub main。

## 验证

- 全套 unittest：1053 项，1049 通过、4 跳过。首次干净工作树缺失本地受控 eval_112.json，导致两个数据测试错误；补齐本地测试夹具后全套通过。该文件不跟踪、不发布。
- 独立 venv 仅安装入口需要的 requests、sympy；不加载默认关闭的可选 RAG 组件。
- verify.py：10 个实验源码字节哈希、默认配置、三个并发官方公开 client 契约 solve、非空 final_response 与 JSON 序列化验证。
- 新生成的 Git index checkout：全部 10 个文件逐字节哈希吻合；独立 venv 的 verify.py 通过。
- git diff --check / staged diff --check；提交范围为上述实验恢复与发布核验材料。
- 未新增真实模型实验。历史 221 题结果属于本地诊断；发布不表示已完成平台隐藏评测或提交作品页面操作。

复核命令（仓库根目录）：`python docs/releases/grh-v1.1-20261002/verify.py`。
