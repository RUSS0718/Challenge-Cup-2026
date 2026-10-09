# 条件与边界求解路径本地候选

- 基线：`6a653f5774f556fe34c5841b74ad80219ebde421`，统一1150秒预算。
- 状态：`OPEN / LOCAL_CODE_ACCEPTED / DIAGNOSTIC_SMOKE_ONLY / NO_CAPABILITY_CONCLUSION`。
- 用户于2026-10-09授权在本地1150配置上调整第一条额外路径。

唯一生成变量是第2路的system提示词：在原提示词后增加必要条件、充分条件、
解集完整性、极值可达性、定义域和关键变形的检查重点。第1路和第3路仍使用
原提示词。新请求只含system和当前题目，未注入其他路径答案；本路恢复、
续写和修正继续继承自身上下文。

原有加路条件、温度（0.2/0.6/0.6）、token额度、统一1150秒截止、
共享6次调用上限、验证器和投票规则保持一致。不启用答案保护、verified
提前交付、证据优先投票，也不强制任何题进入加路。

提示词定义位于`implementations/candidates/sl_v3_cont/path_prompts.py`。
路径计数在每次solve开始时重置，并且只在实际开始额外路径时递增。

本候选有别于历史4k/k5的`hetero_k5`、短候选CAR-002以及针对已有答案的
CFR修正：本次仅在当前SL-v3条件加路中的第2路增加求解侧重点，保持既有
生成额度和选择流程。它不继承历史候选的收益或通过状态。

验证命令（零远程请求）：

```powershell
python -m pytest -q -p no:cacheprovider tests/test_boundary_check_path.py tests/test_intern_s2_import.py tests/test_intern_architecture_isolation.py tests/test_llm_client.py
```

新测试通过正式入口捕获请求，覆盖第2路提示词生效、跨路答案隔离、
第3路还原、单路早退、复用代理、请求失败、续写、6次调用和检查点协议。
验收结果：27项测试及11项子测试通过；`git diff --check`通过。
源码与来源哈希以发布目录的`source_sha256.json`为准。

尚未进行真实模型A/B，不推断正确率改善。下一次模型实验需冻结新题集、
同条件对照及健康/成本门槛，记录各路答案以区分候选生成收益与选择收益。
用户于2026-10-09随后授权撤回GitCode protection并发布本候选；
发布范围及入口审计见[发布说明](../../releases/main-boundary-path-1150-20261009.md)。

2026-10-09用户授权半小时诊断smoke，运行7题（easy3、medium2、hard2）；
第二路在一道选择题68.498秒完整返回（2827tokens），一道概率题350秒请求超时，
当时单题仍剩约653秒。用户随后将本地请求上限改为1000秒，补跑两道hard和
概率题；概率题第二路91.209秒完整返回（3831tokens）。两道hard首路与概率题
第三路在窗口停止时尚未返回，不能当作1000秒请求超时或1150秒用尽。
未观察到length截断，不支持增加第二路token额度；本窗不是配对能力实验。
监控曾发生Windows文件占用错误，恢复监控未重发请求；本地测试进程已停止。
产物：`artifacts/SLV3-BOUNDARY-SMOKE-30M-20261009-001/`，含逐路答案与请求事件。
